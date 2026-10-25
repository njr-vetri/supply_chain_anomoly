"""Synthetic-only checks for API authorization and safe operational defaults."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import EvidenceRow, IncidentRow, RecommendationRow, HypothesisRow, Repository
from src.risk.hypotheses import HypothesisCase, EvidenceLedger, LedgerEvidence
from src.core.schemas import HypothesisStatus


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-company", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "synthetic-viewer": "viewer", "synthetic-analyst": "analyst",
        "synthetic-reviewer": "reviewer", "synthetic-admin": "admin",
    }))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    app = api_main.create_app(repo)
    app.state.kill_switch = False
    return TestClient(app), repo


def headers(role="analyst"):
    return {"X-API-Key": f"synthetic-{role}"}


def test_unauthenticated_and_role_restrictions(client):
    http, _repo = client
    assert http.get("/api/v1/health").status_code == 401
    denied = http.put("/api/v1/admin/kill-switch", headers=headers("viewer"), json={"enabled": True, "reason": "synthetic test"})
    assert denied.status_code == 403


def test_invalid_input_uses_consistent_error_shape(client):
    http, _repo = client
    response = http.post("/api/v1/pipeline/run", headers=headers("analyst"),
        json={"datasets": ["synthetic-unknown"]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["message"] == "Request validation failed"


def test_read_routes_and_openapi_smoke(client):
    http, _repo = client
    for path in ("/health", "/quality", "/incidents", "/predictions", "/anomalies",
                 "/hypotheses", "/recommendations", "/approvals", "/actions",
                 "/actions/history", "/alerts", "/models", "/outcomes"):
        response = http.get(f"/api/v1{path}", headers=headers("viewer"))
        assert response.status_code == 200, (path, response.text)
    assert http.get("/openapi.json").status_code == 200


def test_incident_detail_and_graph_include_stored_relationships(client):
    http, repo = client
    from src.core.repository import DatasetVersionRow
    observed = api_main.datetime.now(api_main.timezone.utc)
    repo.add(DatasetVersionRow(id="synthetic-dataset", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=observed, payload={}))
    repo.add(IncidentRow(id="synthetic-incident", dataset_version_id="synthetic-dataset", source="synthetic",
        title="Synthetic incident", occurred_at=observed, payload={"id": "synthetic-incident",
            "title": "Synthetic incident", "description": "Synthetic detail", "source": "synthetic",
            "record_refs": ["synthetic-record"], "occurred_at": observed.isoformat(),
            "evidence_refs": ["synthetic-evidence"], "limitations": ["Synthetic limitation"]}))
    repo.add(EvidenceRow(id="synthetic-evidence", dataset_version_id="synthetic-dataset",
        incident_id="synthetic-incident", source="synthetic", observed_at=observed,
        record_refs=["synthetic-record"], payload={"id": "synthetic-evidence",
            "evidence_type": "synthetic_observation", "source": "synthetic",
            "record_refs": ["synthetic-record"], "observed_at": observed.isoformat(),
            "facts": {"observed_value": 7}, "limitations": ["Synthetic evidence limit"]}))
    detail = http.get("/api/v1/incidents/synthetic-incident", headers=headers("viewer"))
    assert detail.status_code == 200
    assert detail.json()["evidence"][0]["facts"]["observed_value"] == 7
    assert "Synthetic limitation" in detail.json()["limitations"]
    graph = http.get("/api/v1/incidents/synthetic-incident/graph", headers=headers("viewer"))
    assert graph.status_code == 200
    assert graph.json()["edges"][0]["status"] == "ESTABLISHED"


def test_confirmation_requires_reviewer_role(client):
    http, repo = client
    # SQLite FK relations are populated with synthetic parent rows.
    from src.core.repository import DatasetVersionRow
    repo.add(DatasetVersionRow(id="synthetic-dataset", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=api_main.datetime.now(api_main.timezone.utc), payload={}))
    repo.add(IncidentRow(id="synthetic-incident", dataset_version_id="synthetic-dataset", source="synthetic",
        title="Synthetic incident", occurred_at=api_main.datetime.now(api_main.timezone.utc), payload={}))
    case = HypothesisCase(id="synthetic-hypothesis", statement="Synthetic hypothesis", source="synthetic",
        status=HypothesisStatus.SUPPORTED,
        ledger=EvidenceLedger(supporting=[
            LedgerEvidence(evidence_id="synthetic-evidence-1", classification="supporting", source="synthetic", record_refs=["synthetic-row-1"], observed_at=api_main.datetime.now(api_main.timezone.utc), strength=0.9, description="Synthetic evidence"),
            LedgerEvidence(evidence_id="synthetic-evidence-2", classification="supporting", source="synthetic", record_refs=["synthetic-row-2"], observed_at=api_main.datetime.now(api_main.timezone.utc), strength=0.9, description="Synthetic evidence"),
        ]))
    repo.add(HypothesisRow(id=case.id, incident_id="synthetic-incident", statement=case.statement,
        status=case.status.value, payload=case.model_dump(mode="json")))
    body = {"rationale": "Synthetic review rationale"}
    assert http.post(f"/api/v1/hypotheses/{case.id}/confirm", headers=headers("analyst"), json=body).status_code == 403
    confirmed = http.post(f"/api/v1/hypotheses/{case.id}/confirm", headers=headers("reviewer"), json=body)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"


def test_kill_switch_blocks_action_execution_and_dry_run_is_labelled(client):
    http, repo = client
    from src.core.repository import DatasetVersionRow
    repo.add(DatasetVersionRow(id="synthetic-dataset", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=api_main.datetime.now(api_main.timezone.utc), payload={}))
    repo.add(IncidentRow(id="synthetic-incident", dataset_version_id="synthetic-dataset", source="synthetic",
        title="Synthetic incident", occurred_at=api_main.datetime.now(api_main.timezone.utc), payload={}))
    repo.add(RecommendationRow(id="synthetic-recommendation", incident_id="synthetic-incident",
        source="synthetic", action="investigate_synthetic", payload={}))
    enabled = http.put("/api/v1/admin/kill-switch", headers=headers("admin"),
        json={"enabled": True, "reason": "Synthetic safety test"})
    assert enabled.status_code == 200 and enabled.json()["enabled"] is True
    result = http.post("/api/v1/actions", headers=headers("analyst"), json={
        "recommendation_id": "synthetic-recommendation", "action_class": "READ_ONLY"})
    assert result.status_code == 201
    assert result.json()["status"] == "BLOCKED_KILL_SWITCH"
    disabled = http.put("/api/v1/admin/kill-switch", headers=headers("admin"),
        json={"enabled": False, "reason": "Synthetic safety test complete"})
    assert disabled.status_code == 200
    dry_run = http.post("/api/v1/actions", headers=headers("analyst"), json={
        "recommendation_id": "synthetic-recommendation", "action_class": "READ_ONLY"})
    assert dry_run.status_code == 201
    assert dry_run.json()["status"] == "DRY_RUN" and dry_run.json()["dry_run"] is True
