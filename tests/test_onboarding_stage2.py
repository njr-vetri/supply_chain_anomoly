"""Synthetic-only onboarding tests; these fixtures are not evidence of real-world performance."""
from __future__ import annotations

import json
import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import DataSourceRow, Repository


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-company", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({"synthetic-reviewer": "reviewer", "synthetic-viewer": "viewer"}))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    return TestClient(api_main.create_app(repo))


def auth(role: str = "reviewer") -> dict[str, str]:
    return {"X-API-Key": f"synthetic-{role}"}


def upload(client: TestClient, filename: str, data: str, name: str) -> dict:
    response = client.post("/api/v1/datasets/upload", files={"file": (filename, data.encode(), "text/csv")},
                           data={"dataset_name": name}, headers=auth())
    assert response.status_code == 201, response.text
    return response.json()


def test_chunked_upload_profile_mapping_and_import_decision(client):
    # Synthetic source with deliberately non-canonical source column names.
    result = upload(client, "orders.csv",
        "Order Ref,Event Date,Vendor Ref\nO-1,2026-01-01,V-1\nO-2,2026-01-02,V-2\n", "orders")
    assert result["status"] == "QUEUED"
    job = client.get(f"/api/v1/imports/{result['import_job_id']}", headers=auth()).json()
    assert job["status"] == "AWAITING_IMPORT_DECISION"
    assert job["processed_rows"] == 2
    assert job["total_rows"] == 2
    stored = Path(client.app.state.repository.get(DataSourceRow, result["source_id"]).location_ref)
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == result["sha256"]
    profile = job["statistics"]
    assert all("sample" not in column and "values" not in column for column in profile["columns"])
    assert next(column for column in profile["columns"] if column["name"] == "Order Ref")["candidate_identifier"]

    preview = client.post(f"/api/v1/imports/{result['import_job_id']}/preview", json={"mode": "append"},
                          headers=auth())
    assert preview.status_code == 200
    assert preview.json()["resulting_rows"] == 2
    assert "Preview only" in preview.json()["note"]
    suggestion_response = client.get("/api/v1/datasets/orders/suggestions", headers=auth())
    assert suggestion_response.status_code == 200, suggestion_response.text
    suggestions = suggestion_response.json()
    assert suggestions["auto_confirmed"] is False
    assert all("confidence" in item and "reason" in item for item in suggestions["suggestions"])

    mapping = client.post("/api/v1/datasets/orders/mappings", json={
        "mappings": {"Order Ref": "order_id", "Event Date": "order_ts"},
        "custom_fields": {"vendor_ref": "Vendor Ref"}, "units": {},
        "time_zone": "UTC", "date_format": "%Y-%m-%d", "reason": "Synthetic review"},
        headers=auth())
    assert mapping.status_code == 200, mapping.text
    assert mapping.json()["status"] == "PENDING_REVIEW"
    assert mapping.json()["auto_confirmed"] is False
    version = mapping.json()["version"]
    accepted = client.post(f"/api/v1/datasets/orders/mappings/{version}/accept",
                           json={"reason": "Synthetic human acceptance"}, headers=auth())
    assert accepted.json()["status"] == "ACCEPTED"
    assert Path(accepted.json()["mapping"]["profile_path"]).exists()

    commit = client.post(f"/api/v1/imports/{result['import_job_id']}/commit", json={"mode": "append"},
                         headers=auth())
    assert commit.json()["status"] == "IMPORTING"
    completed = client.get(f"/api/v1/imports/{result['import_job_id']}", headers=auth()).json()
    assert completed["status"] == "COMPLETED"
    assert completed["processed_rows"] == completed["total_rows"] == 2
    assert Path(completed["processed_file"]).exists()
    assert Path(completed["lineage_file"]).exists()


def test_multifile_relationship_preview_reports_orphans_and_requires_approval(client):
    # Synthetic orders, shipments and suppliers deliberately contain broken foreign keys.
    orders = upload(client, "orders.csv", "order_ref,vendor_ref\nO1,V1\nO2,V2\nO3,V9\n", "orders")
    shipments = upload(client, "shipments.csv", "order_ref,ship_date\nO1,2026-01-02\nO9,2026-01-03\n", "shipments")
    suppliers = upload(client, "suppliers.csv", "vendor_ref,name\nV1,North\nV3,West\n", "suppliers")
    # Ensure background task results are visible before relationship profiling.
    for item in (orders, shipments, suppliers):
        assert client.get(f"/api/v1/imports/{item['import_job_id']}", headers=auth()).json()["status"] == "AWAITING_IMPORT_DECISION"

    body = {"links": [
        {"left_source_id": orders["source_id"], "left_key": "order_ref",
         "right_source_id": shipments["source_id"], "right_key": "order_ref", "relationship": "order_shipment"},
        {"left_source_id": orders["source_id"], "left_key": "vendor_ref",
         "right_source_id": suppliers["source_id"], "right_key": "vendor_ref", "relationship": "order_supplier"},
    ]}
    preview = client.post("/api/v1/datasets/relationships/preview", json=body, headers=auth())
    assert preview.status_code == 200, preview.text
    links = preview.json()["links"]
    assert links[0]["matched_left_rows"] == 1
    assert links[0]["orphan_left_rows"] == 2
    assert links[0]["orphan_right_rows"] == 1
    assert links[1]["matched_left_rows"] == 1
    assert links[1]["orphan_left_rows"] == 2
    assert preview.json()["created_relationships"] is False
    approved = client.post(f"/api/v1/datasets/relationships/{preview.json()['proposal_id']}/approve",
                           json={"reason": "Synthetic explicit approval"}, headers=auth())
    assert approved.json()["created_relationships"] is True


def test_replace_import_soft_deletes_old_monitoring_source_but_keeps_file_and_history(client):
    first = upload(client, "orders-v1.csv", "order_ref,event_time\nO1,2026-01-01\nO2,2026-01-02\n", "replaceable")
    first_source = client.app.state.repository.get(DataSourceRow, first["source_id"])
    mapping_body = {"mappings": {"order_ref": "order_id", "event_time": "order_ts"},
        "reason": "Synthetic mapping", "date_format": "%Y-%m-%d", "time_zone": "UTC"}
    first_mapping = client.post("/api/v1/datasets/replaceable/mappings", json=mapping_body, headers=auth()).json()
    client.post(f"/api/v1/datasets/replaceable/mappings/{first_mapping['version']}/accept",
        json={"reason": "Synthetic acceptance"}, headers=auth())
    client.post(f"/api/v1/imports/{first['import_job_id']}/commit", json={"mode": "append"}, headers=auth())
    assert client.get(f"/api/v1/imports/{first['import_job_id']}", headers=auth()).json()["status"] == "COMPLETED"

    second = upload(client, "orders-v2.csv", "order_ref,event_time\nO3,2026-01-03\n", "replaceable")
    second_mapping = client.post("/api/v1/datasets/replaceable/mappings", json=mapping_body, headers=auth()).json()
    client.post(f"/api/v1/datasets/replaceable/mappings/{second_mapping['version']}/accept",
        json={"reason": "Synthetic acceptance"}, headers=auth())
    preview = client.post(f"/api/v1/imports/{second['import_job_id']}/preview", json={"mode": "replace"},
                          headers=auth())
    assert preview.json()["current_rows"] == 2
    assert preview.json()["incoming_rows"] == 1
    client.post(f"/api/v1/imports/{second['import_job_id']}/commit", json={"mode": "replace"}, headers=auth())
    assert client.get(f"/api/v1/imports/{second['import_job_id']}", headers=auth()).json()["status"] == "COMPLETED"
    previous = client.app.state.repository.get(DataSourceRow, first_source.id, include_deleted=True)
    assert previous.deleted_at is not None
    assert Path(previous.location_ref).exists()
    history = client.get("/api/v1/imports", headers=auth()).json()
    assert history["count"] == 2


def test_upload_blocks_formula_injection_and_path_traversal(client):
    formula = client.post("/api/v1/datasets/upload",
        files={"file": ("formula.csv", b"id,comment\n1,=HYPERLINK('x')\n", "text/csv")}, headers=auth())
    assert formula.status_code == 201
    job = client.get(f"/api/v1/imports/{formula.json()['import_job_id']}", headers=auth()).json()
    assert job["status"] == "FAILED"
    assert "formula injection" in job["error"]
    bad_name = client.post("/api/v1/datasets/upload",
        files={"file": ("../escape.csv", b"id,date\n1,2026-01-01\n", "text/csv")}, headers=auth())
    assert bad_name.status_code == 400


def test_upload_accepts_json_and_viewer_cannot_upload(client):
    denied = client.post("/api/v1/datasets/upload", files={"file": ("x.json", b"[]", "application/json")},
                         headers=auth("viewer"))
    assert denied.status_code == 403
    data = b'[{"event_id":"SYN-1","event_timestamp":"2026-01-01T00:00:00Z"}]'
    response = client.post("/api/v1/datasets/upload", files={"file": ("events.json", data, "application/json")},
                           headers=auth())
    assert response.status_code == 201
    status = client.get(f"/api/v1/imports/{response.json()['import_job_id']}", headers=auth()).json()
    assert status["status"] == "AWAITING_IMPORT_DECISION"
    assert status["total_rows"] == 1


def test_zip_path_traversal_is_blocked_without_extracting(client):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.csv", "id,date\nSYN-1,2026-01-01\n")
    response = client.post("/api/v1/datasets/upload",
        files={"file": ("source.zip", archive.getvalue(), "application/zip")}, headers=auth())
    assert response.status_code == 201
    job = client.get(f"/api/v1/imports/{response.json()['import_job_id']}", headers=auth()).json()
    assert job["status"] == "FAILED"
    assert "Path traversal" in job["error"]
