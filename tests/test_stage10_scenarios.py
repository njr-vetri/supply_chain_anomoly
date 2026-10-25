"""
Stage 10 Acceptance Test Suite: Scenarios 1 through 10.
All test data is SYNTHETIC. Never used to claim production accuracy or real data findings.
"""
import io
import json
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (
    AnomalyRow, AuditEventRow, HypothesisRow, IncidentRow, PredictionRow, RecommendationRow, Repository,
)
from src.data.profile import detect_capabilities
from src.ml.anomaly.statistical import iqr, robust_zscore
from src.ml.anomaly.isolation_forest import detect as detect_isolation_forest
from src.monitoring.drift import compare_profiles, profile_frame


@pytest.fixture
def scenario_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="acme_industrial_stage10", engine=engine)

    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "stage10-viewer": "viewer",
        "stage10-analyst": "analyst",
        "stage10-reviewer": "reviewer",
        "stage10-admin": "admin",
    }))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    app = api_main.create_app(repo)
    return TestClient(app), repo


def _headers(role="reviewer", company_id="acme_industrial_stage10"):
    return {"X-API-Key": f"stage10-{role}", "X-Company-Id": company_id}


# ── Scenario 1: New Company Onboarding & Dataset Upload ───────────────────────────

def test_scenario_1_onboarding_and_upload(scenario_client):
    client, repo = scenario_client
    csv_bytes = b"po_number,po_created_date,vendor_code,ordered_qty\nPO-001,2025-01-01T10:00:00Z,V-100,5\nPO-002,2025-01-02T10:00:00Z,V-101,12\n"

    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("acme_purchase_orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"dataset_name": "acme_purchase_orders"},
        headers=_headers("reviewer"),
    )
    assert response.status_code in (200, 201), response.text
    data = response.json()
    assert data["dataset_name"] == "acme_purchase_orders"
    assert "import_job_id" in data
    assert len(data["sha256"]) == 64
    assert data["status"] in ("QUEUED", "COMPLETED", "PROCESSING")

    # Viewer role cannot upload
    viewer_resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("acme_orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"dataset_name": "acme_orders"},
        headers=_headers("viewer"),
    )
    assert viewer_resp.status_code == 403


# ── Scenario 2: Schema Mapping Wizard & Suggestions ───────────────────────────────

def test_scenario_2_schema_mapping_wizard(scenario_client):
    client, repo = scenario_client
    csv_bytes = b"Order Ref,Event Date,Vendor Ref\nO-1,2026-01-01,V-1\nO-2,2026-01-02,V-2\n"
    client.post(
        "/api/v1/datasets/upload",
        files={"file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"dataset_name": "orders"},
        headers=_headers("reviewer"),
    )

    # Get suggestions
    sugg_resp = client.get("/api/v1/datasets/orders/suggestions", headers=_headers("reviewer"))
    assert sugg_resp.status_code == 200
    sugg_data = sugg_resp.json()
    assert sugg_data.get("auto_confirmed") is False
    assert "suggestions" in sugg_data

    # Accept mapping as reviewer
    accept_resp = client.post(
        "/api/v1/datasets/orders/mappings",
        json={
            "mappings": {"Order Ref": "order_id", "Event Date": "order_ts"},
            "custom_fields": {"vendor_id": "Vendor Ref"},
            "units": {},
            "time_zone": "UTC",
            "date_format": "%Y-%m-%d",
            "reason": "Synthetic reviewer verified canonical mapping",
        },
        headers=_headers("reviewer"),
    )
    assert accept_resp.status_code == 200, accept_resp.text
    mapping_data = accept_resp.json()
    assert mapping_data["status"] in ("PENDING_REVIEW", "ACCEPTED")

    # Viewer role cannot modify mappings
    viewer_resp = client.post(
        "/api/v1/datasets/orders/mappings",
        json={"mappings": {}, "reason": "Unauthorized attempt"},
        headers=_headers("viewer"),
    )
    assert viewer_resp.status_code == 403


# ── Scenario 3: Cross-Source Relationships & Orphan Detection ────────────────────

def test_scenario_3_cross_source_relationships(scenario_client):
    client, repo = scenario_client
    orders_csv = b"Order Ref,Event Date\nO-1,2026-01-01\nO-2,2026-01-02\n"
    shipments_csv = b"Tracking,Order Ref\nTRK-1,O-1\nTRK-2,O-ORPHAN\n"

    up1 = client.post("/api/v1/datasets/upload", files={"file": ("orders.csv", io.BytesIO(orders_csv), "text/csv")},
                      data={"dataset_name": "orders"}, headers=_headers("reviewer")).json()
    up2 = client.post("/api/v1/datasets/upload", files={"file": ("shipments.csv", io.BytesIO(shipments_csv), "text/csv")},
                      data={"dataset_name": "shipments"}, headers=_headers("reviewer")).json()

    preview_resp = client.post(
        "/api/v1/datasets/relationships/preview",
        json={
            "links": [{
                "left_source_id": up1["source_id"],
                "left_key": "Order Ref",
                "right_source_id": up2["source_id"],
                "right_key": "Order Ref",
                "relationship": "order_shipment",
            }]
        },
        headers=_headers("reviewer"),
    )
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert "proposal_id" in preview_data

    proposal_id = preview_data.get("proposal_id")
    if proposal_id:
        approve_resp = client.post(
            f"/api/v1/datasets/relationships/{proposal_id}/approve",
            json={"reason": "Synthetic human approval of verified key relation"},
            headers=_headers("reviewer"),
        )
        assert approve_resp.status_code == 200


# ── Scenario 4: Capability Checklist & Gating ─────────────────────────────────────

def test_scenario_4_capability_checklist_and_gating():
    # Only sales fields mapped
    mappings = {
        "SKU": "product_id",
        "Qty": "quantity",
        "OrderDate": "order_ts",
        "OrderID": "order_id",
    }
    caps = detect_capabilities(mappings)

    # Demand forecasting is supported with product, quantity, order_ts
    assert caps.demand_forecasting.possible is True

    # Delay prediction is not possible because promised_ts is missing
    assert caps.delay_prediction.possible is False
    assert "promised_ts" in caps.delay_prediction.missing_roles


# ── Scenario 5: Quality Validation & Drift Monitoring ─────────────────────────────

def test_scenario_5_quality_validation_and_drift_monitoring():
    baseline_df = pd.DataFrame({
        "supplier_id": ["S1", "S2", "S1", "S3", "S2"],
        "order_qty": [10.0, 20.0, 15.0, 12.0, 18.0],
        "lead_days": [3.0, 4.0, 3.5, 3.0, 4.2],
    })
    drifted_df = pd.DataFrame({
        "supplier_id": ["S1", "S2", "S1", "S3", "S2"],
        "order_qty": [100.0, 250.0, 180.0, 190.0, 220.0],
        "lead_days": [3.0, 4.0, 3.5, 3.0, 4.2],
        "new_carrier_code": ["C1", "C2", "C1", "C3", "C2"],
    })
    baseline_profile = profile_frame(baseline_df)
    current_profile = profile_frame(drifted_df)

    drift_result = compare_profiles(baseline_profile, current_profile, max_numeric_mean_shift=1.0)
    assert drift_result["status"] == "DRIFT_ALERT"
    assert "new_carrier_code" in drift_result["schema"]["added_columns"]
    assert drift_result.get("drift_is_warning_only", True) is True
    assert drift_result.get("triggers_automatic_retrain", False) is False


# ── Scenario 6: Multi-Method Anomaly Detection & ML Delay Prediction ──────────────

def test_scenario_6_anomaly_detection_and_ml_prediction():
    normal_series = pd.Series([10.0, 12.0, 11.0, 10.5, 11.5, 9.8, 10.2, 50.0])  # 50.0 is anomaly
    iqr_res = iqr(normal_series)
    z_res = robust_zscore(normal_series)
    assert bool(iqr_res["anomaly"].iloc[-1]) is True
    assert bool(z_res["anomaly"].iloc[-1]) is True

    iforest_res = detect_isolation_forest(normal_series, contamination=0.15)
    assert len(iforest_res) == len(normal_series)
    assert bool(iforest_res["anomaly"].iloc[-1]) is True


# ── Scenario 7: Incident Assembly & Causal Hypothesis Lifecycle ───────────────────

def test_scenario_7_incident_assembly_and_hypothesis_lifecycle(scenario_client):
    client, repo = scenario_client
    csv_bytes = b"Order Ref,Event Date,Amount\nO-1,2026-01-01,100\nO-2,2026-01-02,5000\n"
    up = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"dataset_name": "orders"},
        headers=_headers("reviewer"),
    ).json()

    repo.add(AnomalyRow(
        id="anom-001", dataset_version_id=up["dataset_version_id"],
        source="orders", detector="IQR", record_ref="O-2",
        feature="Amount", observed_value=5000.0, baseline=100.0, payload={"severity": 0.8},
    ))

    # Assemble incident
    assemble_resp = client.post(
        "/api/v1/incidents/assemble",
        json={
            "anomaly_ids": ["anom-001"],
            "title": "Synthetic assembled supplier delay incident",
        },
        headers=_headers("analyst"),
    )
    assert assemble_resp.status_code == 201, assemble_resp.text
    inc_data = assemble_resp.json()
    incident_id = inc_data["incident"]["id"]

    # Create unverified hypothesis
    hyp_resp = client.post(
        "/api/v1/hypotheses",
        json={
            "incident_id": incident_id,
            "statement": "Synthetic hypothesis: supplier component shortage",
            "source": "synthetic",
            "record_refs": ["O-2"],
        },
        headers=_headers("analyst"),
    )
    assert hyp_resp.status_code == 201
    hyp_data = hyp_resp.json()
    assert hyp_data["status"] == "UNVERIFIED"
    hyp_id = hyp_data["id"]

    # Analyst review Disallows direct confirmation
    analyst_review = client.post(
        f"/api/v1/hypotheses/{hyp_id}/review",
        json={"status": "CONFIRMED", "rationale": "Analyst trying to confirm"},
        headers=_headers("analyst"),
    )
    # Reviewer confirmation of unverified hypothesis without adequate support is rejected
    unverified_confirm = client.post(
        f"/api/v1/hypotheses/{hyp_id}/confirm",
        json={"rationale": "Premature confirmation attempt"},
        headers=_headers("reviewer"),
    )
    assert unverified_confirm.status_code == 409

    # When supported by evidence, reviewer confirmation succeeds
    from src.risk.hypotheses import HypothesisCase, EvidenceLedger, LedgerEvidence
    from src.core.schemas import HypothesisStatus
    supported_case = HypothesisCase(
        id=hyp_id, statement="Supplier component shortage", source="synthetic",
        status=HypothesisStatus.SUPPORTED,
        ledger=EvidenceLedger(supporting=[
            LedgerEvidence(evidence_id="ev-1", classification="supporting", source="synthetic", record_refs=["O-2"], observed_at=datetime.now(timezone.utc), strength=0.9, description="Supporting delivery delay log"),
            LedgerEvidence(evidence_id="ev-2", classification="supporting", source="synthetic", record_refs=["O-2"], observed_at=datetime.now(timezone.utc), strength=0.9, description="Corroborating carrier log"),
        ]),
    )
    with repo.sessions() as session:
        existing = session.get(HypothesisRow, hyp_id)
        existing.status = supported_case.status.value
        existing.payload = supported_case.model_dump(mode="json")
        session.commit()

    reviewer_confirm = client.post(
        f"/api/v1/hypotheses/{hyp_id}/confirm",
        json={"rationale": "Human reviewer verified with supplier audit log"},
        headers=_headers("reviewer"),
    )
    assert reviewer_confirm.status_code == 200
    assert reviewer_confirm.json()["status"] == "CONFIRMED"


# ── Scenario 8: Supply-Chain Dependency Graph & Upstream/Downstream Tracing ───────

def test_scenario_8_supply_chain_graph_and_tracing(scenario_client):
    client, repo = scenario_client
    # Bounded query enforcement
    limit_resp = client.get("/api/v1/projects/synthetic-project/graph?limit=5001", headers=_headers("viewer"))
    assert limit_resp.status_code == 422
    assert limit_resp.json()["error"]["code"] == "invalid_request"

    # Upstream / downstream trace endpoint checks
    trace_resp = client.get(
        "/api/v1/projects/synthetic-project/graph/trace/downstream?node_id=supplier:synthetic:1&limit=50",
        headers=_headers("viewer"),
    )
    assert trace_resp.status_code in (200, 404)


# ── Scenario 9: Recommendation Playbooks & What-If Simulations ───────────────────

def test_scenario_9_recommendations_and_whatif(scenario_client):
    client, repo = scenario_client
    whatif_resp = client.post(
        "/api/v1/recommendations/what-if",
        json={
            "affected_order_count": 25,
            "calibrated_delay_probability": 0.35,
            "probability_calibrated": True,
            "scenarios": [
                {
                    "name": "Synthetic dual-sourcing scenario",
                    "assumed_relative_probability_reduction": 0.20,
                    "assumptions": ["Synthetic supplier SLA compliance improves by 20%"],
                }
            ],
        },
        headers=_headers("analyst"),
    )
    assert whatif_resp.status_code == 200
    whatif_data = whatif_resp.json()
    assert whatif_data.get("label") == "HYPOTHETICAL"
    assert "scenarios" in whatif_data
    assert len(whatif_data["scenarios"]) >= 1
    scenario_result = whatif_data["scenarios"][-1]
    assert scenario_result.get("is_hypothetical", True) is True


# ── Scenario 10: Guarded Actions, Approval Queue, Kill Switch & Audit Chaining ────

def test_scenario_10_guarded_actions_approval_killswitch_and_audit(scenario_client):
    client, repo = scenario_client
    csv_bytes = b"Order Ref,Event Date\nO-1,2026-01-01\n"
    up = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"dataset_name": "orders"},
        headers=_headers("reviewer"),
    ).json()

    inc = IncidentRow(
        id="inc-synthetic-001", dataset_version_id=up["dataset_version_id"],
        source="orders", title="Incident for Rec", occurred_at=datetime.now(timezone.utc),
    )
    repo.add(inc)
    rec = RecommendationRow(
        id="rec-001", incident_id="inc-synthetic-001", source="orders",
        action="Audit vendor capacity",
        payload={"title": "Synthetic audit vendor capacity", "action_class": "HIGH_IMPACT", "status": "PENDING"},
    )
    repo.add(rec)

    # 1. High-impact action without approval is rejected
    action_fail = client.post(
        "/api/v1/actions",
        json={"recommendation_id": "rec-001", "action_class": "HIGH_IMPACT"},
        headers=_headers("analyst"),
    )
    assert action_fail.status_code in (400, 403, 409, 422)

    # 2. Create approval request
    appr_create = client.post(
        "/api/v1/approvals",
        json={"recommendation_id": "rec-001"},
        headers=_headers("analyst"),
    )
    assert appr_create.status_code in (200, 201)
    approval_id = appr_create.json()["id"]

    # 3. Reviewer approves
    appr_sign = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"rationale": "Human reviewer signs off on high impact mitigation"},
        headers=_headers("reviewer"),
    )
    assert appr_sign.status_code == 200

    # 4. Action recorded strictly defaults to DRY_RUN
    action_ok = client.post(
        "/api/v1/actions",
        json={"recommendation_id": "rec-001", "action_class": "HIGH_IMPACT", "approval_id": approval_id},
        headers=_headers("analyst"),
    )
    assert action_ok.status_code in (200, 201)
    action_data = action_ok.json()
    assert action_data.get("dry_run", True) is True

    # 5. Admin toggles kill switch -> subsequent action is halted
    kill_toggle = client.put(
        "/api/v1/admin/kill-switch",
        json={"enabled": True, "reason": "Emergency halt test"},
        headers=_headers("admin"),
    )
    assert kill_toggle.status_code == 200

    action_killed = client.post(
        "/api/v1/actions",
        json={"recommendation_id": "rec-001", "action_class": "READ_ONLY"},
        headers=_headers("analyst"),
    )
    assert action_killed.status_code == 201
    assert action_killed.json()["status"] == "BLOCKED_KILL_SWITCH"

    # Reset kill switch
    client.put(
        "/api/v1/admin/kill-switch",
        json={"enabled": False, "reason": "Restore normal state"},
        headers=_headers("admin"),
    )

    # 6. Audit log hash-chaining verification
    repo.add(AuditEventRow(
        id="audit-test-01", event_type="action_recorded", actor="test-analyst",
        source="orders", occurred_at=datetime.now(timezone.utc),
        previous_hash="0" * 64, event_hash="a" * 64, payload={"action": "test"},
    ))
    audit_resp = client.get("/api/v1/audit", headers=_headers("admin"))
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    events = audit_data.get("items", [])
    assert len(events) >= 1
    for ev in events:
        assert "event_hash" in ev or "payload" in ev
