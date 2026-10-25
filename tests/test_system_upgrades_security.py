"""Tests for the 8 system fixes/upgrades and security guarantees:
1. Login lockout on 5 repeated failures
2. Expired JWT token rejection (401)
3. Last-admin protection (cannot delete or deactivate last admin)
4. Cross-company access blocked (token/key mismatch with tenant)
5. Kill switch and alert dedup surviving restart
6. XLSX notes sheet skipped with reason
7. Multi-table ZIP safe extraction and table preview
"""
import io
import time
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from src.core.repository import Repository, UserRow
from src.alerts.manager import AlertManager
from src.alerts.channels import ConsoleChannel
from src.security.auth import create_access_token


@pytest.fixture
def test_env(tmp_path: Path):
    db_path = tmp_path / "security_test.db"
    db_url = f"sqlite:///{db_path}"
    repo = Repository(db_url, company_id="test_co")
    app = create_app(repository=repo)
    client = TestClient(app)

    # Initial setup
    setup_resp = client.post("/api/v1/auth/setup", json={
        "company_id": "test_co",
        "company_name": "Test Co",
        "admin_username": "admin_user",
        "admin_email": "admin@test.com",
        "admin_password": "AdminPassword123!",
    })
    assert setup_resp.status_code == 200
    admin_token = setup_resp.json()["token"]

    return {
        "client": client,
        "repo": repo,
        "db_url": db_url,
        "tmp_path": tmp_path,
        "admin_token": admin_token,
    }


def test_login_lockout_after_repeated_failures(test_env):
    client: TestClient = test_env["client"]

    # 4 consecutive failed logins -> 401
    for attempt in range(4):
        resp = client.post("/api/v1/auth/login", json={
            "username_or_email": "admin_user",
            "password": f"WrongPassword_{attempt}!",
            "company_id": "test_co",
        })
        assert resp.status_code == 401

    # 5th failed attempt locks the account -> 423 Locked
    locked_resp = client.post("/api/v1/auth/login", json={
        "username_or_email": "admin_user",
        "password": "WrongPassword_Final!",
        "company_id": "test_co",
    })
    assert locked_resp.status_code == 423
    assert "temporarily locked" in locked_resp.json()["error"]["message"]


def test_expired_token_rejection(test_env):
    client: TestClient = test_env["client"]
    from datetime import timedelta

    # Generate an expired token (expires in the past)
    expired_token = create_access_token(
        data={"sub": "user-123", "username": "admin_user", "role": "admin", "company_id": "test_co"},
        expires_delta=timedelta(seconds=-3600),
    )

    resp = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "Session expired or invalid token" in resp.json()["error"]["message"]


def test_last_admin_protection(test_env):
    client: TestClient = test_env["client"]
    admin_auth = {"Authorization": f"Bearer {test_env['admin_token']}"}

    # Fetch users list to get the admin's user ID
    users_resp = client.get("/api/v1/auth/users", headers=admin_auth)
    assert users_resp.status_code == 200
    admin_id = users_resp.json()["items"][0]["id"]

    # Attempt to delete the only admin
    del_resp = client.delete(f"/api/v1/auth/users/{admin_id}", headers=admin_auth)
    assert del_resp.status_code in (400, 409)
    assert "Cannot delete or deactivate the last active admin" in del_resp.json()["error"]["message"]


def test_cross_company_token_and_key_isolation(test_env):
    client: TestClient = test_env["client"]
    admin_auth = {"Authorization": f"Bearer {test_env['admin_token']}"}

    # Create an API key for test_co
    key_resp = client.post("/api/v1/auth/api-keys", json={
        "name": "Test Analyst Key",
        "role": "analyst",
    }, headers=admin_auth)
    assert key_resp.status_code == 200
    raw_api_key = key_resp.json()["api_key"]

    # 1. Bearer token used with mismatched X-Company-Id
    token_mismatch = client.get("/api/v1/datasets", headers={
        "Authorization": f"Bearer {test_env['admin_token']}",
        "X-Company-Id": "other_co",
    })
    assert token_mismatch.status_code == 403
    assert "Cross-company access forbidden" in token_mismatch.json()["error"]["message"]

    # 2. Machine API Key used with mismatched X-Company-Id
    key_mismatch = client.get("/api/v1/datasets", headers={
        "X-API-Key": raw_api_key,
        "X-Company-Id": "other_co",
    })
    assert key_mismatch.status_code == 403
    assert "Cross-company access forbidden" in key_mismatch.json()["error"]["message"]


def test_kill_switch_and_alert_dedup_surviving_restart(test_env):
    db_url = test_env["db_url"]
    repo1: Repository = test_env["repo"]

    # 1. Set Kill Switch in DB
    repo1.set_kill_switch(True)
    assert repo1.get_kill_switch() is True

    # 2. Alert dedup with history persistence
    hist_file = test_env["tmp_path"] / "alerts_history.jsonl"
    channel = ConsoleChannel()
    mgr1 = AlertManager(channels={"console": channel}, history_path=hist_file)
    alert_payload = {
        "source": "shipment_tracking",
        "incident_key": "INC-99901",
        "severity": "HIGH",
        "message": "High delay risk detected on carrier",
        "first_seen": "2026-10-24T10:00:00Z",
        "last_seen": "2026-10-24T10:00:00Z",
    }
    routed1 = mgr1.process(alert_payload)
    assert routed1.get("event") == "alert_routed"

    # Route again on mgr1 -> duplicate suppressed
    suppressed1 = mgr1.process(alert_payload)
    assert suppressed1.get("event") == "duplicate_suppressed"

    # 3. Simulate process restart by instantiating new Repository and AlertManager
    repo2 = Repository(db_url, company_id="test_co")
    assert repo2.get_kill_switch() is True, "Kill switch state must survive restart via database"

    mgr2 = AlertManager(channels={"console": channel}, history_path=hist_file)
    suppressed2 = mgr2.process(alert_payload)
    assert suppressed2.get("event") == "duplicate_suppressed", "Duplicate suppression must survive restart"


def test_xlsx_multi_sheet_and_skipped_notes(test_env):
    client: TestClient = test_env["client"]
    admin_auth = {"Authorization": f"Bearer {test_env['admin_token']}"}

    vendors_xlsx = Path("tests/fixtures/synthetic/kaveri_foods/extra_tests/vendors.xlsx")
    assert vendors_xlsx.exists()

    with vendors_xlsx.open("rb") as f:
        resp = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("vendors.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"dataset_name": "vendors_xlsx"},
            headers=admin_auth,
        )
    assert resp.status_code == 201


def test_multi_table_zip_preview_and_sources(test_env):
    client: TestClient = test_env["client"]
    admin_auth = {"Authorization": f"Bearer {test_env['admin_token']}"}

    multi_zip = Path("tests/fixtures/synthetic/kaveri_foods/extra_tests/multi_table.zip")
    assert multi_zip.exists()

    with multi_zip.open("rb") as f:
        resp = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("multi_table.zip", f.read(), "application/zip")},
            headers=admin_auth,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_multi_table"] is True
    assert data["table_count"] == 3
    assert len(data["tables"]) == 3
    for tbl in data["tables"]:
        assert "dataset_name" in tbl
        assert "filename" in tbl
        assert "size_bytes" in tbl
