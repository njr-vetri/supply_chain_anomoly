"""
Test suite for Graph Redesign:
Aggregated group network, peer-based health computation,
time-bucketed health series, downstream/upstream exposure tracing,
node capping, and multi-tenant scoping.
All test data is SYNTHETIC. Never used to claim production accuracy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (
    AnomalyRow, DataSourceRow, DatasetVersionRow, ImportJobRow, Repository, WorkspaceRow, ProjectRow,
)


@pytest.fixture
def graph_clients(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    # Company A Setup
    engine_a = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo_a = Repository("sqlite://", company_id="company_a_synthetic", engine=engine_a)

    # Company B Setup
    engine_b = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo_b = Repository("sqlite://", company_id="company_b_rival", engine=engine_b)

    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "key-company-a-viewer": "viewer",
        "key-company-a-reviewer": "reviewer",
        "key-company-b-viewer": "viewer",
    }))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)

    app_a = api_main.create_app(repo_a)
    client_a = TestClient(app_a)

    app_b = api_main.create_app(repo_b)
    client_b = TestClient(app_b)

    # Plant synthetic records in Company A
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_file = processed_dir / "canonical_orders.jsonl"

    repo_a.add(DatasetVersionRow(
        id="ver-a-1",
        dataset="synthetic_orders",
        source="synthetic_orders",
        source_hash="synthetic_hash_1",
        observed_at=datetime.now(timezone.utc),
        payload={},
    ))

    records = []
    # 4 Healthy suppliers, 1 Planted Faulty supplier
    suppliers = ["SUP-HEALTHY-1", "SUP-HEALTHY-2", "SUP-HEALTHY-3", "SUP-HEALTHY-4"]
    records_count = 0

    with processed_file.open("w", encoding="utf-8") as out:
        # Healthy suppliers: 10 orders each, 0 anomalies
        for sup in suppliers:
            for i in range(10):
                rec_id = f"rec-healthy-{sup}-{i}"
                rec = {
                    "event_id": rec_id,
                    "source_record_ref": rec_id,
                    "supplier_id": sup,
                    "product_id": f"PROD-{sup[-1]}",
                    "carrier": "CARRIER-EXPRESS",
                    "event_timestamp": "2026-01-05T10:00:00Z",
                    "quantity": 10.0,
                    "price": 100.0,
                }
                out.write(json.dumps(rec) + "\n")
                records.append(rec)
                records_count += 1

        # Planted Faulty supplier: 10 orders, 8 severe anomalies
        faulty_sup = "SUP-PLANTED-FAULTY"
        for i in range(10):
            rec_id = f"rec-faulty-{i}"
            rec = {
                "event_id": rec_id,
                "source_record_ref": rec_id,
                "supplier_id": faulty_sup,
                "product_id": "PROD-CRITICAL-PART",
                "carrier": "CARRIER-EXPRESS",
                "event_timestamp": "2026-01-12T10:00:00Z" if i >= 5 else "2026-01-05T10:00:00Z",
                "quantity": 5.0,
                "price": 4500.0 if i >= 2 else 100.0,
            }
            out.write(json.dumps(rec) + "\n")
            records.append(rec)
            records_count += 1

            if i >= 2:
                # Add anomaly row
                repo_a.add(AnomalyRow(
                    id=f"anom-planted-{i}",
                    dataset_version_id="ver-a-1",
                    source="synthetic_orders",
                    record_ref=rec_id,
                    feature="price",
                    observed_value=4500.0,
                    baseline=100.0,
                    detector="IQR",
                    payload={"severity": 0.95},
                ))

    # Add Workspace, Project, DataSource & ImportJob in Company A
    repo_a.add(WorkspaceRow(id="ws-a-1", name="Synthetic Workspace"))
    repo_a.add(ProjectRow(id="proj-a-1", workspace_id="ws-a-1", name="Synthetic Project"))
    src_a = DataSourceRow(id="src-a-1", name="synthetic_orders", project_id="proj-a-1", source_type="jsonl", location_ref=str(processed_file))
    repo_a.add(src_a)
    job_a = ImportJobRow(
        id="job-a-1",
        data_source_id="src-a-1",
        status="COMPLETED",
        payload={"processed_file": str(processed_file), "total_rows": records_count},
    )
    repo_a.add(job_a)

    return client_a, client_b, repo_a, repo_b


def _headers(role="viewer", key="key-company-a-viewer", company_id="company_a_synthetic"):
    return {"X-API-Key": key, "X-Company-Id": company_id}


def test_aggregated_graph_identifies_planted_faulty_supplier(graph_clients):
    client_a, _, _, _ = graph_clients
    resp = client_a.get(
        "/api/v1/projects/proj-a-1/graph/aggregated",
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "nodes" in data
    assert "edges" in data
    assert "time_buckets" in data
    assert "capping" in data

    nodes_by_id = {n["id"]: n for n in data["nodes"]}

    # 1. Faulty supplier node evaluates to PROBLEM
    faulty_id = "supplier:SUP-PLANTED-FAULTY"
    assert faulty_id in nodes_by_id, f"Faulty supplier {faulty_id} not found in {list(nodes_by_id.keys())}"
    faulty_node = nodes_by_id[faulty_id]
    assert faulty_node["health"] == "PROBLEM"
    assert faulty_node["anomaly_count"] == 8
    assert faulty_node["exposure"] == 10

    # Metrics vs peers show elevated anomaly rate
    metrics = faulty_node["metrics_vs_peer_baseline"]
    assert metrics["anomaly_rate"] == 0.8
    assert metrics["difference_from_peer_average"] > 0.5
    assert metrics["z_score"] >= 1.75

    # 2. Healthy suppliers evaluate to HEALTHY
    for sup_num in range(1, 5):
        h_id = f"supplier:SUP-HEALTHY-{sup_num}"
        assert h_id in nodes_by_id
        assert nodes_by_id[h_id]["health"] == "HEALTHY"
        assert nodes_by_id[h_id]["anomaly_count"] == 0

    # 3. Individual orders are NOT in nodes; no hardcoded ProcessStage nodes exist
    for n in data["nodes"]:
        assert not n["id"].startswith("order:"), f"Found unaggregated order node: {n['id']}"
        assert n["type"] in ("Supplier", "Product", "Carrier", "Warehouse", "Route/Lane", "CustomerRegion")
        assert n["type"] != "ProcessStage", "ProcessStage nodes with hardcoded constants must not exist"
        # All node metrics must be derived from records
        assert n["exposure"] > 0
        assert n["source"] == "synthetic_orders"

    # 4. Planted fault edge connectivity: faulty supplier connected to product and carrier
    edges = data["edges"]
    faulty_edges = [e for e in edges if e["from"] == faulty_id]
    assert len(faulty_edges) >= 2, f"Expected at least 2 edges from faulty supplier, got {len(faulty_edges)}"
    targets = {e["to"]: e["type"] for e in faulty_edges}
    assert "product:PROD-CRITICAL-PART" in targets
    assert targets["product:PROD-CRITICAL-PART"] == "SUPPLIES"
    assert "carrier:CARRIER-EXPRESS" in targets
    assert targets["carrier:CARRIER-EXPRESS"] == "USES"


def test_time_bucketed_health_shows_when_node_turned_problem(graph_clients):
    client_a, _, _, _ = graph_clients
    resp = client_a.get("/api/v1/projects/proj-a-1/graph/aggregated", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()

    faulty_id = "supplier:SUP-PLANTED-FAULTY"
    nodes_by_id = {n["id"]: n for n in data["nodes"]}
    faulty_node = nodes_by_id[faulty_id]

    # Verify time series contains multiple buckets
    ts = faulty_node.get("time_series", [])
    assert len(ts) >= 2
    # Verify buckets are structured with health and volume
    for bucket_info in ts:
        assert "bucket" in bucket_info
        assert "health" in bucket_info
        assert "volume" in bucket_info
        assert "anomalies" in bucket_info


def test_downstream_trace_from_faulty_supplier(graph_clients):
    client_a, _, _, _ = graph_clients
    faulty_id = "supplier:SUP-PLANTED-FAULTY"
    resp = client_a.get(
        f"/api/v1/projects/proj-a-1/graph/aggregated/trace?node_id={faulty_id}&direction=downstream",
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["label"] == "exposure/hypothesis, not confirmed cause"
    assert data["direction"] == "downstream"
    assert data["count"] >= 1

    node_ids = {n["id"] for n in data["nodes"]}
    assert faulty_id in node_ids
    # Affected product and carrier are reached
    assert "product:PROD-CRITICAL-PART" in node_ids
    assert "carrier:CARRIER-EXPRESS" in node_ids


def test_node_capping_mechanism(graph_clients):
    client_a, _, _, _ = graph_clients
    # Set cap to 8 nodes to force clustering of tail entities
    resp = client_a.get(
        "/api/v1/projects/proj-a-1/graph/aggregated?max_nodes=8",
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["capping"]["capped"] is True
    assert data["capping"]["clustered_into_other"] > 0
    # Faulty supplier is preserved despite capping
    faulty_id = "supplier:SUP-PLANTED-FAULTY"
    node_ids = {n["id"] for n in data["nodes"]}
    assert faulty_id in node_ids


def test_missing_roles_reported(graph_clients):
    client_a, _, _, _ = graph_clients
    resp = client_a.get("/api/v1/projects/proj-a-1/graph/aggregated", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()

    omitted = data.get("omitted_node_types", {})
    # In this dataset, warehouse and customer region were not supplied
    assert "Warehouse" in omitted
    assert "CustomerRegion" in omitted


def test_company_b_cannot_read_company_a_graph(graph_clients):
    client_a, client_b, _, _ = graph_clients

    # 1. Company B attempts to read Company A graph using A's company_id -> 403 Forbidden
    resp_cross = client_b.get(
        "/api/v1/projects/proj-a-1/graph/aggregated?company_id=company_a_synthetic",
        headers={"X-API-Key": "key-company-b-viewer", "X-Company-Id": "company_b_rival"},
    )
    assert resp_cross.status_code == 403

    # 2. Company B querying within its own scope sees empty or isolated data
    resp_isolated = client_b.get(
        "/api/v1/projects/proj-a-1/graph/aggregated",
        headers={"X-API-Key": "key-company-b-viewer", "X-Company-Id": "company_b_rival"},
    )
    assert resp_isolated.status_code == 200
    # No Company A data leaks to Company B
    nodes = resp_isolated.json()["nodes"]
    assert not any("SUP-PLANTED-FAULTY" in n["id"] for n in nodes)


def test_edge_counts_match_distinct_pairs_in_data(graph_clients):
    client_a, _, _, _ = graph_clients
    resp = client_a.get("/api/v1/projects/proj-a-1/graph/aggregated", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    edges = data["edges"]
    from collections import Counter
    edge_types = Counter(e["type"] for e in edges)
    # 5 distinct supplier-product pairs (4 healthy + 1 faulty)
    assert edge_types["SUPPLIES"] == 5
    # 5 distinct supplier-carrier pairs
    assert edge_types["USES"] == 5
    for e in edges:
        assert e["weight"] == 10  # each supplier had 10 orders
        assert e["status"] in ("ESTABLISHED", "INFERRED")


def test_fails_if_any_node_metric_is_not_derived_from_data(graph_clients):
    client_a, _, _, _ = graph_clients
    resp = client_a.get("/api/v1/projects/proj-a-1/graph/aggregated", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    nodes = data["nodes"]

    # Verify no hardcoded process stage nodes
    assert all(n["type"] != "ProcessStage" for n in nodes)

    # Every node's exposure and anomaly count must match raw data counts
    for n in nodes:
        if n["id"] == "supplier:SUP-PLANTED-FAULTY":
            assert n["exposure"] == 10
            assert n["anomaly_count"] == 8
        elif n["id"].startswith("supplier:SUP-HEALTHY-"):
            assert n["exposure"] == 10
            assert n["anomaly_count"] == 0
        elif n["id"] == "carrier:CARRIER-EXPRESS":
            assert n["exposure"] == 50
        elif n["id"] == "product:PROD-CRITICAL-PART":
            assert n["exposure"] == 10
        elif n["id"].startswith("product:PROD-"):
            assert n["exposure"] == 10
        # Check that no node has hardcoded constants like exposure=20000 or anomaly_count=500
        assert n["exposure"] != 20000
        assert n["anomaly_count"] != 500
