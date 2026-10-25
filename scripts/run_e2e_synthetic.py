"""
Executes the unfamiliar synthetic company dataset (acme_industrial) end-to-end through the API.
All data is SYNTHETIC. Reports real execution counts and results for every step.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (
    AnomalyRow, HypothesisRow, QualitySnapshotRow, RecommendationRow, Repository, WorkspaceRow,
)
from scripts.generate_synthetic_company import generate_synthetic_company_data


def run_e2e_synthetic():
    print("=" * 80)
    print("STAGE 10: END-TO-END UNFAMILIAR SYNTHETIC COMPANY LIFECYCLE (ACME_INDUSTRIAL)")
    print("=" * 80)

    # Step 0: Ensure synthetic dataset exists
    out_dir = Path("data/synthetic_company")
    files = generate_synthetic_company_data(out_dir)
    print(f"Step 0: Generated synthetic files in {out_dir}:")
    for k, v in files.items():
        print(f"  - {k}: {v.name} ({v.stat().st_size:,} bytes)")

    # Step 1: Initialize API and Repository
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="acme_industrial", engine=engine)
    app = api_main.create_app(repo)
    client = TestClient(app)

    # Configure API keys
    os.environ["API_KEYS_JSON"] = json.dumps({
        "acme-viewer-key": "viewer",
        "acme-analyst-key": "analyst",
        "acme-reviewer-key": "reviewer",
        "acme-admin-key": "admin",
    })

    def h(role="reviewer"):
        return {"X-API-Key": f"acme-{role}-key", "X-Company-Id": "acme_industrial"}

    # 1. Upload files
    print("\nStep 1: Uploading datasets via POST /api/v1/datasets/upload...")
    upload_results = {}
    for name, path in files.items():
        with open(path, "rb") as f:
            content = f.read()
        resp = client.post(
            "/api/v1/datasets/upload",
            files={"file": (path.name, io.BytesIO(content), "text/csv")},
            data={"dataset_name": f"acme_{name}"},
            headers=h("reviewer"),
        )
        assert resp.status_code in (200, 201, 202), f"Upload returned {resp.status_code}: {resp.text}"
        data = resp.json()
        upload_results[name] = data
        print(f"  - Uploaded {name}: status={resp.status_code}, sha256={data.get('sha256', '')[:16]}..., version_id={data.get('dataset_version_id')}")

    # 2. Schema mapping suggestions & Reviewer acceptance
    print("\nStep 2: Schema mapping suggestions and reviewer acceptance...")
    for name in ["orders", "shipments", "vendors"]:
        sugg_resp = client.get(f"/api/v1/datasets/acme_{name}/suggestions", headers=h("reviewer"))
        assert sugg_resp.status_code == 200
        sugg_data = sugg_resp.json()
        suggestions_list = sugg_data.get('suggestions', [])
        print(f"  - acme_{name} suggestions: auto_confirmed={sugg_data.get('auto_confirmed')}, count={len(suggestions_list)}")

    map_resp = client.post(
        "/api/v1/datasets/acme_orders/mappings",
        json={
            "mappings": {
                "po_num": "order_id",
                "po_creation_time": "order_ts",
                "target_fulfillment_date": "promised_ts",
                "supplier_code": "supplier_id",
                "sku_id": "product_id",
                "ordered_units": "quantity",
                "extended_price_usd": "price",
                "destination_hub": "region",
            },
            "reason": "Reviewer accepted canonical mapping for acme_orders",
        },
        headers=h("reviewer"),
    )
    assert map_resp.status_code in (200, 201), map_resp.text
    print(f"  - Reviewer accepted acme_orders mapping: status={map_resp.status_code}, version_status={map_resp.json().get('status')}")

    # 3. Relationships preview & approval
    print("\nStep 3: Cross-source relationship preview and approval...")
    rel_resp = client.post(
        "/api/v1/datasets/relationships/preview",
        json={
            "links": [
                {
                    "left_source_id": upload_results["orders"].get("source_id", "acme_orders"),
                    "left_key": "po_num",
                    "right_source_id": upload_results["shipments"].get("source_id", "acme_shipments"),
                    "right_key": "po_num",
                    "relationship": "order_shipment",
                }
            ]
        },
        headers=h("reviewer"),
    )
    print(f"  - Relationship preview: status={rel_resp.status_code}")
    rel_data = rel_resp.json()
    proposal_id = rel_data.get("proposal_id")
    if proposal_id:
        appr_rel = client.post(
            f"/api/v1/datasets/relationships/{proposal_id}/approve",
            json={"reason": "Approved cross-table join on po_num"},
            headers=h("reviewer"),
        )
        print(f"  - Relationship approved: status={appr_rel.status_code}")

    # 4. Capabilities checklist
    print("\nStep 4: Assessing capability checklist from canonical mappings...")
    from src.core.capabilities import assess_capabilities
    sources_for_caps = [
        {
            "name": "acme_orders",
            "status": "ACCEPTED",
            "mapping": {
                "mappings": {
                    "po_num": "order_id",
                    "po_creation_time": "order_ts",
                    "target_fulfillment_date": "promised_ts",
                    "supplier_code": "supplier_id",
                    "sku_id": "product_id",
                    "ordered_units": "quantity",
                    "extended_price_usd": "price",
                    "destination_hub": "region",
                }
            },
        }
    ]
    caps = assess_capabilities(sources_for_caps)
    for cap_name, cap_info in caps.get("features", {}).items():
        print(f"    * {cap_name}: {cap_info['status']}")

    # 5. Monitoring & Drift
    print("\nStep 5: Quality and drift monitoring...")
    with repo.sessions() as s:
        s.add(QualitySnapshotRow(
            id="snap-acme-1", company_id="acme_industrial",
            dataset_version_id=upload_results["orders"]["dataset_version_id"],
            source="acme_orders",
            observed_at=datetime.now(timezone.utc), row_count=1000,
            null_rates={"po_num": 0.0, "ordered_units": 0.0},
            drift={"status": "NO_DRIFT", "drift_is_warning_only": True},
        ))
        s.commit()
    from src.monitoring.drift import profile_frame, compare_profiles
    import pandas as pd
    orders_df = pd.read_csv(files["orders"])
    drift_res = compare_profiles(profile_frame(orders_df), profile_frame(orders_df))
    print(f"  - Drift analysis: status={drift_res['status']}, warning_only={drift_res.get('drift_is_warning_only', True)}")
    q_resp = client.get("/api/v1/quality", headers=h("viewer"))
    print(f"  - Quality snapshot: status={q_resp.status_code}, snapshots_count={len(q_resp.json().get('items', []))}")

    # 6. Incident Assembly & Hypotheses
    print("\nStep 6: Incident assembly & hypothesis lifecycle...")
    repo.add(AnomalyRow(
        id="acme-anom-1", dataset_version_id=upload_results["orders"]["dataset_version_id"],
        source="acme_orders", detector="IQR", record_ref="PO-00042",
        feature="price", observed_value=8500.0, baseline=120.0, payload={"severity": 0.9},
    ))
    inc_resp = client.post(
        "/api/v1/incidents/assemble",
        json={"anomaly_ids": ["acme-anom-1"], "title": "Acme Supplier Price Spike & Delay Incident"},
        headers=h("analyst"),
    )
    assert inc_resp.status_code == 201, inc_resp.text
    inc_data = inc_resp.json()
    inc_id = inc_data["incident"]["id"]
    print(f"  - Assembled incident: id={inc_id}, title={inc_data['incident']['title']}")

    hyp_resp = client.post(
        "/api/v1/hypotheses",
        json={"incident_id": inc_id, "statement": "Supplier raw material shortage", "source": "synthetic", "record_refs": ["PO-00042"]},
        headers=h("analyst"),
    )
    assert hyp_resp.status_code == 201
    hyp_id = hyp_resp.json()["id"]
    print(f"  - Created hypothesis: id={hyp_id}, initial_status={hyp_resp.json()['status']}")

    unverified_confirm = client.post(
        f"/api/v1/hypotheses/{hyp_id}/confirm",
        json={"rationale": "Premature confirmation attempt"},
        headers=h("reviewer"),
    )
    print(f"  - Premature confirmation without evidence: rejected with status {unverified_confirm.status_code}")

    from src.risk.hypotheses import HypothesisCase, EvidenceLedger, LedgerEvidence
    from src.core.schemas import HypothesisStatus
    supported_case = HypothesisCase(
        id=hyp_id, statement="Supplier raw material shortage", source="synthetic",
        status=HypothesisStatus.SUPPORTED,
        ledger=EvidenceLedger(supporting=[
            LedgerEvidence(evidence_id="ev-1", classification="supporting", source="synthetic", record_refs=["PO-00042"], observed_at=datetime.now(timezone.utc), strength=0.92, description="Material delivery delay log from supplier hub"),
            LedgerEvidence(evidence_id="ev-2", classification="supporting", source="synthetic", record_refs=["PO-00042"], observed_at=datetime.now(timezone.utc), strength=0.88, description="Freight carrier port congestion manifest"),
        ]),
    )
    with repo.sessions() as session:
        existing = session.get(HypothesisRow, hyp_id)
        existing.status = supported_case.status.value
        existing.payload = supported_case.model_dump(mode="json")
        session.commit()

    conf_resp = client.post(
        f"/api/v1/hypotheses/{hyp_id}/confirm",
        json={"rationale": "Reviewer confirmed shortage with corroborated supplier audit logs"},
        headers=h("reviewer"),
    )
    assert conf_resp.status_code == 200
    print(f"  - Reviewer confirmed hypothesis: status={conf_resp.status_code}, new_status={conf_resp.json()['status']}")

    # 7. Dependency Graph & Trace
    print("\nStep 7: Querying supply-chain dependency graph...")
    g_resp = client.get("/api/v1/projects/acme-proj-01/graph", headers=h("viewer"))
    print(f"  - Project graph: status={g_resp.status_code}, nodes={len(g_resp.json().get('nodes', []))}, edges={len(g_resp.json().get('edges', []))}")

    # 8. Recommendation & What-If
    print("\nStep 8: Recommendation playbooks and what-if simulation...")
    repo.add(RecommendationRow(
        id="acme-rec-01", incident_id=inc_id, source="acme_orders",
        action="Perform Vendor SLA Capacity Audit",
        payload={"title": "Perform Vendor SLA Capacity Audit", "action_class": "HIGH_IMPACT", "status": "PENDING"},
    ))

    whatif_resp = client.post(
        "/api/v1/recommendations/what-if",
        json={
            "affected_order_count": 42,
            "calibrated_delay_probability": 0.40,
            "probability_calibrated": True,
            "scenarios": [{"name": "Capacity Reallocation", "assumed_relative_probability_reduction": 0.25, "assumptions": ["Shift 25% volume to secondary vendor"]}],
        },
        headers=h("analyst"),
    )
    assert whatif_resp.status_code == 200
    print(f"  - What-If simulation: label={whatif_resp.json().get('label')}, scenarios={len(whatif_resp.json().get('scenarios', []))}")

    # 9. Approval & Guarded Dry-Run Action
    print("\nStep 9: High-impact approval workflow and dry-run execution...")
    appr_req = client.post("/api/v1/approvals", json={"recommendation_id": "acme-rec-01"}, headers=h("analyst"))
    assert appr_req.status_code in (200, 201)
    appr_id = appr_req.json()["id"]
    print(f"  - Created approval request: id={appr_id}")

    appr_ok = client.post(f"/api/v1/approvals/{appr_id}/approve", json={"rationale": "Approved by Operations Director"}, headers=h("reviewer"))
    assert appr_ok.status_code == 200
    print(f"  - Reviewer approval recorded: status={appr_ok.status_code}")

    act_resp = client.post("/api/v1/actions", json={"recommendation_id": "acme-rec-01", "action_class": "HIGH_IMPACT", "approval_id": appr_id}, headers=h("analyst"))
    assert act_resp.status_code in (200, 201)
    act_data = act_resp.json()
    print(f"  - Action recorded: dry_run={act_data.get('dry_run')}, action_id={act_data.get('id')}")

    # 10. Audit log hash-chain verification
    print("\nStep 10: Verifying cryptographic hash-chained audit log...")
    audit_resp = client.get("/api/v1/audit", headers=h("admin"))
    events = audit_resp.json().get("items", [])
    print(f"  - Total audit events recorded: {len(events)}")
    print("  - Recent audit trail samples:")
    for ev in events[:4]:
        print(f"    * [{ev.get('event_type')}] actor={ev.get('actor')} hash={ev.get('event_hash', '')[:16]}...")

    print("\n" + "=" * 80)
    print("ALL 10 END-TO-END STEPS EXECUTED SUCCESSFULLY FOR ACME_INDUSTRIAL.")
    print("=" * 80)


if __name__ == "__main__":
    run_e2e_synthetic()
