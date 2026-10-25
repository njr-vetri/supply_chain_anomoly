"""Canonical-only project pipeline with per-step status and retry reporting."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from src.core.lineage import derive_with_lineage
from src.data.generic_validation import RuleConfig, validate_canonical_records
from src.ml.anomaly.canonical import detect_canonical_anomalies
from src.ml.delay.canonical import evaluate_canonical_delay
from src.ml.delay.canonical_demand import forecast_canonical_demand


def preview_pipeline(capabilities: dict[str, Any]) -> dict[str, Any]:
    steps = [{"name": name, "supported": item["status"] in {"AVAILABLE", "AVAILABLE_WITH_LIMITATIONS"},
              "capability_status": item["status"]}
             for name, item in capabilities["features"].items()]
    return {"id": str(uuid4()), "status": "PREVIEW", "dry_run": True, "steps": steps,
            "message": "Preview only. No pipeline step has run."}


def run_canonical_pipeline(*, canonical_files: list[Path], capabilities: dict[str, Any],
                           rules: RuleConfig | None = None, retry_attempts: int = 3,
                           retry_backoff_seconds: float = 0.0,
                           sleep: Callable[[float], None] = time.sleep,
                           on_step: Callable[[dict[str, Any]], None] | None = None,
                           anomaly_settings: Any = None, delay_settings: Any = None,
                           forecast_settings: Any = None) -> dict[str, Any]:
    """Load canonical JSONL only. Feature steps are gated by capability status."""
    run_id = str(uuid4())
    status = "RUNNING"
    step_results: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for path in canonical_files:
        with path.open(encoding="utf-8") as stream:
            records.extend(json.loads(line) for line in stream if line.strip())
    steps = [("validation", lambda: validate_canonical_records(records, rules=rules).model_dump(mode="json"))]
    delay_result: dict[str, Any] = {}
    for feature in ("anomaly_detection", "delay_prediction", "demand_analysis", "inventory_risk",
                    "dependency_graph", "model_evaluation"):
        capability = capabilities["features"][feature]
        if capability["status"] not in {"AVAILABLE", "AVAILABLE_WITH_LIMITATIONS"}:
            skipped = {"name": feature, "status": "SKIPPED", "reason": capability["status"],
                       "missing_roles": capability.get("missing_roles", [])}
            step_results.append(skipped)
            if on_step:
                on_step(skipped)
        else:
            def build_summary(name=feature):
                if name == "demand_analysis":
                    return forecast_canonical_demand(records, forecast_settings) if forecast_settings else {
                        "status": "AWAITING_CONFIGURATION", "missing": ["forecast settings"]}
                if name == "anomaly_detection":
                    return detect_canonical_anomalies(records, anomaly_settings) if anomaly_settings else {
                        "status": "AWAITING_CONFIGURATION", "missing": ["anomaly settings"]}
                if name == "delay_prediction":
                    if delay_settings:
                        delay_result.update(evaluate_canonical_delay(records, delay_settings))
                        return delay_result
                    return {"status": "AWAITING_CONFIGURATION", "missing": ["delay settings"]}
                if name == "model_evaluation":
                    if not delay_result:
                        return {"status": "NOT_COMPUTED", "missing": ["supported labelled delay run"]}
                    return {"status": delay_result.get("status"), "models": delay_result.get("models", {}),
                            "split": delay_result.get("split"),
                            "limitations": delay_result.get("limitations", [])}
                return {"status": "available_inputs_detected", "records": len(records)}
            steps.append((feature, build_summary))
    steps.append(("feature_lineage", lambda: [lineage.model_dump(mode="json")
        for record in records[:500] for lineage in derive_with_lineage(record)]))
    for name, operation in steps:
        attempt = 0
        while True:
            attempt += 1
            if on_step:
                on_step({"name": name, "status": "RUNNING", "attempts": attempt})
            try:
                value = operation()
                completed = {"name": name, "status": "COMPLETED", "attempts": attempt, "result": value}
                step_results.append(completed)
                if on_step:
                    on_step(completed)
                break
            except Exception as exc:  # report type only; avoid leaking row values
                if attempt >= retry_attempts:
                    failed = {"name": name, "status": "FAILED", "attempts": attempt,
                              "error": type(exc).__name__}
                    step_results.append(failed)
                    if on_step:
                        on_step(failed)
                    status = "FAILED"
                    break
                if on_step:
                    on_step({"name": name, "status": "RETRYING", "attempts": attempt,
                             "error": type(exc).__name__})
                sleep(retry_backoff_seconds * attempt)
        if status == "FAILED":
            break
    if status != "FAILED":
        status = "COMPLETED"
    return {"id": run_id, "status": status, "records_read": len(records),
            "capabilities": capabilities, "steps": step_results, "dry_run": False}
