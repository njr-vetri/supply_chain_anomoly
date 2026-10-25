"""Company-scoped local file paths for imported/derived artifacts.

Strictly enforces filesystem multi-tenant boundary under base_dir/tenants/{company_id}/
and prevents directory traversal attacks, path escapes, and null byte injection.
"""
from __future__ import annotations

import os
from pathlib import Path
import re


def validate_safe_relative_path(relative_path: str) -> str:
    """Validate relative path to prevent directory traversal and null byte injection."""
    if not relative_path or not relative_path.strip():
        raise ValueError("Relative path cannot be empty")
    cleaned = relative_path.strip()
    if "\x00" in cleaned:
        raise ValueError("Null bytes not permitted in file path")
    # Disallow absolute paths
    if os.path.isabs(cleaned) or cleaned.startswith(("/", "\\")):
        raise ValueError("Path must be relative, not absolute")
    return cleaned


def company_file_path(base_dir: Path | str, company_id: str, relative_path: str) -> Path:
    """Resolve and enforce that relative_path strictly stays within company storage root."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", company_id):
        raise ValueError("Invalid company_id: must match [A-Za-z0-9_-]{1,128}")
    clean_relative = validate_safe_relative_path(relative_path)
    base = Path(base_dir).resolve()
    company_root = (base / "tenants" / company_id).resolve()
    target = (company_root / clean_relative).resolve()
    if target != company_root and company_root not in target.parents:
        raise ValueError("File path escapes company storage")
    return target


class TenantFileStore:
    """Per-tenant isolated file storage partitioning uploads, parquet, models, and logs."""

    def __init__(self, base_dir: Path | str = "data", *, company_id: str):
        if not company_id or not company_id.strip():
            raise ValueError("company_id is required")
        self.base_dir = Path(base_dir)
        self.company_id = company_id.strip()

    def get_path(self, relative_path: str) -> Path:
        return company_file_path(self.base_dir, self.company_id, relative_path)

    def write_bytes(self, relative_path: str, content: bytes) -> Path:
        target = self.get_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def read_bytes(self, relative_path: str) -> bytes:
        target = self.get_path(relative_path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return target.read_bytes()

    def exists(self, relative_path: str) -> bool:
        try:
            return self.get_path(relative_path).exists()
        except ValueError:
            return False

    def delete_file(self, relative_path: str) -> bool:
        target = self.get_path(relative_path)
        if target.is_file():
            target.unlink()
            return True
        return False

    def list_files(self, subfolder: str = "") -> list[str]:
        target_dir = self.get_path(subfolder) if subfolder else (self.base_dir / "tenants" / self.company_id).resolve()
        if not target_dir.is_dir():
            return []
        files: list[str] = []
        for p in target_dir.rglob("*"):
            if p.is_file():
                files.append(p.relative_to(target_dir).as_posix())
        return files

    def upload_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        return self.get_path(f"uploads/{safe_name}")

    def parquet_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        return self.get_path(f"parquet/{safe_name}")

    def model_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        return self.get_path(f"models/{safe_name}")

    def log_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        return self.get_path(f"logs/{safe_name}")
