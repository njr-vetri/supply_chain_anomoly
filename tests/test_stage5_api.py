"""Synthetic API contract coverage for Stage 5 controls."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import AnomalyRow, DatasetVersionRow, Repository


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-company", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "synthetic-viewer": "viewer", "synthetic-analyst": "analyst",
        "synthetic-reviewer": "reviewer", "synthetic-admin": "admin"}))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    return TestClient(api_main.create_app(repo)), repo


def headers(role="analyst"):
    return {"X-API-Key": f"synthetic-{role}"}


def test_graph_api_enforces_size_limit(client):
    http, _repo = client
    response = http.get("/api/v1/projects/synthetic-project/graph?limit=5001", headers=headers("viewer"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_company_risk_configuration_is_admin_only_and_versioned(client):
    http, repo = client
    body = {"weights": {"likelihood": 0.35, "impact": 0.3, "evidence_strength": 0.2, "uncertainty": 0.15},
            "thresholds": {"low_max": 0.2, "medium_max": 0.45, "high_max": 0.7}}
    assert http.put("/api/v1/risk/scoring-config", headers=headers("analyst"), json=body).status_code == 403
    stored = http.put("/api/v1/risk/scoring-config", headers=headers("admin"), json=body)
    assert stored.status_code == 200
    assert stored.json()["version"] == "risk-v2"
    assert stored.json()["lifecycle"] == "CANDIDATE"
    assert http.get("/api/v1/risk/scoring-config", headers=headers("viewer")).json()["version"] == "risk-v1"
    compare = http.get("/api/v1/risk/scoring-config/risk-v2/comparison", headers=headers("analyst"))
    assert compare.status_code == 200
    assert compare.json()["performance_effect"].startswith("NOT_ESTIMATED")
    promoted = http.post("/api/v1/risk/scoring-config/risk-v2/promote", headers=headers("reviewer"),
                         json={"reason": "Synthetic reviewer approval"})
    assert promoted.status_code == 200 and promoted.json()["lifecycle"] == "CURRENT"


def test_risk_configuration_requires_review_and_supports_rollback(client):
    http, _repo = client
    body = {"weights": {"likelihood": 0.35, "impact": 0.3, "evidence_strength": 0.2, "uncertainty": 0.15},
            "thresholds": {"low_max": 0.2, "medium_max": 0.45, "high_max": 0.7}}
    assert http.put("/api/v1/risk/scoring-config", headers=headers("admin"), json=body).status_code == 200
    assert http.post("/api/v1/risk/scoring-config/risk-v2/promote", headers=headers("analyst"),
                     json={"reason": "Synthetic approval"}).status_code == 403
    assert http.post("/api/v1/risk/scoring-config/risk-v2/promote", headers=headers("reviewer"),
                     json={"reason": "Synthetic approval"}).status_code == 200
    changed = {**body, "weights": {"likelihood": 0.4, "impact": 0.25, "evidence_strength": 0.2, "uncertainty": 0.15}}
    assert http.put("/api/v1/risk/scoring-config", headers=headers("admin"), json=changed).status_code == 200
    assert http.post("/api/v1/risk/scoring-config/risk-v3/promote", headers=headers("reviewer"),
                     json={"reason": "Synthetic second approval"}).status_code == 200
    rolled_back = http.post("/api/v1/risk/scoring-config/rollback", headers=headers("reviewer"),
                            json={"reason": "Synthetic rollback"})
    assert rolled_back.status_code == 200
    assert rolled_back.json()["current_version"] == "risk-v2"


def test_risk_score_omits_uncalibrated_likelihood(client):
    http, _repo = client
    response = http.post("/api/v1/risk/score", headers=headers("analyst"), json={
        "likelihood": 0.9, "likelihood_calibrated": False,
        "impact": 0.6, "evidence_strength": 0.5, "uncertainty": 0.4})
    assert response.status_code == 200
    result = response.json()
    assert result["factors"]["likelihood"]["available"] is False
    assert result["severity"] is None
    assert result["qualitative_rating"] is not None


def test_incident_assembly_persists_provenance_and_display_status(client):
    http, repo = client
    observed = api_main.datetime.now(api_main.timezone.utc)
    repo.add(DatasetVersionRow(id="synthetic-dataset-stage5", dataset="synthetic", source="synthetic",
        source_hash="synthetic-source-hash", observed_at=observed, payload={}))
    repo.add(AnomalyRow(id="synthetic-anomaly-stage5", dataset_version_id="synthetic-dataset-stage5",
        source="synthetic", detector="synthetic-rule", record_ref="synthetic:record-1",
        feature="synthetic_metric", observed_value=9, baseline=2, payload={}))
    response = http.post("/api/v1/incidents/assemble", headers=headers("analyst"), json={
        "anomaly_ids": ["synthetic-anomaly-stage5"], "title": "Synthetic incident"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["incident"]["record_refs"] == ["synthetic:record-1"]
    assert body["evidence"][0]["facts"]["observed_value"] == 9
    hypotheses = http.get("/api/v1/hypotheses", headers=headers("viewer")).json()["items"]
    assert hypotheses[0]["status"] == "UNVERIFIED"
    assert hypotheses[0]["status_label"] == "Unverified"
