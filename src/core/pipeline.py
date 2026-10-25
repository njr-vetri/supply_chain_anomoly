"""Local end-to-end orchestration for validated, source-separated risk runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from src.alerts.channels import ConsoleChannel, FileChannel
from src.alerts.manager import AlertManager
from src.core.audit import AuditLog
from src.core.config import load_settings
from src.core.repository import (AnomalyRow, AuditEventRow, EvidenceRow, HypothesisRow, IncidentRow, ModelVersionRow, PredictionRow,
    QualitySnapshotRow, RecommendationRow, Repository)
from src.adapters.base import get_adapter
from src.adapters.features import build_feature_groups
from src.data.validation import validate_frame
from src.monitoring.drift import compare_profiles, profile_frame
from src.ml.anomaly.isolation_forest import detect as detect_isolation
from src.ml.anomaly.rule_based import detect as detect_rule
from src.ml.anomaly.statistical import iqr, robust_zscore
from src.recommendations.engine import recommend
from src.risk.engine import prioritize
from src.risk.investigator import investigate


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def _find_source(dataset: str, root: Path) -> Path:
    adapter = get_adapter(dataset, root / "config" / "profiles")
    candidates = sorted(set(root.glob("*.zip")) | set((root / "data" / "raw").rglob("*.zip")))
    matches = [path for path in candidates if adapter.detect(path)]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one source archive for configured profile '{dataset}', found {len(matches)}")
    return matches[0]


def _features(dataset: str, frames: list[tuple[str, pd.DataFrame]], settings: Any):
    """Compatibility name used by earlier pipeline tests; source logic lives in adapters."""
    return build_feature_groups(dataset, frames, settings)


def _quality(dataset: str, member: str, frame: pd.DataFrame, dataset_version_id: str,
             repository: Repository, settings: Any, *, root: Path, source_hash: str,
             chunk_index: int, snapshot_member: str | None = None
             ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    required = {
        "olist": {"olist_orders_dataset": ["order_id", "order_purchase_timestamp"],
                  "olist_order_items_dataset": ["order_id", "order_item_id"]},
        "dataco": {"datacosupplychaindataset": ["Order Item Id", "Late_delivery_risk",
                                                   "order date (DateOrders)"]},
        "online_retail_ii": {"online_retail_ii": ["StockCode", "InvoiceDate", "Quantity"]},
    }[dataset].get(Path(member.split(" [")[0]).stem.lower(), [])
    date_columns = [column for column in frame.columns
                    if "date" in str(column).lower() or "timestamp" in str(column).lower()]
    preferred_freshness = {"olist": ["order_purchase_timestamp", "review_creation_date"],
                           "dataco": ["order date (DateOrders)"],
                           "online_retail_ii": ["InvoiceDate"]}[dataset]
    freshness_column = next((column for column in preferred_freshness if column in frame.columns), None)
    valid, quarantined, report = validate_frame(
        frame, source=f"{dataset}:{member}", required_columns=required, date_columns=date_columns,
        freshness_column=freshness_column,
        freshness_max_age_hours=settings.data.freshness_max_age_hours,
        max_null_fraction=settings.data.max_null_fraction)
    null_rates = {column: count / len(frame) if len(frame) else 0.0
                  for column, count in report.null_counts.items()}
    snapshot_source = f"{dataset}:{snapshot_member or member}"
    previous = repository.prior_quality(snapshot_source)
    current_profile = profile_frame(frame)
    drift: dict[str, Any] = {"status": "BASELINE_CREATED", "row_count_change_fraction": None,
                             "null_rate_changes": {}, "schema": {"added_columns": [],
                             "removed_columns": [], "type_changes": {}}, "alerts": [],
                             "profile": current_profile}
    if previous:
        prior_profile = (previous.drift or {}).get("profile") or {
            "row_count": previous.row_count,
            "columns": {name: {"dtype": "UNKNOWN", "null_rate": rate}
                        for name, rate in previous.null_rates.items()},
        }
        drift = compare_profiles(prior_profile, current_profile,
            max_row_count_change_fraction=settings.drift.max_row_count_change_fraction,
            max_null_rate_change=settings.drift.max_null_rate_change,
            max_numeric_mean_shift=settings.drift.max_numeric_mean_shift,
            max_category_concentration_change=settings.drift.max_category_concentration_change)
        drift["profile"] = current_profile
    snapshot = QualitySnapshotRow(id=str(uuid4()), dataset_version_id=dataset_version_id,
        source=snapshot_source, observed_at=datetime.now(timezone.utc), row_count=report.total_rows,
        null_rates=null_rates, drift=drift)
    repository.add(snapshot)
    quarantine_path = None
    if not quarantined.empty:
        quarantine_dir = root / "data" / "processed" / "quarantine" / dataset
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        target = quarantine_dir / f"{Path(member).stem}.chunk{chunk_index:04d}.jsonl"
        with target.open("w", encoding="utf-8") as stream:
            for row_index, row in quarantined.iterrows():
                stream.write(json.dumps({"dataset": dataset, "source_archive_sha256": source_hash,
                    "source_member": member, "chunk_index": chunk_index, "row_offset": int(row_index),
                    "reason": str(row.get("_quarantine_reasons", "unspecified"))},
                    ensure_ascii=False) + "\n")
        quarantine_path = str(target.relative_to(root))
    return valid, quarantined, {"member": member, "quality": report.model_dump(mode="json"),
                                "drift": drift, "quarantine_manifest": quarantine_path}


def _detect(feature_groups: list[dict[str, Any]], settings: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    anomalies: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for group in feature_groups:
        frame: pd.DataFrame = group["frame"]
        record_ids: pd.Series = group["record_ids"]
        for feature, threshold, direction in group["monitored"]:
            if feature not in frame:
                continue
            values = frame[feature]
            detectors = {
                "rule": detect_rule(values, threshold, direction=direction),
                "robust_zscore": robust_zscore(values, settings.anomaly.robust_z_threshold),
                "iqr": iqr(values, settings.anomaly.iqr_multiplier),
            }
            if settings.pipeline.enable_isolation_forest:
                try:
                    detectors["isolation_forest"] = detect_isolation(
                        values, settings.anomaly.isolation_forest_contamination,
                        settings.anomaly.isolation_forest_estimators, settings.anomaly.random_seed)
                except RuntimeError:
                    pass
            for detector, result in detectors.items():
                flagged = result.loc[result["anomaly"]]
                counts[detector] = counts.get(detector, 0) + len(flagged)
                for index, row in flagged.iterrows():
                    anomalies.append({"dataset": group["source"], "detector": detector,
                        "record_ref": str(record_ids.loc[index]), "feature": feature,
                        "observed_value": _json_value(row["observed_value"]),
                        "baseline": _json_value(row["baseline"]),
                        "source_sheet": group.get("sheet")})
    return anomalies, counts


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value.isoformat() if hasattr(value, "isoformat") else value


def _sync_audit_events(audit_log: AuditLog, repository: Repository) -> None:
    """Import earlier chained JSONL events so the SQLite chain has no gaps."""
    with repository.sessions() as session:
        known_hashes = {item[0] for item in session.query(AuditEventRow.event_hash).all()}
    missing = []
    for event in audit_log.read_all():
        if event.event_hash in known_hashes:
            continue
        missing.append(AuditEventRow(id=event.id, event_type=event.event_type, actor=event.actor,
            source=event.source, occurred_at=event.occurred_at, previous_hash=event.previous_hash,
            event_hash=event.event_hash, payload={"record_refs": event.record_refs, "details": event.details}))
        known_hashes.add(event.event_hash)
    repository.add_many(missing)


def _predict(dataset: str, groups: list[dict[str, Any]], root: Path, dataset_version_id: str,
             repository: Repository, settings: Any) -> tuple[dict[str, dict[str, Any]], int]:
    """Apply only already-registered Logistic Regression artifacts, if present."""
    if dataset == "online_retail_ii":
        if not groups:
            return {}, 0
        group = groups[0]
        weekly = group["frame"].sort_values(["StockCode", "week"])
        latest = weekly.groupby("StockCode", sort=True).tail(1).head(settings.pipeline.max_predictions_per_dataset)
        if latest.empty:
            return {}, 0
        model_id = str(uuid4())
        repository.add(ModelVersionRow(id=model_id, dataset_version_id=dataset_version_id,
            name="demand_forecast_naive", version="last-observed-week-v1",
            artifact_hash=hashlib.sha256(b"naive forecast: last observed product-week quantity").hexdigest(),
            trained_at=None, training_data_version=dataset_version_id,
            payload={"method": "next-week forecast equals most recent weekly quantity",
                     "task": "demand forecasting, not stockout prediction", "limitations": [
                         "Simple baseline only; no forecast quality metric is claimed."]}))
        results = {}
        for _, row in latest.iterrows():
            ref = f"{row['StockCode']}@{row['week']}"
            prediction_id = str(uuid4())
            forecast_week = (pd.Timestamp(row["week"]) + pd.Timedelta(weeks=1)).isoformat()
            value = float(row["weekly_quantity"])
            repository.add(PredictionRow(id=prediction_id, dataset_version_id=dataset_version_id,
                model_version_id=model_id, source=dataset, predicted_at=datetime.now(timezone.utc),
                target="weekly_quantity_forecast", value=value, confidence=None, record_refs=[ref],
                payload={"forecast_period": forecast_week, "method": "naive last observed week",
                         "not_stockout_prediction": True}))
            results[ref] = {"id": prediction_id, "value": value, "target": "weekly_quantity_forecast"}
        return results, len(latest)
    try:
        import joblib
    except ImportError:
        return {}, 0
    registry_path = root / "src" / "ml" / "model_registry.json"
    if not registry_path.exists():
        return {}, 0
    entries = json.loads(registry_path.read_text(encoding="utf-8")).get("models", [])
    lookup = {"olist": ("olist_delay", "olist_delay-logistic_regression-v1.joblib"),
              "dataco": ("dataco_delay", "dataco_delay-logistic_regression-v1.joblib")}
    if dataset not in lookup:
        return {}, 0
    name, fallback = lookup[dataset]
    entry = next((item for item in reversed(entries) if item.get("dataset") == name and
                  Path(item.get("artifact", "")).name == fallback), None)
    artifact = root / (entry["artifact"] if entry else Path("models") / fallback)
    if not artifact.is_file():
        return {}, 0
    model = joblib.load(artifact)
    if not groups:
        return {}, 0
    frame = groups[0]["frame"].copy()
    if dataset == "olist":
        feature_names = ["estimated_transit_days", "prior_seller_delivery_days_mean",
                         "prior_seller_order_count", "delivery_buffer_days"]
        frame["delivery_buffer_days"] = frame["estimated_transit_days"] - frame["prior_seller_delivery_days_mean"]
        target = "delay_probability"
        timestamp = "order_purchase_timestamp"
        frame = frame.loc[frame["actual_delivery_days"].notna() & frame["estimated_transit_days"].notna()]
    else:
        feature_names = ["scheduled_shipping_days", "shipping_mode", "order_weekday", "order_region"]
        target = "late_delivery_risk_probability"
        timestamp = "order_timestamp"
    if any(column not in frame for column in feature_names):
        return {}, 0
    frame = frame.loc[frame[feature_names].notna().any(axis=1)]
    if timestamp in frame and not frame.empty:
        ordered = frame.sort_values(timestamp, kind="stable")
        train_end = int(len(ordered) * settings.evaluation["train_fraction"])
        frame = ordered.iloc[train_end:]
    frame = frame.head(settings.pipeline.max_predictions_per_dataset)
    if frame.empty:
        return {}, 0
    probabilities = model.predict_proba(frame[feature_names])[:, 1]
    artifact_hash = _digest(artifact)
    model_version_id = str(uuid4())
    trained_at = None
    if entry and entry.get("registered_at"):
        trained_at = pd.to_datetime(entry["registered_at"], utc=True).to_pydatetime()
    model_version = ModelVersionRow(id=model_version_id, dataset_version_id=dataset_version_id,
        name=name, version="registry-artifact", artifact_hash=artifact_hash,
        trained_at=trained_at, training_data_version=dataset_version_id,
        payload={"artifact": str(artifact.relative_to(root)), "features": feature_names,
                 "calibrated": False, "limitations": ["Stored evaluation artifact; probability calibration is not assumed."]})
    repository.add(model_version)
    result: dict[str, dict[str, Any]] = {}
    records = groups[0]["record_ids"]
    for (index, _), probability in zip(frame.iterrows(), probabilities):
        ref = str(records.loc[index])
        row_id = str(uuid4())
        repository.add(PredictionRow(id=row_id, dataset_version_id=dataset_version_id,
            model_version_id=model_version_id, source=dataset, predicted_at=datetime.now(timezone.utc),
            target=target, value=float(probability), confidence=None, record_refs=[ref],
            payload={"probability_calibrated": False, "model_version": model_version_id}))
        result.setdefault(ref, {"id": row_id, "value": float(probability), "target": target})
    return result, len(frame)


def _persist_investigation(dataset: str, anomaly: dict[str, Any], dataset_version_id: str,
                           prediction: dict[str, Any] | None, root: Path,
                           repository: Repository) -> tuple[int, int, int]:
    investigation = None
    if dataset in {"olist", "dataco"}:
        investigation = investigate({"dataset": dataset, "record_ref": anomaly["record_ref"],
            "feature": anomaly["feature"], "observed_value": anomaly["observed_value"],
            "prediction": prediction}, root=root)
    if investigation and investigation.get("status") == "evidence_found":
        incident_data = investigation["incident"]
        evidence_data = investigation["evidence"]
        hypothesis_data = investigation["hypothesis"]
        incident_id, evidence_id, hypothesis_id = (incident_data["id"], evidence_data["id"], hypothesis_data["id"])
        occurred_at = datetime.fromisoformat(incident_data["occurred_at"])
        repository.add(IncidentRow(id=incident_id, dataset_version_id=dataset_version_id,
            prediction_id=(prediction or {}).get("id"), source=dataset, title=incident_data["title"],
            occurred_at=occurred_at, payload=incident_data))
        repository.add(EvidenceRow(id=evidence_id, dataset_version_id=dataset_version_id,
            incident_id=incident_id, source=dataset, observed_at=datetime.fromisoformat(evidence_data["observed_at"]),
            record_refs=evidence_data["record_refs"], payload=evidence_data))
        repository.add(HypothesisRow(id=hypothesis_id, incident_id=incident_id,
            statement=hypothesis_data["statement"], status=hypothesis_data["status"], payload=hypothesis_data))
        return incident_id, evidence_id, hypothesis_id
    now = datetime.now(timezone.utc)
    incident_id, evidence_id, hypothesis_id = str(uuid4()), str(uuid4()), str(uuid4())
    refs = [anomaly["record_ref"]]
    incident_data = {"id": incident_id, "title": f"Observed {anomaly['feature']} anomaly",
        "description": "Signal grouped from a validated dataset record; no cause inferred.",
        "source": dataset, "record_refs": refs, "occurred_at": now.isoformat(),
        "evidence_refs": [evidence_id], "limitations": ["Exposure is not causation."]}
    evidence_data = {"id": evidence_id, "evidence_type": "validated_feature_observation",
        "source": dataset, "record_refs": refs, "observed_at": now.isoformat(),
        "facts": {"feature": anomaly["feature"], "observed_value": anomaly["observed_value"],
                  "baseline": anomaly["baseline"], "detector": anomaly["detector"],
                  "source_sheet": anomaly.get("source_sheet")},
        "limitations": ["Derived feature evidence only; independent corroboration is missing."]}
    hypothesis_data = {"id": hypothesis_id, "statement": f"The {anomaly['feature']} signal reflects an operational condition.",
        "status": "UNVERIFIED", "source": dataset, "record_refs": refs,
        "evidence_refs": [evidence_id], "missing_evidence": ["Independent corroboration"]}
    repository.add(IncidentRow(id=incident_id, dataset_version_id=dataset_version_id,
        prediction_id=(prediction or {}).get("id"), source=dataset, title=incident_data["title"],
        occurred_at=now, payload=incident_data))
    repository.add(EvidenceRow(id=evidence_id, dataset_version_id=dataset_version_id,
        incident_id=incident_id, source=dataset, observed_at=now, record_refs=refs, payload=evidence_data))
    repository.add(HypothesisRow(id=hypothesis_id, incident_id=incident_id, statement=hypothesis_data["statement"],
        status="UNVERIFIED", payload=hypothesis_data))
    return incident_id, evidence_id, hypothesis_id


def _route_alert(dataset: str, dataset_version_id: str, flagged_total: int, run_id: str, root: Path,
                 repository: Repository, audit_log: AuditLog, settings: Any) -> dict[str, Any]:
    severity = "LOW"
    for candidate in ("MEDIUM", "HIGH", "CRITICAL"):
        if flagged_total >= settings.pipeline.severity_thresholds.get(candidate, 0):
            severity = candidate
    manager = AlertManager(channels={"console": ConsoleChannel(),
        "file": FileChannel(root / "data" / "processed" / "alerts.jsonl")},
        history_path=root / "data" / "processed" / "alert_history.jsonl")
    alert = {"source": dataset, "incident_key": f"{run_id}:{dataset}", "severity": severity,
        "event_type": "pipeline_summary", "flagged_count": flagged_total,
        "dry_run": True, "run_id": run_id}
    event = manager.process(alert)
    audit = audit_log.append(event_type="pipeline_alert_dry_run", actor="system", source=dataset,
        record_refs=[], details={"severity": severity, "flagged_count": flagged_total, "status": event["status"]})
    repository.add(AuditEventRow(id=str(uuid4()), event_type="pipeline_alert_dry_run", actor="system",
        dataset_version_id=dataset_version_id, source=dataset, occurred_at=audit.occurred_at, previous_hash=audit.previous_hash,
        event_hash=audit.event_hash,
        payload={"severity": severity, "flagged_count": flagged_total, "status": event["status"],
                 "dry_run": True, "record_refs": audit.record_refs, "details": audit.details}))
    return event


def run_dataset(dataset: str, root: Path | str, repository: Repository, *, archive: Path | None = None,
                settings: Any | None = None, run_id: str | None = None) -> dict[str, Any]:
    """Execute one dataset through every stage; source datasets never cross-join."""
    root = Path(root)
    settings = settings or load_settings()
    run_id = run_id or str(uuid4())
    source_path = archive or _find_source(dataset, root)
    source_hash = _digest(source_path)
    now = datetime.now(timezone.utc)
    version = repository.dataset_version(dataset, source_path.name, source_hash,
        {"id": str(uuid4()), "dataset": dataset, "source": source_path.name,
         "source_hash": source_hash, "observed_at": now, "license_status": "UNKNOWN",
         "transform_steps": ["read ZIP in memory", "validate and quarantine", "build source-specific features"]})

    audit_file = root / settings.audit.log_path
    audit_log = AuditLog(audit_file)
    _sync_audit_events(audit_log, repository)
    rules_snapshot = {"validation": settings.validation.model_dump(),
                      "anomaly": settings.anomaly.model_dump(),
                      "delay_prediction": settings.delay_prediction.model_dump(),
                      "risk": settings.risk.model_dump(), "pipeline": settings.pipeline.model_dump()}
    rules_hash = hashlib.sha256(json.dumps(rules_snapshot, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    latest_rule_event = next((event for event in reversed(audit_log.read_all())
                              if event.event_type == "rule_configuration_versioned" and event.source == dataset), None)
    if latest_rule_event is None or latest_rule_event.details.get("config_hash") != rules_hash:
        rule_event = audit_log.append(event_type="rule_configuration_versioned", actor="system", source=dataset,
            record_refs=[version.id], details={"config_hash": rules_hash, "config": rules_snapshot})
        repository.add(AuditEventRow(id=str(uuid4()), dataset_version_id=version.id,
            event_type=rule_event.event_type, actor=rule_event.actor, source=rule_event.source,
            occurred_at=rule_event.occurred_at, previous_hash=rule_event.previous_hash,
            event_hash=rule_event.event_hash, payload={"record_refs": rule_event.record_refs,
                                                       "details": rule_event.details}))
    adapter = get_adapter(dataset, root / "config" / "profiles")
    loaded = list(adapter.read_chunks(source_path, chunksize=settings.data.csv_chunk_rows))
    frame_inputs: list[tuple[str, pd.DataFrame]] = []
    quality_reports = []
    input_rows = quarantined_rows = 0
    for chunk_index, (member, frame) in enumerate(loaded):
        valid, quarantined, quality = _quality(dataset, member, frame, version.id, repository, settings,
            root=root, source_hash=source_hash, chunk_index=chunk_index,
            snapshot_member=f"{member}#chunk-{chunk_index}")
        input_rows += len(frame)
        quarantined_rows += int(quality["quality"]["quarantined_rows"])
        quality_reports.append(quality)
        if not valid.empty:
            frame_inputs.append((member, valid))

    feature_groups = build_feature_groups(dataset, frame_inputs, settings)
    feature_rows = sum(len(group["frame"]) for group in feature_groups)
    anomaly_items, detector_counts = _detect(feature_groups, settings)
    total_flags = len(anomaly_items)
    cap = settings.pipeline.max_persisted_anomalies_per_dataset
    anomaly_items = anomaly_items[:cap]
    for item in anomaly_items:
        repository.add(AnomalyRow(id=str(uuid4()), dataset_version_id=version.id, source=dataset,
            detector=item["detector"], record_ref=item["record_ref"], feature=item["feature"],
            observed_value=item["observed_value"], baseline=item["baseline"], payload=item))

    prediction_map, prediction_count = _predict(dataset, feature_groups, root, version.id, repository, settings)
    # Record model and prediction changes separately from the aggregate run summary.
    for model in repository.list_rows(ModelVersionRow, limit=100000):
        if model.dataset_version_id == version.id:
            event = audit_log.append(event_type="model_version_registered", actor="system", source=dataset,
                record_refs=[model.id], details={"name": model.name, "version": model.version,
                    "artifact_hash": model.artifact_hash, "training_data_version": model.training_data_version})
            repository.add(AuditEventRow(id=str(uuid4()), event_type=event.event_type, actor=event.actor,
                source=event.source, occurred_at=event.occurred_at, previous_hash=event.previous_hash,
                event_hash=event.event_hash, payload={"record_refs": event.record_refs, "details": event.details}))
    for prediction in repository.list_rows(PredictionRow, limit=100000):
        if prediction.dataset_version_id == version.id:
            event = audit_log.append(event_type="prediction_created", actor="system", source=dataset,
                record_refs=[prediction.id, *prediction.record_refs], details={"model_version_id": prediction.model_version_id,
                    "target": prediction.target, "predicted_at": prediction.predicted_at.isoformat()})
            repository.add(AuditEventRow(id=str(uuid4()), event_type=event.event_type, actor=event.actor,
                source=event.source, occurred_at=event.occurred_at, previous_hash=event.previous_hash,
                event_hash=event.event_hash, payload={"record_refs": event.record_refs, "details": event.details}))
    investigations = recommendations_count = 0
    investigated_refs: set[str] = set()
    limit = settings.pipeline.max_investigations_per_dataset
    for item in anomaly_items:
        if item["record_ref"] in investigated_refs or investigations >= limit:
            continue
        investigated_refs.add(item["record_ref"])
        prediction = prediction_map.get(item["record_ref"])
        incident_id, evidence_id, hypothesis_id = _persist_investigation(
            dataset, item, version.id, prediction, root, repository)
        factors = prioritize(delay_probability=(prediction or {}).get("value"), probability_calibrated=False,
            affected_order_count=1, supplier_exposure=0, evidence_strength=None,
            evidence_age_hours=None, recurrence_count=1, missing_data_fraction=1.0)
        recs = recommend(evidence_refs=[evidence_id], monitoring_recurrence=1,
                         shipment_status_known=dataset != "olist")
        for recommendation in recs:
            recommendation_id = str(uuid4())
            payload = {**recommendation, "priority_breakdown": factors,
                       "hypothesis_ref": hypothesis_id, "dry_run": True}
            repository.add(RecommendationRow(id=recommendation_id, incident_id=incident_id,
                hypothesis_id=hypothesis_id, source=dataset, action=recommendation["action"], payload=payload))
            recommendations_count += 1
        investigations += 1

    for incident in repository.list_rows(IncidentRow, limit=100000):
        if incident.dataset_version_id == version.id:
            event = audit_log.append(event_type="investigation_assembled", actor="system", source=dataset,
                record_refs=[incident.id], details={"title": incident.title,
                    "prediction_id": incident.prediction_id, "occurred_at": incident.occurred_at.isoformat()})
            repository.add(AuditEventRow(id=str(uuid4()), event_type=event.event_type, actor=event.actor,
                source=event.source, occurred_at=event.occurred_at, previous_hash=event.previous_hash,
                event_hash=event.event_hash, payload={"record_refs": event.record_refs, "details": event.details}))

    alert = _route_alert(dataset, version.id, total_flags, run_id, root, repository, audit_log, settings)
    result = {"run_id": run_id, "dataset": dataset, "source_hash": source_hash,
        "dataset_version_id": version.id,
        "stages": {"ingest": "complete", "validate": "complete", "features": "complete",
                   "detect": "complete", "predict": "complete" if prediction_count else "no_eligible_prediction_rows",
                   "investigate": "complete", "prioritize": "complete", "recommend": "complete",
                   "alert": alert["status"], "persist": "complete"},
        "counts": {"input_rows": input_rows, "quarantined_rows": quarantined_rows,
            "feature_rows": feature_rows, "anomaly_flags_by_detector": detector_counts,
            "anomaly_records_persisted": len(anomaly_items), "anomaly_flags_total": total_flags,
            "predictions_persisted": prediction_count, "incidents_investigated": investigations,
            "recommendations_persisted": recommendations_count},
        "limits": {"persisted_anomaly_cap": cap, "investigation_cap": limit,
                   "prediction_cap": settings.pipeline.max_predictions_per_dataset,
                   "quality_reports": quality_reports, "license_status": "UNKNOWN"}}
    audit = audit_log.append(event_type="pipeline_run_completed", actor="system", source=dataset,
        record_refs=[version.id], details={"run_id": run_id, "counts": result["counts"],
                                         "stages": result["stages"]})
    repository.add(AuditEventRow(id=str(uuid4()), event_type="pipeline_run_completed", actor="system",
        dataset_version_id=version.id, source=dataset, occurred_at=audit.occurred_at,
        previous_hash=audit.previous_hash, event_hash=audit.event_hash,
        payload={"run_id": run_id, "counts": result["counts"], "stages": result["stages"],
                 "record_refs": audit.record_refs, "details": audit.details}))
    return result


def run_all(root: Path | str, *, datasets: list[str] | None = None,
            database_url: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    settings = load_settings()
    url = database_url or settings.storage.url
    repository = Repository(url, company_id="local")
    run_id = str(uuid4())
    outputs = {}
    for dataset in datasets or ["olist", "dataco", "online_retail_ii"]:
        try:
            outputs[dataset] = run_dataset(dataset, root, repository, settings=settings, run_id=run_id)
        except Exception as exc:
            outputs[dataset] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
    generate_daily_summary(repository, root / "docs" / "DAILY_SUMMARY.md")
    report = {"run_id": run_id, "database_url": url, "datasets": outputs,
              "daily_summary": str(root / "docs" / "DAILY_SUMMARY.md"), "stored_counts": repository.counts()}
    report_path = root / "data" / "processed" / "pipeline_runs" / f"{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def generate_daily_summary(repository: Repository, output: Path | str,
                           *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    end = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=1)
    summary = repository.daily_summary(start, end)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text("# Daily pipeline summary\n\nCounts are computed from persisted SQLite rows. The audit count includes the append-only JSONL history imported into SQLite; per-run JSON under `data/processed/pipeline_runs/` distinguishes current executions.\n\n```json\n" +
        json.dumps(summary, indent=2) + "\n```\n", encoding="utf-8")
    return summary


def run_with_retries(root: Path | str, *, datasets: list[str] | None = None,
                     database_url: str | None = None, sleep=time.sleep) -> dict[str, Any]:
    settings = load_settings()
    attempts = settings.pipeline.retry_attempts
    pending = list(datasets or ["olist", "dataco", "online_retail_ii"])
    completed: dict[str, Any] = {}
    last_report: dict[str, Any] = {}
    for attempt in range(attempts):
        last_report = run_all(root, datasets=pending, database_url=database_url)
        completed.update(last_report.get("datasets", {}))
        pending = [dataset for dataset, result in last_report.get("datasets", {}).items()
                   if result.get("status") == "FAILED"]
        if not pending:
            last_report["datasets"] = completed
            last_report["retry_attempts_used"] = attempt + 1
            return last_report
        if attempt + 1 < attempts:
            sleep(settings.pipeline.retry_backoff_seconds * (2 ** attempt))
    errors = {dataset: completed[dataset].get("error") for dataset in pending}
    raise RuntimeError(f"Pipeline failed after {attempts} configured attempts: {errors}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--database-url")
    parser.add_argument("--dataset", action="append", choices=["olist", "dataco", "online_retail_ii"])
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--interval-seconds", type=float, help="Run repeatedly at this configured interval")
    args = parser.parse_args()
    while True:
        report = (run_with_retries if args.retry else run_all)(args.root,
            datasets=args.dataset, database_url=args.database_url)
        print(json.dumps(report, indent=2, default=str))
        if args.interval_seconds is None:
            break
        time.sleep(max(args.interval_seconds, 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
