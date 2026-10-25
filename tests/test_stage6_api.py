"""Synthetic API integration checks for Stage 6 workflows and connectors."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (DataSourceRow, DatasetVersionRow, EvidenceRow, IncidentRow,
                                 MappingVersionRow, ProjectRow, Repository, WorkspaceRow)


@pytest.fixture
def client(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-company", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({"synthetic-viewer": "viewer", "synthetic-analyst": "analyst",
        "synthetic-reviewer": "reviewer", "synthetic-admin": "admin"}))
    monkeypatch.setenv("CONNECTORS_ENABLED", "false")
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    app = api_main.create_app(repo)
    app.state.alert_history_path = tmp_path / "alert-history.jsonl"
    return TestClient(app), repo


def headers(role="analyst"):
    return {"X-API-Key": f"synthetic-{role}"}


def test_playbook_api_derives_fields_from_accepted_mapping(client):
    http, repo = client
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    repo.add(WorkspaceRow(id="synthetic-workspace", name="Synthetic workspace"))
    repo.add(ProjectRow(id="synthetic-project", workspace_id="synthetic-workspace", name="Synthetic project"))
    repo.add(DataSourceRow(id="synthetic-source", project_id="synthetic-project", name="synthetic",
                           source_type="synthetic", location_ref="synthetic://source"))
    repo.add(DatasetVersionRow(id="synthetic-dataset-stage6", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=now, payload={"source_id": "synthetic-source"}))
    repo.add(MappingVersionRow(id="synthetic-map", data_source_id="synthetic-source", version="v0001",
        status="ACCEPTED", mapping={"mappings": {"supplier_id": "SyntheticSupplier", "order_id": "SyntheticOrder"}}))
    repo.add(IncidentRow(id="synthetic-incident-stage6", dataset_version_id="synthetic-dataset-stage6",
        source="synthetic", title="Synthetic incident", occurred_at=now,
        payload={"record_refs": ["synthetic-record"]}))
    repo.add(EvidenceRow(id="synthetic-evidence-stage6", dataset_version_id="synthetic-dataset-stage6",
        incident_id="synthetic-incident-stage6", source="synthetic", observed_at=now,
        record_refs=["synthetic-record"], payload={}))
    response = http.post("/api/v1/recommendations/playbooks", headers=headers(), json={
        "incident_id": "synthetic-incident-stage6", "driver_type": "supplier",
        "driver_value": "synthetic-supplier", "evidence_refs": ["synthetic-evidence-stage6"]})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "PROPOSED"
    assert data["estimated_effect"] is None
    assert data["approvals"]["required"] is True


def test_what_if_and_connector_health_are_transparent_and_disabled_by_default(client):
    http, _repo = client
    scenario = http.post("/api/v1/recommendations/what-if", headers=headers(), json={
        "affected_order_count": 10, "calibrated_delay_probability": 0.4, "probability_calibrated": True,
        "scenarios": [{"name": "synthetic-scenario", "assumed_relative_probability_reduction": 0.1,
                       "assumptions": ["synthetic assumption"]}]})
    assert scenario.status_code == 200
    assert scenario.json()["label"] == "HYPOTHETICAL"
    assert scenario.json()["not_estimated"] == ["supplier capacity", "inventory", "cost savings"]
    health = http.get("/api/v1/connectors/health", headers=headers("admin"))
    assert health.status_code == 200
    statuses = {item["name"]: item["status"] for item in health.json()["items"]}
    assert statuses["smtp_email"] == "DRY_RUN"
    assert statuses["webhook"] == "DRY_RUN"
    assert health.json()["extensions"]["erp"]["status"] == "EXTENSION_NOT_IMPLEMENTED"


def test_alert_api_acknowledgement_and_assignment_are_persisted(client):
    http, _repo = client
    from src.alerts.manager import AlertManager
    manager = AlertManager(channels={}, history_path=http.app.state.alert_history_path,
        settings={"dedup_window_seconds": 60, "severity_routes": {}, "escalation": [], "group_by": []})
    routed = manager.process({"source": "synthetic", "incident_key": "synthetic-alert", "severity": "LOW"})
    ack = http.post(f"/api/v1/alerts/{routed['group_id']}/acknowledge", headers=headers(),
                    json={"reason": "synthetic acknowledgement"})
    assign = http.post(f"/api/v1/alerts/{routed['group_id']}/assign", headers=headers(),
                       json={"assigned_to": "synthetic-reviewer"})
    assert ack.status_code == 200 and ack.json()["status"] == "ACKNOWLEDGED"
    assert assign.status_code == 200 and assign.json()["assigned_to"] == "synthetic-reviewer"
    history = http.get("/api/v1/alerts/history", headers=headers("viewer")).json()["items"]
    assert [item["event"] for item in history[-2:]] == ["alert_acknowledged", "alert_assigned"]


def test_alert_evaluation_requires_verified_labels_and_permission_changes_are_audited(client):
    http, _repo = client
    initial = http.get("/api/v1/evaluation/alerts", headers=headers("viewer"))
    assert initial.status_code == 200
    assert initial.json()["status"] == "INSUFFICIENT_VERIFIED_LABELS"
    denied = http.put("/api/v1/admin/permission-policy", headers=headers("analyst"),
        json={"role_levels": {"viewer": 1, "analyst": 3, "reviewer": 5, "admin": 8}})
    assert denied.status_code == 403
    changed = http.put("/api/v1/admin/permission-policy", headers=headers("admin"),
        json={"role_levels": {"viewer": 1, "analyst": 3, "reviewer": 5, "admin": 8}})
    assert changed.status_code == 200
    assert changed.json()["role_levels"]["analyst"] == 3
    invalid = http.put("/api/v1/admin/permission-policy", headers=headers("admin"),
        json={"role_levels": {"viewer": 5, "analyst": 3, "reviewer": 6, "admin": 8}})
    assert invalid.status_code == 422
