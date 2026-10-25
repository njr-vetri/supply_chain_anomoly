"""Synthetic recommendation and what-if checks; scenario outputs are not claims."""
import pytest

from src.recommendations.engine import recommend
from src.recommendations.whatif import compare_scenarios


def test_rule_recommendations_include_evidence_assumptions_uncertainty_constraints():
    result = recommend(evidence_refs=["synthetic-evidence"], seller_recurrence=3, shipment_status_known=False,
                       monitoring_recurrence=1, calibrated_delay_probability=0.9, probability_calibrated=True)
    assert {item["action"] for item in result} == {
        "investigate seller pattern", "verify shipment status", "increase monitoring", "notify operator"}
    for item in result:
        assert item["evidence_refs"] == ["synthetic-evidence"]
        assert item["rationale"] and item["assumptions"] and item["uncertainty"] and item["constraints"]
        assert item["dry_run"] and item["human_approval_required"]


def test_recommendation_requires_evidence_for_triggered_rule():
    with pytest.raises(ValueError, match="evidence"):
        recommend(evidence_refs=[], seller_recurrence=3)


def test_whatif_is_explicitly_hypothetical_and_requires_calibrated_baseline():
    no_evidence = compare_scenarios(affected_order_count=10, calibrated_delay_probability=0.5,
                                   probability_calibrated=False, scenarios=[])
    assert no_evidence["status"] == "Insufficient evidence"
    result = compare_scenarios(affected_order_count=10, calibrated_delay_probability=0.5,
        probability_calibrated=True, scenarios=[{"name": "synthetic-mitigation", "assumed_relative_probability_reduction": 0.2,
                                                 "assumptions": ["synthetic assumption"]}])
    assert result["label"] == "HYPOTHETICAL"
    assert all(row["label"] == "HYPOTHETICAL" for row in result["scenarios"])
    assert result["scenarios"][1]["expected_delayed_orders"] == 4
