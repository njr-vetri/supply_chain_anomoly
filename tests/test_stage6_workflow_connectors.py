"""Synthetic tests for local workflow scheduling, alert operations and connectors."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from src.alerts.manager import AlertManager
from src.connectors.base import ConnectorHealth, RecordBatch
from src.connectors.database import DatabaseImportConnector
from src.connectors.extensions import SimulatedConnector, UNBUILT_CONNECTOR_EXTENSIONS
from src.connectors.folder import FolderImportConnector
from src.connectors.notifications import SMTPNotificationAdapter, WebhookNotificationAdapter
from src.connectors.rest import RestPollingConnector
from src.recommendations.playbooks import recommend_for_driver
from src.recommendations.whatif import compare_scenarios
from src.workflow.engine import WorkflowEngine
from src.workflow.scheduler import LocalWorkflowScheduler
from src.core.audit import AuditLog
from src.core.repository import (ActionRow, DatasetVersionRow, IncidentRow, ModelVersionRow,
                                  PredictionRow, RecommendationRow, Repository)
from src.workflow.outcomes import record_execution_verification, record_observed_outcome


class FakeChannel:
    def send(self, alert):
        pass


def test_synthetic_timer_and_new_batch_jobs_retry_and_are_idempotent(tmp_path):
    calls = []
    def runner(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("synthetic transient secret must not be logged")
        return {"status": "DRY_RUN", "batch_id": payload.get("batch_id")}

    scheduler = LocalWorkflowScheduler(runner, history_path=tmp_path / "jobs.jsonl", interval_seconds=10,
        max_attempts=2, retry_backoff_seconds=0, sleeper=lambda _delay: None)
    engine = WorkflowEngine(scheduler)
    batch = scheduler.new_batch("synthetic-batch-1", project_id="synthetic-project")
    duplicate = scheduler.new_batch("synthetic-batch-1", project_id="synthetic-project")
    assert duplicate["duplicate_suppressed"] is True
    timer = engine.timer_trigger(slot="synthetic-timer-slot")
    assert timer["trigger"] == "timer"
    results = engine.run_pending()
    assert [item["status"] for item in results] == ["COMPLETED", "COMPLETED"]
    assert results[0]["attempts"] == 2
    history = (tmp_path / "jobs.jsonl").read_text(encoding="utf-8")
    assert "synthetic transient secret" not in history
    assert engine.job(batch["id"])["status"] == "COMPLETED"
    with pytest.raises(ValueError, match="untrusted text"):
        scheduler.submit(trigger="new_batch", payload={"command": "delete"}, idempotency_key="synthetic-command")


def test_workflow_engine_accepts_and_preserves_simulated_connector_label(tmp_path):
    class Connector:
        def health_check(self):
            return ConnectorHealth("synthetic", "SIMULATED", "2025-01-01T00:00:00+00:00", "mock")
        def read_batches(self):
            yield RecordBatch("synthetic", "synthetic-source", None, [{"id": "synthetic-row"}], "SIMULATED")
    scheduler = LocalWorkflowScheduler(lambda payload: payload, history_path=tmp_path / "jobs.jsonl",
                                       retry_backoff_seconds=0, sleeper=lambda _delay: None)
    engine = WorkflowEngine(scheduler)
    jobs = engine.poll_connector(Connector(), project_id="synthetic-project")
    assert jobs[0]["payload"]["simulation_label"] == "SIMULATED"
    result = engine.run_pending()[0]
    assert result["result"]["simulation_label"] == "SIMULATED"


def test_driver_playbook_requires_available_roles_and_history_for_effect_estimate():
    driver = {"dimension": "supplier", "value": "synthetic-supplier"}
    missing = recommend_for_driver(driver=driver, available_roles={"supplier_id"}, evidence_refs=["synthetic-ref"])
    assert missing["status"] == "NEEDS_DATA"
    result = recommend_for_driver(driver=driver, available_roles={"supplier_id", "order_id"},
                                  evidence_refs=["synthetic-ref"])
    assert result["status"] == "PROPOSED"
    for field in ("rationale", "evidence_refs", "assumptions", "uncertainty", "tradeoffs",
                  "approvals", "preconditions", "status", "result"):
        assert field in result
    assert result["estimated_effect"] is None
    historical = recommend_for_driver(driver=driver, available_roles={"supplier_id", "order_id"},
        evidence_refs=["synthetic-ref"], history={"row_count": 40, "observed_effect": 0.1})
    assert historical["estimated_effect"]["label"] == "HYPOTHETICAL"
    assert "erp" in UNBUILT_CONNECTOR_EXTENSIONS and "wms" in UNBUILT_CONNECTOR_EXTENSIONS


def test_what_if_scenario_requires_assumptions_and_never_claims_savings():
    with pytest.raises(ValueError, match="explicit"):
        compare_scenarios(affected_order_count=4, calibrated_delay_probability=0.5,
            probability_calibrated=True, scenarios=[{"name": "synthetic", "assumed_relative_probability_reduction": 0.2}])
    result = compare_scenarios(affected_order_count=4, calibrated_delay_probability=0.5,
        probability_calibrated=True, scenarios=[{"name": "synthetic", "assumed_relative_probability_reduction": 0.2,
                                                  "assumptions": ["synthetic scenario assumption"]}])
    assert result["label"] == "HYPOTHETICAL"
    assert result["not_estimated"] == ["supplier capacity", "inventory", "cost savings"]


def test_alert_acknowledgement_assignment_and_history_restore(tmp_path):
    path = tmp_path / "alerts.jsonl"
    manager = AlertManager(channels={"console": FakeChannel()}, history_path=path,
        settings={"dedup_window_seconds": 60, "severity_routes": {"LOW": ["console"]}, "escalation": [], "group_by": []})
    routed = manager.process({"source": "synthetic", "incident_key": "synthetic-incident", "severity": "LOW"})
    manager.assign(routed["group_id"], actor="synthetic-analyst", assigned_to="synthetic-reviewer")
    manager.acknowledge(routed["group_id"], actor="synthetic-analyst", reason="synthetic acknowledgement")
    restored = AlertManager(channels={}, history_path=path,
        settings={"dedup_window_seconds": 60, "severity_routes": {}, "escalation": [], "group_by": []})
    state = restored.group(routed["group_id"])
    assert state["status"] == "ACKNOWLEDGED"
    assert state["assigned_to"] == "synthetic-reviewer"


def test_folder_connector_reads_without_modifying_and_emits_hash(tmp_path):
    file = tmp_path / "synthetic.csv"
    original = b"order_id,quantity\nsynthetic-order,3\n"
    file.write_bytes(original)
    batch = next(FolderImportConnector(tmp_path, chunksize=1).read_batches())
    assert batch.label == "REAL"
    assert batch.records[0]["order_id"] == "synthetic-order"
    assert batch.source_sha256 == hashlib.sha256(original).hexdigest()
    assert file.read_bytes() == original


def test_rest_connector_uses_env_token_and_fake_transport(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_REST_TOKEN", "synthetic-token")
    seen = {}
    def transport(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return b'{"items":[{"record_id":"synthetic-1"}]}'
    connector = RestPollingConnector("https://localhost/synthetic", token_env="SYNTHETIC_REST_TOKEN",
        timeout_seconds=2, transport=transport)
    batch = connector.poll()
    assert batch.label == "SIMULATED"
    assert batch.records == [{"record_id": "synthetic-1"}]
    assert seen == {"authorization": "Bearer synthetic-token", "timeout": 2}


def test_database_connector_reads_configured_sqlite_table(tmp_path, monkeypatch):
    db = tmp_path / "synthetic.sqlite"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE synthetic_orders (id TEXT, quantity INTEGER)"))
        connection.execute(text("INSERT INTO synthetic_orders VALUES ('synthetic-1', 2)"))
    engine.dispose()
    monkeypatch.setenv("SYNTHETIC_DATABASE_URL", f"sqlite:///{db}")
    connector = DatabaseImportConnector(url_env="SYNTHETIC_DATABASE_URL", table_name="synthetic_orders", chunksize=1)
    batches = list(connector.read_batches())
    assert batches[0].records == [{"id": "synthetic-1", "quantity": 2}]
    assert connector.health_check().status == "HEALTHY"
    with pytest.raises(ValueError, match="identifier"):
        DatabaseImportConnector(url_env="SYNTHETIC_DATABASE_URL", table_name="synthetic; DROP TABLE x")


def test_smtp_and_webhook_notification_connectors_use_mock_transports(monkeypatch):
    monkeypatch.setenv("CONNECTORS_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_USERNAME", "synthetic-user")
    monkeypatch.setenv("SMTP_PASSWORD", "synthetic-secret")
    monkeypatch.setenv("SMTP_FROM", "from@example.invalid")
    monkeypatch.setenv("SMTP_TO", "to@example.invalid")
    class FakeSMTP:
        def __init__(self, *args, **kwargs): self.sent = False
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def ehlo(self): pass
        def starttls(self): pass
        def login(self, *_args): pass
        def send_message(self, _message): self.sent = True
    smtp = SMTPNotificationAdapter(smtp_factory=FakeSMTP)
    assert smtp.send(subject="synthetic", message="synthetic notice")["status"] == "SIMULATED"

    monkeypatch.setenv("SYNTHETIC_WEBHOOK", "https://localhost/hook")
    class Response:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *_args): pass
    requests = []
    def transport(request, timeout):
        requests.append((request.method, timeout))
        return Response()
    webhook = WebhookNotificationAdapter(url_env="SYNTHETIC_WEBHOOK", token_env=None,
                                         request_transport=transport)
    assert webhook.health_check().status == "SIMULATED"
    assert webhook.send(subject="synthetic", message="synthetic message")["status"] == "SIMULATED"
    assert requests == [("POST", 10)]


def test_mock_connector_is_explicitly_simulated():
    assert SimulatedConnector().health_check().status == "SIMULATED"


def test_notification_connectors_default_to_dry_run(monkeypatch):
    monkeypatch.delenv("CONNECTORS_ENABLED", raising=False)
    assert SMTPNotificationAdapter().send(subject="synthetic", message="synthetic")["status"] == "DRY_RUN"
    assert WebhookNotificationAdapter().send(subject="synthetic", message="synthetic")["status"] == "DRY_RUN"


def test_execution_verification_and_later_prediction_recommendation_comparison(tmp_path):
    repo = Repository("sqlite://", company_id="synthetic-company",
                      engine=create_engine("sqlite://"))
    now = datetime.now(timezone.utc)
    repo.add(DatasetVersionRow(id="synthetic-dv", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=now, payload={}))
    repo.add(ModelVersionRow(id="synthetic-mv", dataset_version_id="synthetic-dv", name="synthetic-model",
        version="synthetic-v1", artifact_hash="synthetic-hash", trained_at=now,
        training_data_version="synthetic-dv", payload={}))
    repo.add(IncidentRow(id="synthetic-incident-outcome", dataset_version_id="synthetic-dv", source="synthetic",
        title="Synthetic incident", occurred_at=now, payload={}))
    repo.add(RecommendationRow(id="synthetic-rec-outcome", incident_id="synthetic-incident-outcome",
        source="synthetic", action="synthetic_monitor", payload={"expected_outcome": 1, "outcome_field": "delay"}))
    repo.add(ActionRow(id="synthetic-action-outcome", recommendation_id="synthetic-rec-outcome",
        approval_id=None, source="synthetic", status="EXECUTED", dry_run=False,
        payload={"action_class": "READ_ONLY", "execution_status": "EXECUTED"}))
    repo.add(PredictionRow(id="synthetic-pred-outcome", dataset_version_id="synthetic-dv",
        model_version_id="synthetic-mv", source="synthetic", predicted_at=now,
        target="delay", value=1, confidence=None, record_refs=["synthetic-order"], payload={}))
    audit = AuditLog(tmp_path / "audit.jsonl")
    verified = record_execution_verification(repo, "synthetic-action-outcome", executed=True,
        verified=True, result={"status": "synthetic verified"}, actor="synthetic-reviewer", audit_log=audit)
    assert verified["execution_status"] == "EXECUTED_VERIFIED"
    compared = record_observed_outcome(repo, action_id="synthetic-action-outcome", source="synthetic",
        observed_at=now + timedelta(hours=1), facts={"delay": 1},
        record_refs=["synthetic-order"], prediction_refs=["synthetic-pred-outcome"],
        recommendation_refs=["synthetic-rec-outcome"], result={"observed": "synthetic"},
        audit_log=audit, actor="synthetic-analyst")
    assert [item["matched"] for item in compared["comparisons"]] == [True, True]
    assert all("causality" in item.get("limitation", "") for item in compared["comparisons"] if item["type"] == "RECOMMENDATION")
