"""End-to-End Acceptance test on unseen synthetic Kaveri Foods dataset.
Never uses real-world metrics or claims production readiness.
All data is SYNTHETIC.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from src.core.repository import HypothesisRow, Repository

SYNTHETIC_DIR = Path("tests/fixtures/synthetic/kaveri_foods")
EXTRA_TESTS_DIR = SYNTHETIC_DIR / "extra_tests"


@pytest.fixture
def test_env(tmp_path: Path):
    db_path = tmp_path / "acceptance.db"
    db_url = f"sqlite:///{db_path}"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    os.environ["UPLOAD_DIR"] = str(upload_dir)

    repo = Repository(db_url, company_id="kaveri_foods")
    app = create_app(repository=repo)
    client = TestClient(app)
    return {"client": client, "tmp_path": tmp_path, "db_url": db_url, "repo": repo}


def test_e2e_acceptance_kaveri_foods_and_company_b(test_env):
    client: TestClient = test_env["client"]
    findings_report: dict[str, Any] = {
        "dataset": "SYNTHETIC Kaveri Foods",
        "steps": {},
        "data_quality": {},
        "capabilities": {},
        "top_anomalies": [],
        "top_drivers": [],
        "leakage_handling": {},
        "graph": {},
        "roles_verified": {},
        "failures": [],
    }

    def api_call(method: str, path: str, **kwargs) -> Any:
        resp = getattr(client, method.lower())(path, **kwargs)
        if resp.status_code not in (200, 201, 202):
            fail_info = {
                "step": f"{method.upper()} {path}",
                "status_code": resp.status_code,
                "error": resp.text,
            }
            findings_report["failures"].append(fail_info)
            pytest.fail(f"Step {method.upper()} {path} failed with HTTP {resp.status_code}: {resp.text}")
        return resp

    # ─────────────────────────────────────────────────────────────────────────
    # Step 1: Initial Setup - Company A (Kaveri Foods)
    # ─────────────────────────────────────────────────────────────────────────
    setup_resp = api_call("POST", "/api/v1/auth/setup", json={
        "company_id": "kaveri_foods",
        "company_name": "Kaveri Foods",
        "admin_username": "kaveri_admin",
        "admin_email": "admin@kaverifoods.com",
        "admin_password": "AdminPassword123!",
    })
    admin_token = setup_resp.json()["token"]
    admin_auth = {"Authorization": f"Bearer {admin_token}", "X-Company-Id": "kaveri_foods"}

    # Admin creates Viewer, Analyst, and Reviewer accounts
    api_call("POST", "/api/v1/auth/users", json={
        "username": "kaveri_viewer",
        "email": "viewer@kaverifoods.com",
        "role": "viewer",
        "temp_password": "TempPassword123!",
    }, headers=admin_auth)

    api_call("POST", "/api/v1/auth/users", json={
        "username": "kaveri_analyst",
        "email": "analyst@kaverifoods.com",
        "role": "analyst",
        "temp_password": "TempPassword123!",
    }, headers=admin_auth)

    api_call("POST", "/api/v1/auth/users", json={
        "username": "kaveri_reviewer",
        "email": "reviewer@kaverifoods.com",
        "role": "reviewer",
        "temp_password": "TempPassword123!",
    }, headers=admin_auth)

    # Viewer login and password change
    v_login = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "kaveri_viewer",
        "password": "TempPassword123!",
    })
    temp_v_token = v_login.json()["token"]
    api_call("POST", "/api/v1/auth/change-password", json={
        "old_password": "TempPassword123!",
        "new_password": "NewViewerPassword123!",
    }, headers={"Authorization": f"Bearer {temp_v_token}"})
    v_perm = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "kaveri_viewer",
        "password": "NewViewerPassword123!",
    })
    viewer_token = v_perm.json()["token"]
    viewer_auth = {"Authorization": f"Bearer {viewer_token}", "X-Company-Id": "kaveri_foods"}

    # Analyst login and forced password change
    analyst_login = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "kaveri_analyst",
        "password": "TempPassword123!",
    })
    temp_analyst_token = analyst_login.json()["token"]
    api_call("POST", "/api/v1/auth/change-password", json={
        "old_password": "TempPassword123!",
        "new_password": "NewAnalystPassword123!",
    }, headers={"Authorization": f"Bearer {temp_analyst_token}"})
    analyst_login_perm = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "kaveri_analyst",
        "password": "NewAnalystPassword123!",
    })
    analyst_token = analyst_login_perm.json()["token"]
    analyst_auth = {"Authorization": f"Bearer {analyst_token}", "X-Company-Id": "kaveri_foods"}

    # Reviewer login and forced password change
    rev_login = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "kaveri_reviewer",
        "password": "TempPassword123!",
    })
    temp_rev_token = rev_login.json()["token"]
    api_call("POST", "/api/v1/auth/change-password", json={
        "old_password": "TempPassword123!",
        "new_password": "NewReviewerPassword123!",
    }, headers={"Authorization": f"Bearer {temp_rev_token}"})
    rev_login_perm = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "kaveri_reviewer",
        "password": "NewReviewerPassword123!",
    })
    reviewer_token = rev_login_perm.json()["token"]
    reviewer_auth = {"Authorization": f"Bearer {reviewer_token}", "X-Company-Id": "kaveri_foods"}

    findings_report["steps"]["setup_company_a"] = "COMPLETED"

    # ─────────────────────────────────────────────────────────────────────────
    # Step 2: Multi-Sheet XLSX Test (Fix 5)
    # ─────────────────────────────────────────────────────────────────────────
    vendors_xlsx_path = EXTRA_TESTS_DIR / "vendors.xlsx"
    assert vendors_xlsx_path.exists(), "extra_tests/vendors.xlsx must exist"
    with vendors_xlsx_path.open("rb") as f:
        xlsx_resp = api_call(
            "POST",
            "/api/v1/datasets/upload",
            files={"file": ("vendors.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"dataset_name": "vendors_excel"},
            headers=analyst_auth,
        )
    xlsx_job_id = xlsx_resp.json()["import_job_id"]
    xlsx_job = api_call("GET", f"/api/v1/imports/{xlsx_job_id}", headers=analyst_auth).json()
    stats = xlsx_job.get("statistics", {})
    skipped = stats.get("sheets_skipped", stats.get("skipped_sheets", []))
    assert any("notes" in s.get("sheet_name", "").lower() for s in skipped), "Notes sheet must be reported as skipped"
    findings_report["steps"]["xlsx_multisheet"] = {
        "status": xlsx_job.get("status"),
        "skipped_sheets": skipped,
        "sheets_summary": stats.get("sheets_summary", []),
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Step 3: Multi-Table ZIP Test
    # ─────────────────────────────────────────────────────────────────────────
    multi_zip_path = EXTRA_TESTS_DIR / "multi_table.zip"
    assert multi_zip_path.exists(), "extra_tests/multi_table.zip must exist"
    with multi_zip_path.open("rb") as f:
        zip_resp = api_call(
            "POST",
            "/api/v1/datasets/upload",
            files={"file": ("multi_table.zip", f.read(), "application/zip")},
            headers=analyst_auth,
        )
    zip_data = zip_resp.json()
    assert zip_data.get("is_multi_table") is True
    assert zip_data.get("table_count") == 3
    findings_report["steps"]["multi_table_zip"] = {
        "table_count": zip_data.get("table_count"),
        "tables": [t["dataset_name"] for t in zip_data.get("tables", [])],
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Step 4: Upload Main Files for Company A (purchase_orders, shipments, vendors, sales)
    # ─────────────────────────────────────────────────────────────────────────
    uploaded_sources: dict[str, str] = {}
    main_files = [
        ("purchase_orders", SYNTHETIC_DIR / "purchase_orders.csv"),
        ("shipments", SYNTHETIC_DIR / "shipments.csv"),
        ("vendors", SYNTHETIC_DIR / "vendors.csv"),
        ("sales", SYNTHETIC_DIR / "sales.csv"),
    ]
    for dname, fpath in main_files:
        assert fpath.exists(), f"File {fpath} must exist"
        with fpath.open("rb") as f:
            up_resp = api_call(
                "POST",
                "/api/v1/datasets/upload",
                files={"file": (fpath.name, f.read(), "text/csv")},
                data={"dataset_name": dname},
                headers=analyst_auth,
            )
        up_data = up_resp.json()
        uploaded_sources[dname] = up_data["source_id"]

    findings_report["steps"]["main_uploads"] = list(uploaded_sources.keys())

    # ─────────────────────────────────────────────────────────────────────────
    # Step 5: Column Mappings (Analyst can map & confirm)
    # ─────────────────────────────────────────────────────────────────────────
    mappings = {
        "purchase_orders": {
            "po_number": "order_id",
            "po_date": "order_ts",
            "promised_arrival": "promised_ts",
            "vendor_code": "supplier_id",
            "sku": "product_id",
            "warehouse_code": "warehouse_id",
            "qty_ordered": "quantity",
            "unit_cost": "price",
        },
        "shipments": {
            "shipment_ref": "shipment_id",
            "po_number": "order_id",
            "ship_date": "event_timestamp",
            "arrival_date": "delivered_ts",
            "carrier_name": "carrier",
            "route": "route",
            "delivery_status": "status",
        },
        "vendors": {
            "vendor_code": "supplier_id",
            "vendor_name": "supplier_name",
            "country": "region",
        },
        "sales": {
            "sale_date": "order_ts",
            "sku": "product_id",
            "units_sold": "quantity",
        },
    }
    for dname, col_map in mappings.items():
        api_call(
            "PUT",
            f"/api/v1/datasets/{dname}/confirm-mapping",
            json={"mappings": col_map, "description": f"Kaveri Foods mapping for {dname}"},
            headers=analyst_auth,
        )

    findings_report["steps"]["mappings"] = "CONFIRMED_BY_ANALYST"

    # ─────────────────────────────────────────────────────────────────────────
    # Step 6: Relationship Preview & Approval
    # ─────────────────────────────────────────────────────────────────────────
    rel_preview_resp = api_call("POST", "/api/v1/datasets/relationships/preview", json={
        "links": [
            {
                "left_source_id": uploaded_sources["purchase_orders"],
                "left_key": "po_number",
                "right_source_id": uploaded_sources["shipments"],
                "right_key": "po_number",
                "relationship": "order_shipment",
            },
            {
                "left_source_id": uploaded_sources["purchase_orders"],
                "left_key": "vendor_code",
                "right_source_id": uploaded_sources["vendors"],
                "right_key": "vendor_code",
                "relationship": "supplier_order",
            },
        ],
    }, headers=analyst_auth)
    preview_data = rel_preview_resp.json()
    proposal_id = preview_data["proposal_id"]
    findings_report["steps"]["relationship_preview"] = preview_data["links"]

    # Analyst approves relationship
    api_call(
        "POST",
        f"/api/v1/datasets/relationships/{proposal_id}/approve",
        json={"reason": "FK alignment verified for POs and Shipments"},
        headers=analyst_auth,
    )
    findings_report["steps"]["relationship_approval"] = "APPROVED_BY_ANALYST"

    # ─────────────────────────────────────────────────────────────────────────
    # Step 7: Capability Assessment
    # ─────────────────────────────────────────────────────────────────────────
    cap_resp = api_call("GET", "/api/v1/projects/project-kaveri_foods/capabilities", headers=viewer_auth)
    capabilities = cap_resp.json()
    findings_report["capabilities"] = capabilities
    assert capabilities["features"]["delay_prediction"]["status"] == "AVAILABLE_WITH_LIMITATIONS"
    assert capabilities["features"]["dependency_graph"]["status"] == "AVAILABLE"

    # ─────────────────────────────────────────────────────────────────────────
    # Step 8: Pipeline Execution Through API (Fix 1)
    # ─────────────────────────────────────────────────────────────────────────
    run_resp = api_call(
        "POST",
        "/api/v1/projects/project-kaveri_foods/pipeline/run",
        headers=analyst_auth,
    )
    run_data = run_resp.json()
    assert run_data.get("status") in ("COMPLETED", "RUNNING")
    findings_report["steps"]["pipeline_run"] = {
        "id": run_data.get("id"),
        "status": run_data.get("status"),
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Step 9: Data-Quality Report (Fix 2)
    # ─────────────────────────────────────────────────────────────────────────
    dq_resp = api_call("GET", "/api/v1/projects/project-kaveri_foods/quality-report", headers=viewer_auth)
    dq_report = dq_resp.json()
    findings_report["data_quality"] = dq_report
    summary = dq_report.get("summary", {})

    assert summary.get("exact_duplicate_rows") == 30
    assert summary.get("negative_values") == 18
    assert summary.get("invalid_dates") == 15
    assert summary.get("blank_required_values") == 40
    assert summary.get("unknown_foreign_keys") == 10
    assert summary.get("orphan_rows") == 25
    assert summary.get("open_records") == 150

    # ─────────────────────────────────────────────────────────────────────────
    # Step 10: Extract Pipeline Findings (Anomalies, Drivers, Incidents, Recs)
    # ─────────────────────────────────────────────────────────────────────────
    anom_resp = api_call("GET", "/api/v1/anomalies", headers=viewer_auth)
    anom_items = anom_resp.json().get("items", [])
    findings_report["top_anomalies"] = anom_items[:10]

    inc_resp = api_call("GET", "/api/v1/incidents", headers=viewer_auth)
    inc_items = inc_resp.json().get("items", [])
    findings_report["incidents_count"] = len(inc_items)
    if inc_items:
        findings_report["first_incident_detail"] = inc_items[0]

    recs_resp = api_call("GET", "/api/v1/recommendations", headers=viewer_auth)
    recs_items = recs_resp.json().get("items", [])
    findings_report["recommendations_count"] = len(recs_items)
    findings_report["recommendations"] = recs_items[:5]

    # Verify recommendations do not recommend route diversification for product drivers
    for rec in recs_items:
        drv_type = str((rec.get("payload") or {}).get("driver_type", "")).lower()
        act = str(rec.get("action", "")).lower()
        if "product" in drv_type:
            assert "route diversification" not in act, f"Product driver recommendation must not recommend route diversification: {act}"

    # Extract delay drivers and leakage handling from pipeline run steps
    pipeline_result = run_data.get("result", {})
    delay_step = next((s for s in pipeline_result.get("steps", []) if s.get("name") == "delay_prediction"), None)
    if delay_step and "result" in delay_step:
        delay_res = delay_step["result"]
        findings_report["top_drivers"] = delay_res.get("top_drivers", [])
        findings_report["leakage_handling"] = delay_res.get("leakage_handling", {})

        # Verify exclusion of identifier columns from model features (Requirement 8)
        delay_features = delay_res.get("features", [])
        ident_overlap = {"order_id", "shipment_id", "source"} & set(delay_features)
        assert not ident_overlap, f"Identifier columns found in model features: {ident_overlap}"

        # Verify change-point fields on top drivers (Requirement 6)
        for drv in findings_report["top_drivers"]:
            assert "estimated_start_date" in drv
            assert "pre_change_rate" in drv
            assert "post_change_rate" in drv
            assert drv.get("status") == "UNVERIFIED"

    # ─────────────────────────────────────────────────────────────────────────
    # Step 11: Supply Graph Verification (Fix 4)
    # ─────────────────────────────────────────────────────────────────────────
    graph_resp = api_call("GET", "/api/v1/projects/project-kaveri_foods/graph/aggregated?clustering_threshold=150", headers=viewer_auth)
    graph_data = graph_resp.json()
    graph_nodes = graph_data.get("nodes", [])
    from collections import Counter
    node_types = Counter(n.get("type") for n in graph_nodes)

    assert node_types["Supplier"] in (24, 25), f"Expected 24 or 25 suppliers, got {node_types['Supplier']}"
    assert node_types["Product"] == 60, f"Expected 60 products, got {node_types['Product']}"
    assert node_types["Carrier"] == 4, f"Expected 4 carriers, got {node_types['Carrier']}"
    assert node_types["Warehouse"] == 4, f"Expected 4 warehouses, got {node_types['Warehouse']}"
    assert node_types.get("Route/Lane", 0) > 0, f"Expected Route/Lane nodes from mapped route role, got {node_types.get('Route/Lane')}"

    # Verify no hardcoded ProcessStage nodes (Requirement 2)
    assert all(n.get("type") != "ProcessStage" for n in graph_nodes), "ProcessStage nodes with hardcoded constants must not exist"
    assert all("process_stage" not in n.get("id") for n in graph_nodes)

    # Verify real weighted edges (Requirement 1)
    graph_edges = graph_data.get("edges", [])
    edge_types = Counter(e.get("type") for e in graph_edges)
    assert edge_types["SUPPLIES"] > 0, f"Expected SUPPLIES edges, got {edge_types}"
    assert edge_types["USES"] > 0, f"Expected USES edges via order-shipment join, got {edge_types}"
    assert edge_types["STORED_AT"] > 0, f"Expected STORED_AT edges, got {edge_types}"
    assert edge_types["SERVES"] > 0, f"Expected SERVES edges, got {edge_types}"

    # Verify planted-fault connectivity: faulty supplier V017 is connected to products and carriers
    v017_edges = [e for e in graph_edges if e.get("from") == "supplier:V017"]
    assert len(v017_edges) >= 2, f"Expected at least 2 edges for faulty supplier V017, got {len(v017_edges)}"
    v017_targets = {e.get("type"): e.get("to") for e in v017_edges}
    assert "SUPPLIES" in v017_targets, "Supplier V017 must connect to products via SUPPLIES"
    assert "USES" in v017_targets, "Supplier V017 must connect to carriers via USES"

    # Verify node health logic: never UNHEALTHY with negative z-score (Requirement 3)
    for n in graph_nodes:
        z = n.get("metrics_vs_peer_baseline", {}).get("z_score", 0)
        if z <= 0:
            assert n.get("health_status") == "HEALTHY", f"Node {n.get('id')} with negative z-score {z} labeled {n.get('health_status')}"
        if n.get("health_status") == "UNHEALTHY":
            assert z > 0, f"Unhealthy node {n.get('id')} has non-positive z-score {z}"

    # Verify node sources list real contributing datasets (Requirement 4)
    assert all(n.get("source") for n in graph_nodes)
    assert any("purchase_orders" in n.get("source", "") for n in graph_nodes)

    unhealthy = [n for n in graph_nodes if n.get("health_status") == "UNHEALTHY" or n.get("health") in ("PROBLEM", "WATCH")]
    top_10_unhealthy = sorted(
        unhealthy,
        key=lambda x: x.get("metrics_vs_peer_baseline", {}).get("z_score", 0),
        reverse=True
    )[:10]
    cleaned_unhealthy = [{k: v for k, v in n.items() if k != "time_series"} for n in top_10_unhealthy]

    findings_report["graph"] = {
        "node_count": len(graph_nodes),
        "edge_count": len(graph_edges),
        "node_counts_by_type": dict(node_types),
        "edge_counts_by_type": dict(edge_types),
        "supplier_count_note": f"{node_types['Supplier']} suppliers ({'24 known vendors + 1 unknown vendor code from POs' if node_types['Supplier'] == 25 else '24 known vendors'})",
        "top_10_unhealthy_nodes": cleaned_unhealthy,
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Step 12: Schema Drift & Units (Fix 7)
    # ─────────────────────────────────────────────────────────────────────────
    batch2_path = EXTRA_TESTS_DIR / "purchase_orders_2026_batch2.csv"
    assert batch2_path.exists(), "extra_tests/purchase_orders_2026_batch2.csv must exist"
    with batch2_path.open("rb") as f:
        api_call(
            "POST",
            "/api/v1/datasets/upload",
            files={"file": ("purchase_orders_2026_batch2.csv", f.read(), "text/csv")},
            data={"dataset_name": "purchase_orders"},
            headers=analyst_auth,
        )

    drift_report = api_call("GET", "/api/v1/datasets/purchase_orders/drift", headers=viewer_auth).json()
    assert drift_report.get("null_rate_unit") == "fraction"
    assert "units" in drift_report
    findings_report["drift_report"] = drift_report

    # ─────────────────────────────────────────────────────────────────────────
    # Step 13: Role Enforcement Tests with Exact Status Codes (Fix 6 & Requirement 10)
    # ─────────────────────────────────────────────────────────────────────────
    role_results: dict[str, dict[str, Any]] = {"viewer": {}, "analyst": {}, "reviewer": {}, "admin": {}}

    # Viewer negative tests
    v_up = client.post("/api/v1/datasets/upload", data={"dataset_name": "illegal"}, headers=viewer_auth)
    assert v_up.status_code == 403
    role_results["viewer"]["upload_dataset"] = {"allowed": False, "status_code": v_up.status_code}

    v_map = client.put("/api/v1/datasets/purchase_orders/confirm-mapping", json={"mappings": {}}, headers=viewer_auth)
    assert v_map.status_code == 403
    role_results["viewer"]["confirm_mapping"] = {"allowed": False, "status_code": v_map.status_code}

    v_pipe = client.post("/api/v1/projects/project-kaveri_foods/pipeline/run", headers=viewer_auth)
    assert v_pipe.status_code == 403
    role_results["viewer"]["run_pipeline"] = {"allowed": False, "status_code": v_pipe.status_code}

    v_conf = client.post("/api/v1/hypotheses/dummy-h/confirm", json={"reason": "test"}, headers=viewer_auth)
    assert v_conf.status_code == 403
    role_results["viewer"]["confirm_hypothesis"] = {"allowed": False, "status_code": v_conf.status_code}

    from sqlalchemy import select
    from src.core.repository import ActionRow, ApprovalRow, RecommendationRow, IncidentRow, DatasetVersionRow
    from datetime import datetime, timezone
    real_rec_id = f"real-rec-{uuid.uuid4().hex[:8]}"
    real_appr_id = f"real-appr-{uuid.uuid4().hex[:8]}"
    real_act_id = f"real-act-{uuid.uuid4().hex[:8]}"
    with test_env["repo"].sessions() as session:
        existing_inc = session.scalar(select(IncidentRow).where(IncidentRow.company_id == "kaveri_foods"))
        if existing_inc:
            target_inc_id = existing_inc.id
        elif inc_items:
            target_inc_id = inc_items[0]["id"]
        else:
            dv = session.scalar(select(DatasetVersionRow))
            target_inc_id = f"inc-{uuid.uuid4().hex[:8]}"
            session.add(IncidentRow(
                id=target_inc_id, dataset_version_id=dv.id if dv else "dv-test",
                source="test", title="Test Incident", occurred_at=datetime.now(timezone.utc),
                company_id="kaveri_foods"
            ))
            session.flush()

        session.add(RecommendationRow(
            id=real_rec_id, incident_id=target_inc_id, source="test", action="Mitigate delay",
            payload={"action": "Mitigate delay"}, company_id="kaveri_foods"
        ))
        session.flush()
        session.add(ApprovalRow(
            id=real_appr_id, recommendation_id=real_rec_id, status="PENDING",
            payload={"requested_action": "Mitigate delay"}, company_id="kaveri_foods"
        ))
        session.flush()
        session.add(ActionRow(
            id=real_act_id, recommendation_id=real_rec_id, approval_id=real_appr_id,
            source="test", status="PENDING_APPROVAL", dry_run=True,
            company_id="kaveri_foods", payload={"status": "PENDING_APPROVAL"}
        ))
        session.flush()
        session.commit()

    # Action approval on real action returns strictly 403 for viewer (never 404)
    v_act = client.post(f"/api/v1/actions/{real_act_id}/approve", json={"reason": "test"}, headers=viewer_auth)
    assert v_act.status_code == 403, f"Expected 403 for viewer action approval, got {v_act.status_code}"
    role_results["viewer"]["approve_action"] = {"allowed": False, "status_code": v_act.status_code}

    v_usr = client.post("/api/v1/auth/users", json={"username": "illegal", "role": "viewer"}, headers=viewer_auth)
    assert v_usr.status_code == 403
    role_results["viewer"]["manage_users"] = {"allowed": False, "status_code": v_usr.status_code}

    # Analyst allowed & negative tests
    a_conf = client.post("/api/v1/hypotheses/dummy-h/confirm", json={"reason": "test"}, headers=analyst_auth)
    assert a_conf.status_code == 403
    role_results["analyst"]["confirm_hypothesis"] = {"allowed": False, "status_code": a_conf.status_code}

    # Action approval on real action returns strictly 403 for analyst (never 404)
    a_act = client.post(f"/api/v1/actions/{real_act_id}/approve", json={"reason": "test"}, headers=analyst_auth)
    assert a_act.status_code == 403, f"Expected 403 for analyst action approval, got {a_act.status_code}"
    role_results["analyst"]["approve_action"] = {"allowed": False, "status_code": a_act.status_code}

    # Reviewer approves the real action -> 200
    r_act = client.post(f"/api/v1/actions/{real_act_id}/approve", json={"reason": "Approved by reviewer"}, headers=reviewer_auth)
    assert r_act.status_code == 200, f"Expected 200 for reviewer action approval, got {r_act.status_code}"
    role_results["reviewer"]["approve_action"] = {"allowed": True, "status_code": r_act.status_code}

    a_usr = client.post("/api/v1/auth/users", json={"username": "illegal", "role": "viewer"}, headers=analyst_auth)
    assert a_usr.status_code == 403
    role_results["analyst"]["manage_users"] = {"allowed": False, "status_code": a_usr.status_code}

    a_ks = client.post("/api/v1/system/kill-switch", json={"enabled": True, "reason": "test"}, headers=analyst_auth)
    assert a_ks.status_code == 403
    role_results["analyst"]["toggle_kill_switch"] = {"allowed": False, "status_code": a_ks.status_code}

    from datetime import datetime, timezone
    from src.risk.hypotheses import HypothesisCase, EvidenceLedger, LedgerEvidence
    from src.core.schemas import HypothesisStatus
    inc_rows = client.get("/api/v1/incidents", headers=analyst_auth).json().get("items", [])
    if inc_rows:
        h_create = client.post("/api/v1/hypotheses", json={
            "incident_id": inc_rows[0]["id"],
            "statement": "Reviewer confirmation test hypothesis",
            "source": "test",
            "record_refs": []
        }, headers=analyst_auth)
        if h_create.status_code == 201:
            h_id = h_create.json()["id"]
            # Premature confirmation without evidence is rejected with 409
            unverified_confirm = client.post(f"/api/v1/hypotheses/{h_id}/confirm", json={"rationale": "Premature confirmation attempt"}, headers=reviewer_auth)
            assert unverified_confirm.status_code == 409

            # When supported by evidence ledger, reviewer confirmation succeeds
            supported_case = HypothesisCase(
                id=h_id, statement="Reviewer confirmation test hypothesis", source="test",
                status=HypothesisStatus.SUPPORTED,
                ledger=EvidenceLedger(supporting=[
                    LedgerEvidence(evidence_id="ev-1", classification="supporting", source="test", record_refs=["PO-1"], observed_at=datetime.now(timezone.utc), strength=0.9, description="Supporting delay log"),
                    LedgerEvidence(evidence_id="ev-2", classification="supporting", source="test", record_refs=["PO-2"], observed_at=datetime.now(timezone.utc), strength=0.9, description="Corroborating carrier log"),
                ]),
            )
            with test_env["repo"].sessions() as session:
                existing = session.get(HypothesisRow, h_id)
                existing.status = supported_case.status.value
                existing.payload = supported_case.model_dump(mode="json")
                session.commit()

            r_conf = client.post(f"/api/v1/hypotheses/{h_id}/confirm", json={"reason": "Confirmed by reviewer with audit trail", "rationale": "Confirmed by reviewer with audit trail"}, headers=reviewer_auth)
            assert r_conf.status_code == 200
            assert r_conf.json()["status"] == "CONFIRMED"
            role_results["reviewer"]["confirm_hypothesis"] = {"allowed": True, "status_code": r_conf.status_code}

    r_usr = client.post("/api/v1/auth/users", json={"username": "illegal", "role": "viewer"}, headers=reviewer_auth)
    assert r_usr.status_code == 403
    role_results["reviewer"]["manage_users"] = {"allowed": False, "status_code": r_usr.status_code}

    r_ks = client.post("/api/v1/system/kill-switch", json={"enabled": True, "reason": "test"}, headers=reviewer_auth)
    assert r_ks.status_code == 403
    role_results["reviewer"]["toggle_kill_switch"] = {"allowed": False, "status_code": r_ks.status_code}

    # Admin allowed tests
    adm_usr = client.get("/api/v1/auth/users", headers=admin_auth)
    assert adm_usr.status_code == 200
    role_results["admin"]["manage_users"] = {"allowed": True, "status_code": adm_usr.status_code}

    adm_ks = client.post("/api/v1/system/kill-switch", json={"enabled": False, "reason": "Admin test"}, headers=admin_auth)
    assert adm_ks.status_code == 200
    role_results["admin"]["toggle_kill_switch"] = {"allowed": True, "status_code": adm_ks.status_code}

    findings_report["roles_verified"] = role_results

    # ─────────────────────────────────────────────────────────────────────────
    # Step 14: Company B Isolation Verification
    # ─────────────────────────────────────────────────────────────────────────
    comp_b_resp = api_call("POST", "/api/v1/companies", json={
        "company_id": "competitor_corp",
        "company_name": "Competitor Corp",
        "admin_username": "comp_b_admin",
        "admin_email": "admin@competitor.com",
        "admin_password": "CompBPassword123!",
    }, headers=admin_auth)

    comp_b_login = api_call("POST", "/api/v1/auth/login", json={
        "username_or_email": "comp_b_admin",
        "password": "CompBPassword123!",
        "company_id": "competitor_corp",
    })
    comp_b_token = comp_b_login.json()["token"]
    comp_b_auth = {"Authorization": f"Bearer {comp_b_token}", "X-Company-Id": "competitor_corp"}

    comp_b_file = EXTRA_TESTS_DIR / "company_b_orders.json"
    assert comp_b_file.exists(), "extra_tests/company_b_orders.json must exist"
    with comp_b_file.open("rb") as f:
        api_call(
            "POST",
            "/api/v1/datasets/upload",
            files={"file": ("company_b_orders.json", f.read(), "application/json")},
            data={"dataset_name": "company_b_orders"},
            headers=comp_b_auth,
        )

    comp_b_datasets = client.get("/api/v1/datasets", headers=comp_b_auth).json()
    b_names = [d["dataset_name"] for d in comp_b_datasets.get("items", [])]
    assert "purchase_orders" not in b_names
    assert "company_b_orders" in b_names

    comp_a_datasets = client.get("/api/v1/datasets", headers=analyst_auth).json()
    a_names = [d["dataset_name"] for d in comp_a_datasets.get("items", [])]
    assert "company_b_orders" not in a_names
    assert "purchase_orders" in a_names

    cross_access = client.get("/api/v1/datasets", headers={
        "Authorization": f"Bearer {analyst_token}",
        "X-Company-Id": "competitor_corp",
    })
    assert cross_access.status_code == 403

    findings_report["isolation"] = {
        "company_a_datasets_count": len(a_names),
        "company_b_datasets_count": len(b_names),
        "cross_company_token_blocked_status": cross_access.status_code,
    }

    # Save real acceptance test output to JSON for report generation
    out_path = Path("docs/acceptance_findings.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings_report, indent=2, default=str), encoding="utf-8")
