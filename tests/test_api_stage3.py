"""Synthetic API coverage for Stage 3 capability and preview routes."""
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import DataSourceRow, MappingVersionRow, ProjectRow, Repository, WorkspaceRow


def test_project_capabilities_and_pipeline_preview_are_project_scoped(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-stage3", engine=engine)
    repo.add(WorkspaceRow(id="synthetic-workspace", name="Synthetic workspace"))
    repo.add(ProjectRow(id="synthetic-project", workspace_id="synthetic-workspace", name="Synthetic sales"))
    repo.add(DataSourceRow(id="synthetic-source", project_id="synthetic-project", name="sales",
                           source_type=".csv", location_ref="synthetic.csv"))
    repo.add(MappingVersionRow(id="synthetic-mapping", data_source_id="synthetic-source", version="v0001",
        status="ACCEPTED", mapping={"mappings": {"sku": "product_id", "units": "quantity",
                                                   "sold": "event_timestamp"}}))
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({"synthetic-analyst": "analyst", "synthetic-viewer": "viewer"}))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    client = TestClient(api_main.create_app(repo))
    headers = {"X-API-Key": "synthetic-viewer"}
    capabilities = client.get("/api/v1/projects/synthetic-project/capabilities", headers=headers).json()
    assert capabilities["features"]["demand_analysis"]["status"] == "AVAILABLE"
    assert capabilities["features"]["inventory_risk"]["status"] == "UNSUPPORTED"
    response = client.post("/api/v1/pipeline/previews", headers={"X-API-Key": "synthetic-analyst"},
                           json={"project_id": "synthetic-project"})
    assert response.status_code == 201
    assert response.json()["dry_run"] is True
    assert response.json()["message"] == "Preview only. No pipeline step has run."
