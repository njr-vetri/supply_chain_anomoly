"""Synthetic tests verifying strict cross-company isolation for Stage 7."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (
    ActionRow, AuditEventRow, DataSourceRow, DatasetVersionRow,
    IncidentRow, OutcomeRow, ProjectRow, RecommendationRow, Repository, WorkspaceRow,
)


@pytest.fixture
def multi_tenant_app(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="company-a", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "viewer-key": "viewer",
        "reviewer-key": "reviewer",
        "admin-key": "admin",
    }))
    app = api_main.create_app(repo)
    return TestClient(app), engine


def test_cross_company_access_is_strictly_prevented(multi_tenant_app):
    client, engine = multi_tenant_app
    now = datetime.now(timezone.utc)

    repo_a = Repository("sqlite://", company_id="company-a", engine=engine)
    repo_b = Repository("sqlite://", company_id="company-b", engine=engine)

    # 1. Company A adds workspace, project, source, dataset, incident, rec, action, outcomes
    repo_a.add(WorkspaceRow(id="ws-a", name="Workspace A"))
    repo_a.add(ProjectRow(id="proj-a", workspace_id="ws-a", name="Project A"))
    repo_a.add(DataSourceRow(id="ds-a", project_id="proj-a", name="feed_a", source_type="csv", location_ref="synthetic"))
    repo_a.add(DatasetVersionRow(
        id="dv-a1", dataset="feed_a", source="feed_a", source_hash="hash-a1",
        observed_at=now, payload={"profile": {"row_count": 50, "columns": {}}}
    ))
    repo_a.add(DatasetVersionRow(
        id="dv-a2", dataset="feed_a", source="feed_a", source_hash="hash-a2",
        observed_at=now, payload={"drift": {
            "status": "DRIFT_ALERT",
            "schema": {"added_columns": ["col_secret_a"]},
            "drift_is_warning_only": True,
        }}
    ))
    repo_a.add(IncidentRow(id="inc-a", dataset_version_id="dv-a1", source="feed_a", title="Incident A", occurred_at=now))
    repo_a.add(RecommendationRow(id="rec-a", incident_id="inc-a", source="feed_a", action="MONITOR"))
    repo_a.add(ActionRow(id="act-a", recommendation_id="rec-a", source="feed_a", status="DRY_RUN", payload={}))
    repo_a.add(OutcomeRow(
        id="outcome-a", action_id="act-a", source="feed_a", observed_at=now,
        payload={"facts": {"metric": 100}, "verified_alert_label": True, "alert_was_raised": True, "verified_by": "rev-a"}
    ))
    repo_a.add(AuditEventRow(
        id="audit-a", event_type="action_dry_run_recorded", actor="user-a",
        occurred_at=now, previous_hash="000", event_hash="hash-a", payload={"secret": "company-a-confidential"}
    ))

    # Company B adds its own data
    repo_b.add(WorkspaceRow(id="ws-b", name="Workspace B"))
    repo_b.add(ProjectRow(id="proj-b", workspace_id="ws-b", name="Project B"))
    repo_b.add(DataSourceRow(id="ds-b", project_id="proj-b", name="feed_b", source_type="csv", location_ref="synthetic"))
    repo_b.add(AuditEventRow(
        id="audit-b", event_type="action_dry_run_recorded", actor="user-b",
        occurred_at=now, previous_hash="000", event_hash="hash-b", payload={"data": "company-b-info"}
    ))

    # 2. Repository level check: Company B cannot see Company A rows
    assert repo_b.get(DataSourceRow, "ds-a") is None
    assert repo_b.get(DatasetVersionRow, "dv-a1") is None
    assert repo_b.get(OutcomeRow, "outcome-a") is None
    assert repo_b.get(AuditEventRow, "audit-a") is None
    assert [row.id for row in repo_b.list_rows(DataSourceRow)] == ["ds-b"]

    # 3. Direct cross-company write rejection
    cross_row = IncidentRow(id="inc-invalid", dataset_version_id="dv-a1", source="synthetic", title="Cross attempt", occurred_at=now)
    cross_row.company_id = "company-b"
    with pytest.raises(PermissionError, match="Cannot write a row owned by another company"):
        repo_a.add(cross_row)

    # 4. API level check using X-Company-Id headers:
    # Request from Company B trying to read Company A's dataset drift
    resp_drift_b = client.get("/api/v1/datasets/feed_a/drift", headers={
        "X-API-Key": "reviewer-key",
        "X-Company-Id": "company-b",
    })
    # Must be 404 because feed_a does not exist for company-b
    assert resp_drift_b.status_code == 404

    # Request from Company A successfully sees its drift
    resp_drift_a = client.get("/api/v1/datasets/feed_a/drift", headers={
        "X-API-Key": "reviewer-key",
        "X-Company-Id": "company-a",
    })
    assert resp_drift_a.status_code == 200
    assert resp_drift_a.json()["status"] == "DRIFT_ALERT"
    assert "col_secret_a" in resp_drift_a.json()["schema"]["added_columns"]

    # Request from Company B for outcomes:
    # Company B has no verified outcomes, must return insufficient verified outcomes (count = 0)
    resp_outcomes_b = client.get("/api/v1/evaluation/outcomes", headers={
        "X-API-Key": "viewer-key",
        "X-Company-Id": "company-b",
    })
    assert resp_outcomes_b.status_code == 200
    assert resp_outcomes_b.json()["total_outcomes_recorded"] == 0
    assert resp_outcomes_b.json()["alerts"]["status"] == "INSUFFICIENT_VERIFIED_LABELS"

    # Request from Company A for outcomes:
    # Sees its 1 verified outcome
    resp_outcomes_a = client.get("/api/v1/evaluation/outcomes", headers={
        "X-API-Key": "viewer-key",
        "X-Company-Id": "company-a",
    })
    assert resp_outcomes_a.status_code == 200
    assert resp_outcomes_a.json()["total_outcomes_recorded"] == 1
    assert resp_outcomes_a.json()["alerts"]["status"] == "COMPUTED_FROM_VERIFIED_LABELS"

    # Request from Company B for audit:
    # Sees only audit-b, never audit-a
    resp_audit_b = client.get("/api/v1/audit", headers={
        "X-API-Key": "admin-key",
        "X-Company-Id": "company-b",
    })
    assert resp_audit_b.status_code == 200
    items_b = resp_audit_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["id"] == "audit-b"
    assert "company-a-confidential" not in str(resp_audit_b.json())
