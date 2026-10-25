"""Synthetic fixtures test Stage 5 mechanics only; they are not performance evidence."""
from datetime import datetime, timedelta, timezone
import random

from src.network.canonical_graph import build_canonical_graph, downstream_trace, upstream_trace
from src.risk.drivers import analyze_drivers
from src.risk.incident_assembly import assemble_incident
from src.risk.scoring import CompanyRiskConfig, score_company_risk


def _driver_fixture(planted: bool) -> tuple[list[dict], list[str]]:
    rows = []
    affected = []
    random_cases = set(random.Random(42).sample(range(100), 10))
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for index in range(100):
        supplier = "supplier_faulty" if index < 30 else "supplier_peer"
        is_affected = (index < 24 or index in {30, 31, 32, 33}) if planted else index in random_cases
        row = {"event_id": f"evt-{index}", "source_record_ref": f"synthetic:{index}",
               "supplier_id": supplier, "carrier_id": f"carrier-{index % 2}",
               "product_id": f"product-{index % 4}", "region": f"region-{index % 2}",
               "mode": f"mode-{index % 2}", "event_timestamp": start + timedelta(days=index)}
        rows.append(row)
        if is_affected:
            affected.append(row["source_record_ref"])
    return rows, affected


def test_planted_supplier_driver_is_ranked_with_support_and_correction():
    rows, affected = _driver_fixture(planted=True)
    result = analyze_drivers(rows, affected, min_affected=5, min_baseline=5, min_effect_size=0.1)
    top = result["drivers"][0]
    assert top["dimension"] == "supplier"
    assert top["value"] == "supplier_faulty"
    assert top["confident_driver"] is True
    assert top["adjusted_p_value"] <= 0.05
    assert top["interpretation"] == "correlation, not proof"
    assert result["change_point"] is not None


def test_no_driver_data_does_not_produce_confident_driver():
    rows, affected = _driver_fixture(planted=False)
    result = analyze_drivers(rows, affected, min_affected=5, min_baseline=5, min_effect_size=0.1)
    assert not result["confident_driver"]
    assert all(not item["confident_driver"] for item in result["drivers"])


def test_established_faulty_supplier_trace_reaches_its_downstream_orders():
    rows = [{"event_id": "synthetic-1", "source_record_ref": "synthetic:row-1", "supplier_id": "faulty",
             "order_id": "order-1", "product_id": "product-1", "event_timestamp": "2025-01-01T00:00:00Z"},
            {"event_id": "synthetic-2", "source_record_ref": "synthetic:row-2", "supplier_id": "faulty",
             "order_id": "order-2", "product_id": "product-2", "event_timestamp": "2025-01-02T00:00:00Z"}]
    built = build_canonical_graph(rows, source="synthetic", mapping_version="synthetic-map-v1",
                                  source_hash="synthetic-hash")
    supplier = "supplier:synthetic:faulty"
    traced = downstream_trace(built["graph"], supplier)
    assert {node["id"] for node in traced["nodes"] if node["id"].startswith("order:")} == {
        "order:synthetic:order-1", "order:synthetic:order-2"}
    assert all(edge["flag"] == "ESTABLISHED" for edge in traced["edges"])
    assert all({"source", "provenance", "validity_period", "source_record_ref", "flag"} <= edge.keys()
               for edge in built["edges"])
    assert upstream_trace(built["graph"], "order:synthetic:order-1")["label"] == "hypothesis"


def test_incident_assembly_keeps_anomaly_fact_and_prediction_separate():
    result = assemble_incident(source="synthetic", anomalies=[{"record_ref": "synthetic:row-1",
        "feature": "delivery_days", "observed_value": 30, "baseline": 5, "detector": "rule"}],
        predictions=[{"record_refs": ["synthetic:row-2"], "target": "delay", "value": True,
                      "model_version_id": "synthetic-model-v1"}])
    assert result["incident"].record_refs == ["synthetic:row-1", "synthetic:row-2"]
    assert [item.evidence_type for item in result["evidence"]] == ["observed_anomaly", "prediction_output"]
    assert all(item.status.value == "UNVERIFIED" for item in result["hypotheses"])


def test_risk_uses_qualitative_fallback_without_calibrated_likelihood():
    result = score_company_risk(config=CompanyRiskConfig(), likelihood=0.8, likelihood_calibrated=False,
        impact=0.6, evidence_strength=0.7, uncertainty=0.2)
    assert result["score"] is None
    assert result["severity"] is None
    assert result["qualitative_rating"] == "HIGHLY_UNCERTAIN"
    assert result["factors"]["likelihood"]["available"] is False
