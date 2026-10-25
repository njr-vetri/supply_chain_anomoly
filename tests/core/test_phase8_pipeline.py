"""Phase 8 integration fixtures are synthetic and do not represent performance."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone

import pandas as pd
import pytest

sqlalchemy = pytest.importorskip("sqlalchemy", reason="SQLAlchemy is a Phase 8 dependency")


class SyntheticProbabilityModel:
    """Deterministic estimator used only by the labelled synthetic integration fixture."""
    def predict_proba(self, frame):
        import numpy as np
        probability = np.full(len(frame), 0.25)
        return np.column_stack([1 - probability, probability])

from src.core.config import load_settings
from src.core import pipeline as pipeline_module
from src.core.pipeline import _quality, generate_daily_summary, run_dataset
from src.core.repository import (AuditEventRow, Base, DatasetVersionRow, EvidenceRow,
                                 Repository)
from src.core.pipeline import _features
from src.data.validation import validate_frame


def test_sqlite_repository_enforces_foreign_keys_and_daily_summary(tmp_path):
    repo = Repository("sqlite:///:memory:", company_id="synthetic-company")
    assert set(Base.metadata.tables) >= {
        "dataset_versions", "model_versions", "predictions", "anomalies", "incidents", "evidence",
        "hypotheses", "recommendations", "approvals", "actions", "outcomes", "audit_events",
    }
    assert any(fk.target_fullname == "dataset_versions.id"
               for fk in Base.metadata.tables["audit_events"].foreign_keys)
    from sqlalchemy import inspect
    assert any(fk["referred_table"] == "dataset_versions"
               for fk in inspect(repo.engine).get_foreign_keys("audit_events"))
    row = DatasetVersionRow(id="synthetic-version", dataset="synthetic", source="synthetic.zip",
        source_hash="synthetic-hash", observed_at=datetime.now(timezone.utc), license_status="UNKNOWN", payload={})
    repo.add(row)
    with pytest.raises(Exception):
        repo.add(EvidenceRow(id="synthetic-orphan", dataset_version_id="missing", incident_id="missing",
            source="synthetic", observed_at=datetime.now(timezone.utc), record_refs=[], payload={}))
    report = generate_daily_summary(repo, tmp_path / "DAILY_SUMMARY.md")
    assert report["total_rows_stored"]["dataset_versions"] == 1
    assert report["rows_created_today"]["dataset_versions"] == 1
    assert (tmp_path / "DAILY_SUMMARY.md").is_file()


def test_full_synthetic_olist_pipeline_runs_and_persists(tmp_path):
    orders = pd.DataFrame({
        "order_id": [f"synthetic-order-{i}" for i in range(4)],
        "order_status": ["delivered"] * 4,
        "order_purchase_timestamp": [f"2018-01-0{i + 1} 00:00:00" for i in range(4)],
        "order_estimated_delivery_date": [f"2018-01-0{i + 3} 00:00:00" for i in range(4)],
        "order_delivered_customer_date": [f"2018-01-0{i + 5} 00:00:00" for i in range(4)],
    })
    items = pd.DataFrame({"order_id": orders["order_id"], "order_item_id": [1] * 4,
                          "seller_id": ["synthetic-seller"] * 4})
    archive_path = tmp_path / "synthetic_olist.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("olist_orders_dataset.csv", orders.to_csv(index=False))
        archive.writestr("olist_order_items_dataset.csv", items.to_csv(index=False))
    import joblib
    artifact = tmp_path / "models" / "olist_delay-logistic_regression-v1.joblib"
    artifact.parent.mkdir(parents=True)
    joblib.dump(SyntheticProbabilityModel(), artifact)
    registry = tmp_path / "src" / "ml" / "model_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"models": [{
        "dataset": "olist_delay", "name": "logistic_regression",
        "artifact": "models/olist_delay-logistic_regression-v1.joblib",
        "registered_at": "2020-01-01T00:00:00+00:00",
    }]}), encoding="utf-8")

    settings = load_settings()
    settings.pipeline.feature_thresholds["olist_delivery_deviation_days"] = 0.5
    settings.pipeline.enable_isolation_forest = False
    settings.pipeline.max_investigations_per_dataset = 2
    repo = Repository("sqlite:///:memory:", company_id="synthetic-company")
    result = run_dataset("olist", tmp_path, repo, archive=archive_path, settings=settings,
                         run_id="synthetic-run")

    assert result["stages"]["ingest"] == "complete"
    assert result["stages"]["validate"] == "complete"
    assert result["stages"]["features"] == "complete"
    assert result["stages"]["detect"] == "complete"
    assert result["stages"]["predict"] == "complete"
    assert result["stages"]["investigate"] == "complete"
    assert result["stages"]["prioritize"] == "complete"
    assert result["stages"]["recommend"] == "complete"
    assert result["stages"]["alert"] == "ROUTED"
    assert result["stages"]["persist"] == "complete"
    assert result["counts"]["input_rows"] == 8
    assert result["counts"]["anomaly_flags_total"] > 0
    assert result["counts"]["predictions_persisted"] == 2
    assert result["counts"]["incidents_investigated"] == 2
    counts = repo.counts()
    assert counts["dataset_versions"] == 1
    assert counts["model_versions"] == 1
    assert counts["predictions"] == 2
    assert counts["anomalies"] > 0
    assert counts["incidents"] == 2
    assert counts["evidence"] == 2
    assert counts["hypotheses"] == 2
    assert counts["recommendations"] > 0
    with repo.sessions() as session:
        events = session.query(AuditEventRow).order_by(AuditEventRow.created_at).all()
        types = {event.event_type for event in events}
        assert {"rule_configuration_versioned", "model_version_registered", "prediction_created",
                "investigation_assembled", "pipeline_run_completed"}.issubset(types)
    from src.core.audit import AuditLog
    assert AuditLog(tmp_path / settings.audit.log_path).verify()


def test_validation_quarantines_rows_when_required_schema_is_missing():
    valid, quarantine, report = validate_frame(pd.DataFrame({"synthetic_id": ["a", "b"]}),
        source="synthetic", required_columns=["missing_column"])
    assert len(valid) == 0
    assert len(quarantine) == 2
    assert report.schema_errors == ["Missing required column: missing_column"]


def test_pipeline_quarantine_manifest_omits_row_contents(tmp_path):
    repo = Repository("sqlite:///:memory:", company_id="synthetic-company")
    version = DatasetVersionRow(id="synthetic-dataset-version", dataset="olist", source="synthetic.zip",
        source_hash="synthetic-hash", observed_at=datetime.now(timezone.utc), license_status="UNKNOWN", payload={})
    repo.add(version)
    frame = pd.DataFrame({"order_id": ["synthetic-private-value"],
                          "order_purchase_timestamp": ["invalid synthetic date"]})
    settings = load_settings()
    _, quarantined, report = _quality("olist", "olist_orders_dataset.csv", frame, version.id,
        repo, settings, root=tmp_path, source_hash="synthetic-hash", chunk_index=0)
    assert len(quarantined) == 1
    target = tmp_path / report["quarantine_manifest"]
    manifest = target.read_text(encoding="utf-8")
    assert '"row_offset": 0' in manifest
    assert "date:order_purchase_timestamp" in manifest
    assert "synthetic-private-value" not in manifest


def test_dataco_feature_builder_receives_all_synthetic_chunks():
    settings = load_settings()
    columns = {
        "Days for shipment (scheduled)": [2], "Shipping Mode": ["synthetic"],
        "order date (DateOrders)": ["2020-01-01"], "Order Region": ["synthetic"],
        "Days for shipping (real)": [1], "Late_delivery_risk": [0], "Order Item Id": [1],
    }
    first = pd.DataFrame(columns)
    second = pd.DataFrame({key: [value[0]] for key, value in columns.items()})
    group = _features("dataco", [("datacosupplychaindataset.csv", first),
                                  ("datacosupplychaindataset.csv", second)], settings)[0]
    assert len(group["frame"]) == 2


def test_scheduler_retries_only_failed_synthetic_dataset(monkeypatch, tmp_path):
    calls = []
    reports = [
        {"datasets": {"olist": {"status": "FAILED", "error": "synthetic transient"},
                      "dataco": {"stages": {"persist": "complete"}}}},
        {"datasets": {"olist": {"stages": {"persist": "complete"}}}},
    ]
    def fake_run_all(root, *, datasets, database_url):
        calls.append(list(datasets))
        return reports.pop(0)
    monkeypatch.setattr(pipeline_module, "run_all", fake_run_all)
    sleeps = []
    result = pipeline_module.run_with_retries(tmp_path, datasets=["olist", "dataco"],
        sleep=sleeps.append)
    assert calls == [["olist", "dataco"], ["olist"]]
    assert sleeps == [load_settings().pipeline.retry_backoff_seconds]
    assert result["retry_attempts_used"] == 2
    assert set(result["datasets"]) == {"olist", "dataco"}
