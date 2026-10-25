"""JSON registry with human-approved promotion and rollback history."""
import json
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Any


def register_model(registry_path: Path | str, entry: dict[str, Any]) -> None:
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"models": []}
    entry = {**entry, "registered_at": datetime.now(timezone.utc).isoformat(),
             "lifecycle": entry.get("lifecycle", "CANDIDATE")}
    payload["models"].append(entry)
    _write(path, payload)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "models": [], "current_model_versions": {}, "promotion_history": []}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


def compare_candidate(registry_path: Path | str, candidate_version: str, *,
                      acceptance: dict[str, Any]) -> dict[str, Any]:
    """Compare candidate against the current version only on an identical held-out context."""
    payload = _read(Path(registry_path))
    candidate = next((m for m in payload["models"] if m.get("version") == candidate_version), None)
    if candidate is None:
        raise KeyError("Candidate model version not found")
    key = f"{candidate.get('dataset')}:{candidate.get('name')}"
    current_version = payload.get("current_model_versions", {}).get(key)
    current = next((m for m in payload["models"] if m.get("version") == current_version), None)
    if current is None:
        return {"status": "NO_CURRENT_MODEL", "candidate_version": candidate_version,
                "acceptance_met": False, "reasons": ["No current model is assigned for comparison."]}
    candidate_context = candidate.get("evaluation_context") or {}
    current_context = current.get("evaluation_context") or {}
    if not candidate_context or candidate_context != current_context:
        return {"status": "INCOMPARABLE_EVALUATION_CONTEXT", "candidate_version": candidate_version,
                "current_version": current_version, "acceptance_met": False,
                "reasons": ["Models must share the same held-out data hash and split context."]}
    metric = str(acceptance.get("primary_metric", "macro_f1"))
    minimum_improvement = float(acceptance.get("minimum_improvement", 0.0))
    current_metrics = current.get("metrics", {}).get("test", {})
    candidate_metrics = candidate.get("metrics", {}).get("test", {})
    current_value, candidate_value = current_metrics.get(metric), candidate_metrics.get(metric)
    reasons = []
    if not isinstance(current_value, (int, float)) or not isinstance(candidate_value, (int, float)):
        reasons.append(f"Required metric '{metric}' is missing from one or both models.")
    elif float(candidate_value) - float(current_value) < minimum_improvement:
        reasons.append(f"Candidate improvement on '{metric}' is below the configured minimum.")
    max_brier_increase = acceptance.get("maximum_brier_increase")
    if max_brier_increase is not None:
        old_brier, new_brier = current_metrics.get("brier_score"), candidate_metrics.get("brier_score")
        if isinstance(old_brier, (int, float)) and isinstance(new_brier, (int, float)):
            if float(new_brier) - float(old_brier) > float(max_brier_increase):
                reasons.append("Candidate exceeds the configured maximum Brier score increase.")
        elif acceptance.get("require_brier"):
            reasons.append("Brier score is required by acceptance criteria but is missing.")
    return {"status": "ACCEPTANCE_MET" if not reasons else "ACCEPTANCE_NOT_MET",
            "candidate_version": candidate_version, "current_version": current_version,
            "primary_metric": metric, "current_value": current_value,
            "candidate_value": candidate_value, "reasons": reasons,
            "acceptance_met": not reasons, "evaluation_context": candidate_context}


def promote_candidate(registry_path: Path | str, candidate_version: str, *,
                      acceptance: dict[str, Any], reviewer: str, reason: str) -> dict[str, Any]:
    """Promote only after acceptance criteria and a human reviewer decision."""
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer and reason are required for model promotion")
    path = Path(registry_path)
    payload = _read(path)
    comparison = compare_candidate(path, candidate_version, acceptance=acceptance)
    if not comparison.get("acceptance_met"):
        raise ValueError("Candidate does not meet promotion acceptance criteria")
    candidate = next(m for m in payload["models"] if m.get("version") == candidate_version)
    key = f"{candidate.get('dataset')}:{candidate.get('name')}"
    previous = payload.get("current_model_versions", {}).get(key)
    for model in payload["models"]:
        if model.get("version") == previous:
            model["lifecycle"] = "SUPERSEDED"
        if model.get("version") == candidate_version:
            model["lifecycle"] = "CURRENT"
    payload.setdefault("current_model_versions", {})[key] = candidate_version
    event = {"event": "MODEL_PROMOTED", "model_key": key, "from_version": previous,
             "to_version": candidate_version, "reviewer": reviewer.strip(),
             "reason": reason.strip(), "criteria": acceptance,
             "at": datetime.now(timezone.utc).isoformat()}
    payload.setdefault("promotion_history", []).append(event)
    _write(path, payload)
    return {"status": "PROMOTED", **event}


def set_initial_current(registry_path: Path | str, model_version: str, *,
                        reviewer: str, reason: str) -> dict[str, Any]:
    """Explicitly approve the first current model; never choose one automatically."""
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer and reason are required for initial model approval")
    path = Path(registry_path)
    payload = _read(path)
    model = next((item for item in payload["models"] if item.get("version") == model_version), None)
    if model is None:
        raise KeyError("Model version not found")
    key = f"{model.get('dataset')}:{model.get('name')}"
    if payload.get("current_model_versions", {}).get(key):
        raise ValueError("A current model already exists; use candidate comparison and promotion")
    payload.setdefault("current_model_versions", {})[key] = model_version
    model["lifecycle"] = "CURRENT"
    event = {"event": "MODEL_INITIALIZED", "model_key": key, "from_version": None,
             "to_version": model_version, "reviewer": reviewer.strip(), "reason": reason.strip(),
             "at": datetime.now(timezone.utc).isoformat()}
    payload.setdefault("promotion_history", []).append(event)
    _write(path, payload)
    return {"status": "CURRENT", **event}


def rollback_model(registry_path: Path | str, model_key: str, *, reviewer: str,
                   reason: str) -> dict[str, Any]:
    """Restore the last superseded version by explicit reviewer request."""
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer and reason are required for rollback")
    path = Path(registry_path)
    payload = _read(path)
    current = payload.get("current_model_versions", {}).get(model_key)
    prior_events = [event for event in payload.get("promotion_history", [])
                    if event.get("model_key") == model_key and event.get("to_version") == current]
    prior = prior_events[-1].get("from_version") if prior_events else None
    if not prior:
        raise ValueError("No previous model version is available for rollback")
    for model in payload["models"]:
        if model.get("version") == current:
            model["lifecycle"] = "ROLLED_BACK"
        if model.get("version") == prior:
            model["lifecycle"] = "CURRENT"
    payload["current_model_versions"][model_key] = prior
    event = {"event": "MODEL_ROLLED_BACK", "model_key": model_key, "from_version": current,
             "to_version": prior, "reviewer": reviewer.strip(), "reason": reason.strip(),
             "at": datetime.now(timezone.utc).isoformat()}
    payload.setdefault("promotion_history", []).append(event)
    _write(path, payload)
    return {"status": "ROLLED_BACK", **event}
