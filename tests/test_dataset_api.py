"""Tests for dataset onboarding API endpoints: upload, suggestions, confirm-mapping, list, delete."""

import io
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.data import dataset_service
from src.core.repository import DataSourceRow, Repository


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    upload_dir = tmp_path / "uploads"
    profile_dir = tmp_path / "profiles"
    monkeypatch.setattr(dataset_service, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(dataset_service, "PROFILE_DIR", profile_dir)
    monkeypatch.setattr(dataset_service, "REGISTRY_PATH", upload_dir / "registry.json")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="synthetic-company", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "synthetic-viewer": "viewer",
        "synthetic-analyst": "analyst",
        "synthetic-reviewer": "reviewer",
        "synthetic-admin": "admin",
    }))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    app = api_main.create_app(repo)
    app.state.kill_switch = False
    return TestClient(app)


def auth_header(role="reviewer"):
    return {"X-API-Key": f"synthetic-{role}"}


def test_upload_requires_analyst_reviewer_or_admin(client):
    csv_bytes = b"order_id,purchase_date\nORD-1,2026-01-01\n"
    # Viewer should be forbidden (403)
    resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("test.csv", csv_bytes, "text/csv")},
        headers=auth_header("viewer"),
    )
    assert resp.status_code == 403

    # Analyst should succeed (201)
    resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("test_analyst.csv", csv_bytes, "text/csv")},
        headers=auth_header("analyst"),
    )
    assert resp.status_code == 201, resp.text

    # Reviewer should succeed (201)
    resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("test_reviewer.csv", csv_bytes, "text/csv")},
        headers=auth_header("reviewer"),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    job = client.get(f"/api/v1/imports/{data['import_job_id']}", headers=auth_header()).json()
    assert job["total_rows"] == 1
    assert data["sha256"]


def test_upload_rejects_unallowed_types(client):
    bad_bytes = b"echo 'malicious'"
    resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("malicious.sh", bad_bytes, "text/x-sh")},
        headers=auth_header("reviewer"),
    )
    assert resp.status_code == 400
    assert "Allowed file types" in resp.json()["error"]["message"]


def test_upload_rejects_exorbitant_size(client, monkeypatch):
    from src.data import dataset_service
    monkeypatch.setattr(dataset_service, "MAX_UPLOAD_SIZE", 50)  # limit to 50 bytes for test

    big_bytes = b"a" * 100
    resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("big.csv", big_bytes, "text/csv")},
        headers=auth_header("reviewer"),
    )
    assert resp.status_code == 413
    assert "exceeds maximum upload limit" in resp.json()["error"]["message"]


def test_upload_zip_bomb_safety(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(501):
            zf.writestr(f"item_{i}.txt", "data")

    resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("bomb.zip", buf.getvalue(), "application/zip")},
        headers=auth_header("reviewer"),
    )
    assert resp.status_code == 201
    job = client.get(f"/api/v1/imports/{resp.json()['import_job_id']}", headers=auth_header()).json()
    assert job["status"] == "FAILED"
    assert "too many entries" in job["error"]


def test_suggestions_and_confirm_mapping_flow(client):
    csv_bytes = (
        "order_id,order_purchase_timestamp,promised_delivery,delivered_date,seller_id\n"
        "SYNTH-01,2026-01-01,2026-01-10,2026-01-09,SELL-10\n"
        "SYNTH-02,2026-01-02,2026-01-12,2026-01-11,SELL-20\n"
    ).encode("utf-8")

    # 1. Upload dataset
    upload_resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("synthetic_flow.csv", csv_bytes, "text/csv")},
        data={"dataset_name": "synthetic_flow"},
        headers=auth_header("reviewer"),
    )
    assert upload_resp.status_code == 201, upload_resp.text

    # 2. Get suggestions
    sugg_resp = client.get(
        "/api/v1/datasets/synthetic_flow/suggestions",
        headers=auth_header("reviewer"),
    )
    assert sugg_resp.status_code == 200
    sugg_data = sugg_resp.json()
    assert sugg_data["auto_confirmed"] is False
    assert len(sugg_data["suggestions"]) == 5

    # 3. Attempt confirmation with invalid mapping (missing order_id) -> 422
    bad_confirm = client.put(
        "/api/v1/datasets/synthetic_flow/confirm-mapping",
        json={"mappings": {"order_purchase_timestamp": "order_ts"}},
        headers=auth_header("reviewer"),
    )
    assert bad_confirm.status_code == 422

    # 4. Confirm with valid mapping
    good_mappings = {
        "order_id": "order_id",
        "order_purchase_timestamp": "order_ts",
        "promised_delivery": "promised_ts",
        "delivered_date": "delivered_ts",
        "seller_id": "supplier_id",
    }
    confirm_resp = client.put(
        "/api/v1/datasets/synthetic_flow/confirm-mapping",
        json={"mappings": good_mappings, "description": "Synthetic flow test"},
        headers=auth_header("reviewer"),
    )
    assert confirm_resp.status_code == 200
    profile_data = confirm_resp.json()
    assert profile_data["name"] == "synthetic_flow"
    assert profile_data["capabilities"]["delay_prediction"]["possible"] is True

    # 5. List datasets
    list_resp = client.get("/api/v1/datasets", headers=auth_header("reviewer"))
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    flow_item = next(item for item in items if item["dataset_name"] == "synthetic_flow")
    assert flow_item["status"] == "ACCEPTED"

    # 6. Delete dataset
    del_resp = client.delete(
        "/api/v1/datasets/synthetic_flow",
        headers=auth_header("admin"),
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True
    # Removing the source from monitoring preserves its immutable raw bytes and history.
    uploaded_path = Path(client.app.state.repository.get(
        DataSourceRow, flow_item["source_id"], include_deleted=True).location_ref)
    assert uploaded_path.exists()
    after_delete = client.get("/api/v1/datasets", headers=auth_header("reviewer"))
    deleted_item = next(item for item in after_delete.json()["items"] if item["dataset_name"] == "synthetic_flow")
    assert deleted_item["status"] == "DELETED"
    assert deleted_item["monitoring"] is False
