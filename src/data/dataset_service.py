"""Dataset onboarding service managing uploads, profiling, schema mapping, and profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile
from datetime import datetime, timezone

from src.data.profile import CANONICAL_ROLES, TIMESTAMP_ROLES, DatasetProfile, detect_capabilities
from src.data.profiler import DatasetProfileReport, profile_data
from src.data.schema_mapper import MappingSuggestionReport, suggest_mappings
from src.core.config import load_settings


UPLOAD_DIR = Path("data/raw/uploads")
PROFILE_DIR = Path("config/profiles")
REGISTRY_PATH = UPLOAD_DIR / "registry.json"

# Optional compatibility override used by tests; production limits come from settings.yaml.
MAX_UPLOAD_SIZE: int | None = None
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".json", ".jsonl", ".zip"}


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def _load_registry() -> dict[str, Any]:
    _ensure_dirs()
    if not REGISTRY_PATH.exists():
        return {}
    try:
        with REGISTRY_PATH.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return {}


def _save_registry(registry: dict[str, Any]) -> None:
    _ensure_dirs()
    with REGISTRY_PATH.open("w", encoding="utf-8") as stream:
        json.dump(registry, stream, indent=2, ensure_ascii=False)


def _path_for_registry(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def handle_upload(
    filename: str,
    content: bytes,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    """Validate, secure, store, and profile an uploaded dataset file."""
    _ensure_dirs()

    # 1. Size limit validation
    max_upload_size = MAX_UPLOAD_SIZE or load_settings().uploads.max_size_bytes
    if len(content) > max_upload_size:
        raise ValueError(f"File size exceeds maximum upload limit ({len(content)} > {max_upload_size} bytes)")

    # 2. Path-traversal sanitization
    sanitized_name = Path(filename).name
    if not sanitized_name or sanitized_name in {".", ".."} or "/" in filename or "\\" in filename:
        sanitized_name = Path(filename.replace("\\", "/")).name
    if not sanitized_name:
        raise ValueError("Invalid filename provided")

    # 3. Allowed file types
    ext = Path(sanitized_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File extension '{ext}' is not permitted. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    # 4. Hash content with SHA-256
    sha256 = hashlib.sha256(content).hexdigest()

    # 5. Determine dataset identifier
    name = (dataset_name.strip() if dataset_name else None) or Path(sanitized_name).stem
    # Sanitize name
    name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name.lower())

    # 6. Store file safely under data/raw/uploads/
    stored_filename = f"{sha256[:16]}_{sanitized_name}"
    target_path = UPLOAD_DIR / stored_filename
    with target_path.open("wb") as stream:
        stream.write(content)

    # 7. Run in-memory profiler (includes zip-bomb and formula injection checks)
    profile_report = profile_data(
        content,
        filename=sanitized_name,
        dataset_name=name,
    )

    # 8. Update upload registry
    registry = _load_registry()
    prior_events = registry.get(name, {}).get("events", [])
    registry[name] = {
        "dataset_name": name,
        "filename": sanitized_name,
        "stored_file": _path_for_registry(target_path),
        "sha256": sha256,
        "total_rows": profile_report.total_rows,
        "total_columns": profile_report.total_columns,
        "file_type": profile_report.file_type,
        "has_formula_injection_risk": profile_report.has_formula_injection_risk,
        "status": "PENDING_MAPPING",
        "events": [*prior_events, {"event": "upload_registered", "occurred_at": datetime.now(timezone.utc).isoformat()}],
    }
    _save_registry(registry)

    return {
        "dataset_name": name,
        "filename": sanitized_name,
        "sha256": sha256,
        "total_rows": profile_report.total_rows,
        "total_columns": profile_report.total_columns,
        "file_type": profile_report.file_type,
        "has_formula_injection_risk": profile_report.has_formula_injection_risk,
        "columns": [col.model_dump(mode="json") for col in profile_report.columns],
    }


def get_dataset_suggestions(dataset_name: str) -> MappingSuggestionReport:
    """Compute mapping suggestions for an uploaded or profiled dataset without auto-confirming."""
    _ensure_dirs()
    registry = _load_registry()

    target_file: Path | None = None
    source_filename = f"{dataset_name}.csv"

    if dataset_name in registry:
        stored_file = registry[dataset_name].get("stored_file")
        if stored_file and Path(stored_file).exists():
            target_file = Path(stored_file)
            source_filename = registry[dataset_name].get("filename", source_filename)

    # Check config/profiles as fallback
    profile_path = PROFILE_DIR / f"{dataset_name}.yaml"
    if target_file is None and profile_path.exists():
        profile = DatasetProfile.load(profile_path)
        # Profile already confirmed, but suggestions can still be generated from known files
        if profile.source_file:
            candidates = list(Path(".").glob(f"*{profile.source_file}*"))
            if candidates:
                target_file = candidates[0]
                source_filename = profile.source_file

    if target_file is None or not target_file.exists():
        raise FileNotFoundError(f"Uploaded dataset source for '{dataset_name}' not found")

    report = profile_data(target_file, filename=source_filename, dataset_name=dataset_name)
    return suggest_mappings(report)


def confirm_dataset_mapping(
    dataset_name: str,
    mappings: dict[str, str],
    description: str = "",
    profile_dir: Path | str | None = None,
) -> DatasetProfile:
    """Validate, detect capabilities, and persist a confirmed dataset profile."""
    _ensure_dirs()
    registry = _load_registry()

    reg_entry = registry.get(dataset_name, {})
    sha256 = reg_entry.get("sha256", "")
    source_file = reg_entry.get("filename", "")

    # Validate mappings and detect capabilities
    capabilities = detect_capabilities(mappings)

    profile = DatasetProfile(
        name=dataset_name,
        version="1.0",
        description=description or reg_entry.get("description", f"Profile for {dataset_name}"),
        source_file=source_file,
        source_archive_sha256=sha256,
        mappings=mappings,
        capabilities=capabilities,
    )
    profile.save(profile_dir=profile_dir or PROFILE_DIR)

    if dataset_name in registry:
        registry[dataset_name]["status"] = "CONFIRMED"
        registry[dataset_name]["capabilities"] = capabilities.model_dump(mode="json")
        _save_registry(registry)

    return profile


def list_datasets() -> list[dict[str, Any]]:
    """List all registered and confirmed datasets with their statuses and capabilities."""
    _ensure_dirs()
    registry = _load_registry()
    items: dict[str, dict[str, Any]] = {}

    # Read saved profiles
    for profile_file in PROFILE_DIR.glob("*.yaml"):
        name = profile_file.stem
        try:
            profile = DatasetProfile.load(profile_file)
            items[name] = {
                "dataset_name": name,
                "status": registry.get(name, {}).get("status", "CONFIRMED"),
                "source_file": profile.source_file,
                "sha256": profile.source_archive_sha256,
                "mappings": profile.mappings,
                "capabilities": profile.capabilities.model_dump(mode="json") if profile.capabilities else None,
                "profile_path": _path_for_registry(profile_file),
                "deleted_at": registry.get(name, {}).get("deleted_at"),
            }
        except Exception:
            continue

    # Merge unconfirmed uploads from registry
    for name, entry in registry.items():
        if name not in items:
            items[name] = {
                "dataset_name": name,
                "status": entry.get("status", "PENDING_MAPPING"),
                "source_file": entry.get("filename", ""),
                "sha256": entry.get("sha256", ""),
                "mappings": {},
                "capabilities": None,
                "profile_path": None,
            }
        else:
            if not items[name]["sha256"]:
                items[name]["sha256"] = entry.get("sha256", "")

    return list(items.values())


def delete_dataset(dataset_name: str) -> bool:
    """Soft-delete a dataset registration; raw files and mapping history are retained."""
    _ensure_dirs()
    deleted = False

    registry = _load_registry()
    profile_exists = (PROFILE_DIR / f"{dataset_name}.yaml").is_file()
    if dataset_name not in registry and not profile_exists:
        return False
    entry = registry.setdefault(dataset_name, {"dataset_name": dataset_name})
    timestamp = datetime.now(timezone.utc).isoformat()
    entry["status"] = "DELETED"
    entry["deleted_at"] = timestamp
    entry.setdefault("events", []).append({"event": "soft_deleted", "occurred_at": timestamp})
    _save_registry(registry)
    deleted = True
    return deleted
