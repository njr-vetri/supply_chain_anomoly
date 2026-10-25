"""Synthetic tests for Stage 7 drift monitoring, outcome evaluations, governance, and audit."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (
    ActionRow, AuditEventRow, DataSourceRow, DatasetVersionRow,
    IncidentRow, ModelVersionRow, OutcomeRow, PredictionRow, ProjectRow,
    RecommendationRow, Repository, WorkspaceRow,
)
from src.ml.delay.evaluation import evaluate_classification
from src.ml.registry import compare_candidate, promote_candidate, rollback_model, set_initial_current
from src.monitoring.drift import compare_profiles, profile_frame
from src.monitoring.outcomes import (
    evaluate_forecast_outcomes,
    evaluate_prediction_outcomes, evaluate_verified_alerts,
)


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-company-stage7", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "synthetic-viewer": "viewer",
        "synthetic-analyst": "analyst",
        "synthetic-reviewer": "reviewer",
        "synthetic-admin": "admin",
    }))
    app = api_main.create_app(repo)
    return TestClient(app), repo


def _headers(role="analyst", company_id="synthetic-company-stage7"):
    return {"X-API-Key": f"synthetic-{role}", "X-Company-Id": company_id}


def test_schema_change_and_drift_never_trigger_automatic_retrain():
    baseline = profile_frame(pd.DataFrame({
        "supplier_id": ["s1", "s2", "s1", "s2"],
        "order_qty": [10.0, 20.0, 15.0, 25.0],
        "status": ["delivered", "delivered", "delivered", "delivered"],
    }))
    current = profile_frame(pd.DataFrame({
        "supplier_id": ["s1", "s2", "s1", "s2"],
        "order_qty": [100.0, 200.0, 150.0, 250.0],
        "status": [1, 2, 3, 4],  # retyped
        "new_promo_col": ["yes", "no", "yes", "no"],  # added
    }))
    result = compare_profiles(baseline, current, max_numeric_mean_shift=1.0)
    assert result["status"] == "DRIFT_ALERT"
    assert "new_promo_col" in result["schema"]["added_columns"]
    assert "schema_changed" in result["alerts"]
    assert "numeric_feature_drift:order_qty" in result["alerts"]
    assert result["drift_is_warning_only"] is True
    assert result["triggers_automatic_retrain"] is False
    assert "warning" in result
    assert "never an automatic retrain trigger" in result["warning"]


def test_forecast_and_prediction_outcome_evaluations_fallback_when_unverified():
    unverified_outcomes = [
        {"action_id": "synthetic-act-1", "facts": {}, "comparisons": []},
        {"action_id": "synthetic-act-2", "facts": {"delay": None}, "comparisons": []},
    ]
    forecast_eval = evaluate_forecast_outcomes(unverified_outcomes)
    assert forecast_eval["status"] == "INSUFFICIENT_VERIFIED_OUTCOMES"
    assert forecast_eval["message"] == "not enough verified outcomes"
    assert forecast_eval["count"] == 0
    assert forecast_eval["mae"] is None

    prediction_eval = evaluate_prediction_outcomes(unverified_outcomes)
    assert prediction_eval["status"] == "INSUFFICIENT_VERIFIED_OUTCOMES"
    assert prediction_eval["message"] == "not enough verified outcomes"
    assert prediction_eval["count"] == 0
    assert prediction_eval["accuracy"] is None

    alerts_eval = evaluate_verified_alerts(unverified_outcomes)
    assert alerts_eval["status"] == "INSUFFICIENT_VERIFIED_LABELS"
    assert alerts_eval["message"] == "not enough verified outcomes"
    assert alerts_eval["alert_precision"] is None


def test_outcome_evaluations_with_verified_forecasts_and_predictions():
    verified_outcomes = [
        {
            "action_id": "synthetic-act-1",
            "facts": {"demand": 100.0, "delay": 1},
            "comparisons": [
                {
                    "type": "FORECAST",
                    "reference_id": "synthetic-pred-demand-1",
                    "prediction_value": 90.0,
                    "observed_value": 100.0,
                    "comparable": True,
                },
                {
                    "type": "PREDICTION",
                    "reference_id": "synthetic-pred-delay-1",
                    "prediction_value": 0.8,
                    "observed_value": 1,
                    "comparable": True,
                },
            ],
            "verified_alert_label": True,
            "alert_was_raised": True,
            "verified_by": "synthetic-reviewer",
        },
        {
            "action_id": "synthetic-act-2",
            "facts": {"demand": 200.0, "delay": 0},
            "comparisons": [
                {
                    "type": "FORECAST",
                    "reference_id": "synthetic-pred-demand-2",
                    "prediction_value": 220.0,
                    "observed_value": 200.0,
                    "comparable": True,
                },
                {
                    "type": "PREDICTION",
                    "reference_id": "synthetic-pred-delay-2",
                    "prediction_value": 0.2,
                    "observed_value": 0,
                    "comparable": True,
                },
            ],
            "verified_alert_label": False,
            "alert_was_raised": False,
            "verified_by": "synthetic-reviewer",
        },
    ]

    forecast_eval = evaluate_forecast_outcomes(verified_outcomes)
    assert forecast_eval["status"] == "COMPUTED_FROM_VERIFIED_OUTCOMES"
    assert forecast_eval["count"] == 2
    assert forecast_eval["mae"] == 15.0
    assert pytest.approx(forecast_eval["mape"], 0.001) == 0.10

    prediction_eval = evaluate_prediction_outcomes(verified_outcomes)
    assert prediction_eval["status"] == "COMPUTED_FROM_VERIFIED_OUTCOMES"
    assert prediction_eval["count"] == 2
    assert prediction_eval["accuracy"] == 1.0
    assert prediction_eval["precision"] == 1.0
    assert prediction_eval["recall"] == 1.0

    alert_eval = evaluate_verified_alerts(verified_outcomes)
    assert alert_eval["status"] == "COMPUTED_FROM_VERIFIED_LABELS"
    assert alert_eval["alert_precision"] == 1.0
    assert alert_eval["missed_events"] == 0


def test_reproducible_evaluation_report_contains_required_fields(tmp_path):
    frame = pd.DataFrame({
        "event_time": pd.date_range("2026-01-01", periods=60, freq="D"),
        "signal": [i % 2 for i in range(60)],
        "group": ["synthetic-grp" for _ in range(60)],
        "label": [i % 2 for i in range(60)],
    })
    config = {
        "train_fraction": 0.6,
        "validation_fraction": 0.2,
        "random_seed": 1234,
        "tree_max_depth": 2,
        "random_forest_estimators": 3,
        "mapping_version": "v2",
        "data_version": "synthetic-data-version-abc",
    }
    models_dir = tmp_path / "models"
    registry_file = tmp_path / "registry.json"
    result = evaluate_classification(
        "synthetic_delay",
        frame,
        label="label",
        timestamp="event_time",
        features=["signal"],
        subgroup="group",
        archive_hash="synthetic-archive-hash-xyz",
        config=config,
        models_dir=models_dir,
        registry_path=registry_file,
    )
    assert result["models"]
    for version in ("synthetic_delay-logistic_regression-v1", "synthetic_delay-decision_tree-v1"):
        report_path = models_dir / "evaluations" / f"{version}.json"
        assert report_path.exists()
        content = json.loads(report_path.read_text(encoding="utf-8"))
        assert content["model_version"] == version
        assert content["data_version"] == "synthetic-data-version-abc"
        assert content["mapping_version"] == "v2"
        assert content["seed"] == 1234
        assert "metrics" in content
        assert "limitations" in content
        assert "Evaluation describes this chronological holdout only." in content["limitations"]


def test_model_and_config_governance_lifecycle(tmp_path):
    reg_path = tmp_path / "model_registry.json"
    ctx = {"method": "chronological", "test_data_hash": "synthetic-holdout-123", "test_rows": 20}
    m1 = {
        "dataset": "synthetic",
        "name": "classifier",
        "version": "synthetic-v1",
        "evaluation_context": ctx,
        "metrics": {"test": {"macro_f1": 0.70, "brier_score": 0.15}},
        "lifecycle": "CANDIDATE",
    }
    m2 = {
        "dataset": "synthetic",
        "name": "classifier",
        "version": "synthetic-v2",
        "evaluation_context": ctx,
        "metrics": {"test": {"macro_f1": 0.78, "brier_score": 0.14}},
        "lifecycle": "CANDIDATE",
    }
    reg_path.write_text(json.dumps({"models": [m1, m2], "current_model_versions": {}, "promotion_history": []}))

    # 1. Initial current model requires explicit human reviewer approval
    with pytest.raises(ValueError, match="Reviewer"):
        set_initial_current(reg_path, "synthetic-v1", reviewer="", reason="synthetic")
    initial_res = set_initial_current(reg_path, "synthetic-v1", reviewer="synthetic-lead", reason="initial baseline approval")
    assert initial_res["status"] == "CURRENT"

    # 2. Candidate comparison
    criteria = {"primary_metric": "macro_f1", "minimum_improvement": 0.05, "maximum_brier_increase": 0.02}
    comp = compare_candidate(reg_path, "synthetic-v2", acceptance=criteria)
    assert comp["status"] == "ACCEPTANCE_MET"
    assert comp["candidate_value"] == 0.78
    assert comp["current_value"] == 0.70

    # 3. Promote candidate requires reviewer and reason
    with pytest.raises(ValueError, match="Reviewer"):
        promote_candidate(reg_path, "synthetic-v2", acceptance=criteria, reviewer="", reason="")
    promoted = promote_candidate(reg_path, "synthetic-v2", acceptance=criteria, reviewer="synthetic-lead", reason="performance improved on holdout")
    assert promoted["status"] == "PROMOTED"

    # 4. Rollback to superseded
    rollback_res = rollback_model(reg_path, "synthetic:classifier", reviewer="synthetic-lead", reason="operational rollback")
    assert rollback_res["status"] == "ROLLED_BACK"
    assert rollback_res["to_version"] == "synthetic-v1"


def test_api_outcomes_drift_and_audit_filters(api_client, tmp_path, monkeypatch):
    client, repo = api_client
    now = datetime.now(timezone.utc)

    # 1. Audit events across all 8 domains
    audit_categories = [
        ("data_source_registered", "source"),
        ("dataset_drift_checked", "source"),
        ("mapping_accepted", "mapping"),
        ("risk_scoring_config_promoted", "rule"),
        ("model_version_registered", "model"),
        ("permission_policy_changed", "permission"),
        ("predictions_recorded", "prediction"),
        ("incident_assembled", "investigation"),
        ("action_dry_run_recorded", "action"),
    ]
    for event_type, _cat in audit_categories:
        repo.add(AuditEventRow(
            id=f"audit-{event_type}",
            event_type=event_type,
            actor="synthetic-test",
            occurred_at=now,
            previous_hash="000000",
            event_hash=f"hash-{event_type}",
            payload={"record_refs": ["ref-1"], "details": {"test": True}},
        ))

    # Test audit filtering by category
    res_source = client.get("/api/v1/audit?category=source", headers=_headers("admin"))
    assert res_source.status_code == 200
    assert all(item["event_type"] in ("data_source_registered", "dataset_drift_checked") for item in res_source.json()["items"])

    res_model = client.get("/api/v1/audit?category=model", headers=_headers("admin"))
    assert res_model.status_code == 200
    assert res_model.json()["items"][0]["event_type"] == "model_version_registered"

    res_action = client.get("/api/v1/audit?category=action", headers=_headers("admin"))
    assert res_action.status_code == 200
    assert res_action.json()["items"][0]["event_type"] == "action_dry_run_recorded"

    # 2. Test outcomes evaluation endpoint
    eval_resp = client.get("/api/v1/evaluation/outcomes", headers=_headers("viewer"))
    assert eval_resp.status_code == 200
    body = eval_resp.json()
    assert body["status"] == "EVALUATION_REPORT"
    assert body["forecast_vs_actual"]["message"] == "not enough verified outcomes"
    assert body["prediction_vs_outcome"]["message"] == "not enough verified outcomes"
    assert body["alerts"]["message"] == "not enough verified outcomes"

    # Add verified outcomes and test evaluation response
    repo.add(WorkspaceRow(id="ws-stage7", name="Synthetic Workspace"))
    repo.add(ProjectRow(id="p-1", workspace_id="ws-stage7", name="Synthetic Project"))
    repo.add(DataSourceRow(id="ds-synthetic", project_id="p-1", name="synthetic_feed", source_type="csv", location_ref="synthetic"))
    repo.add(DatasetVersionRow(
        id="d-1", dataset="synthetic_feed", source="synthetic_feed",
        source_hash="hash-1", observed_at=now, payload={"profile": {"row_count": 10, "columns": {}}}
    ))
    repo.add(ModelVersionRow(id="m-1", name="synthetic-model", version="v1", artifact_hash="art-hash", training_data_version="d-1"))
    repo.add(IncidentRow(id="inc-1", dataset_version_id="d-1", source="synthetic", title="Synthetic Incident", occurred_at=now))
    repo.add(RecommendationRow(id="rec-1", incident_id="inc-1", source="synthetic", action="MONITOR"))
    repo.add(ActionRow(id="act-1", recommendation_id="rec-1", source="synthetic", status="DRY_RUN", payload={}))
    repo.add(PredictionRow(
        id="pred-1", dataset_version_id="d-1", model_version_id="m-1",
        source="synthetic", predicted_at=now, target="demand", value=150.0, record_refs=[]
    ))
    repo.add(OutcomeRow(
        id="out-1",
        action_id="act-1",
        prediction_id="pred-1",
        source="synthetic",
        observed_at=now,
        payload={
            "facts": {"demand": 140.0},
            "comparisons": [{
                "type": "FORECAST",
                "reference_id": "pred-1",
                "prediction_value": 150.0,
                "observed_value": 140.0,
                "comparable": True,
            }],
            "verified_alert_label": True,
            "alert_was_raised": True,
            "verified_by": "synthetic-reviewer",
        },
    ))
    eval_resp2 = client.get("/api/v1/evaluation/outcomes", headers=_headers("viewer"))
    assert eval_resp2.status_code == 200
    body2 = eval_resp2.json()
    assert body2["forecast_vs_actual"]["status"] == "COMPUTED_FROM_VERIFIED_OUTCOMES"
    assert body2["forecast_vs_actual"]["mae"] == 10.0
    assert body2["alerts"]["status"] == "COMPUTED_FROM_VERIFIED_LABELS"
    assert body2["alerts"]["alert_precision"] == 1.0

    # 3. Test dataset drift endpoint
    drift_resp1 = client.get("/api/v1/datasets/synthetic_feed/drift", headers=_headers("reviewer"))
    assert drift_resp1.status_code == 200
    assert drift_resp1.json()["status"] == "NO_PRIOR_VERSION"

    repo.add(DatasetVersionRow(
        id="dv-2", dataset="synthetic_feed", source="synthetic_feed",
        source_hash="hash-2", observed_at=now,
        payload={"drift": {
            "status": "DRIFT_ALERT",
            "alerts": ["schema_changed"],
            "schema": {"added_columns": ["new_col"], "removed_columns": [], "type_changes": {}},
            "drift_is_warning_only": True,
            "triggers_automatic_retrain": False,
        }}
    ))
    drift_resp2 = client.get("/api/v1/datasets/synthetic_feed/drift", headers=_headers("reviewer"))
    assert drift_resp2.status_code == 200
    assert drift_resp2.json()["status"] == "DRIFT_ALERT"
    assert drift_resp2.json()["schema"]["added_columns"] == ["new_col"]
    assert drift_resp2.json()["triggers_automatic_retrain"] is False

    # 4. Test reproducible model evaluation report endpoint
    models_dir = Path("models/evaluations")
    models_dir.mkdir(parents=True, exist_ok=True)
    report_file = models_dir / "synthetic-model-v99.json"
    report_file.write_text(json.dumps({
        "model_version": "synthetic-model-v99",
        "data_version": "synthetic-v1",
        "mapping_version": "v1",
        "seed": 42,
        "metrics": {"test": {"macro_f1": 0.85}},
        "limitations": ["Chronological holdout only."],
    }), encoding="utf-8")
    report_resp = client.get("/api/v1/models/synthetic-model-v99/evaluation-report", headers=_headers("viewer"))
    assert report_resp.status_code == 200
    assert report_resp.json()["seed"] == 42
    assert report_resp.json()["data_version"] == "synthetic-v1"
    assert report_resp.json()["mapping_version"] == "v1"


def test_api_reupload_schema_drift_detection(api_client, tmp_path):
    client, repo = api_client
    # 1. First upload
    csv1 = "order_id,quantity\nsynthetic-1,10\nsynthetic-2,20\n"
    res1 = client.post(
        "/api/v1/datasets/upload",
        headers=_headers("reviewer"),
        data={"dataset_name": "reupload_feed"},
        files={"file": ("reupload_feed_v1.csv", csv1.encode("utf-8"), "text/csv")},
    )
    assert res1.status_code == 201
    job1_id = res1.json()["import_job_id"]
    source1_id = res1.json()["source_id"]
    version1_id = res1.json()["dataset_version_id"]

    # Execute profiling for first upload synchronously
    source1 = repo.get(DataSourceRow, source1_id)
    api_main._profile_import_job(repo, job1_id, source1_id, version1_id, source1.location_ref, "reupload_feed_v1.csv", "reupload_feed")

    drift_init = client.get("/api/v1/datasets/reupload_feed/drift", headers=_headers("reviewer"))
    assert drift_init.status_code == 200
    assert drift_init.json()["status"] == "NO_PRIOR_VERSION"

    # 2. Second upload with modified schema (added column 'region', removed 'quantity', added 'amount')
    csv2 = "order_id,amount,region\nsynthetic-1,100,north\nsynthetic-2,200,south\n"
    res2 = client.post(
        "/api/v1/datasets/upload",
        headers=_headers("reviewer"),
        data={"dataset_name": "reupload_feed"},
        files={"file": ("reupload_feed_v2.csv", csv2.encode("utf-8"), "text/csv")},
    )
    assert res2.status_code == 201
    job2_id = res2.json()["import_job_id"]
    source2_id = res2.json()["source_id"]
    version2_id = res2.json()["dataset_version_id"]

    source2 = repo.get(DataSourceRow, source2_id)
    api_main._profile_import_job(repo, job2_id, source2_id, version2_id, source2.location_ref, "reupload_feed_v2.csv", "reupload_feed")

    # 3. Query drift endpoint
    drift_res = client.get("/api/v1/datasets/reupload_feed/drift", headers=_headers("reviewer"))
    assert drift_res.status_code == 200
    drift_data = drift_res.json()
    assert drift_data["status"] == "DRIFT_ALERT"
    assert "amount" in drift_data["schema"]["added_columns"]
    assert "region" in drift_data["schema"]["added_columns"]
    assert "quantity" in drift_data["schema"]["removed_columns"]
    assert drift_data["drift_is_warning_only"] is True
    assert drift_data["triggers_automatic_retrain"] is False
    assert "Drift is a warning, never an automatic retrain trigger." in drift_data["warning"]
