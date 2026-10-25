"""Synthetic evidence fixtures validate risk controls, not claims about real causes."""
from datetime import datetime, timezone
import zipfile

import pytest

from src.core.schemas import HypothesisStatus
from src.explainability.shap_explainer import EXPLANATION_NOTE
from src.risk.engine import prioritize
from src.risk.hypotheses import HypothesisCase, HypothesisService, LedgerEvidence
from src.risk.investigator import investigate


def evidence(classification="supporting", strength=0.9):
    return LedgerEvidence(classification=classification, source="synthetic_fixture", record_refs=["synthetic-id"],
                          observed_at=datetime.now(timezone.utc), strength=strength,
                          description="synthetic test evidence")


def test_status_transitions_require_evidence_and_reviewer_for_confirmation():
    service = HypothesisService(minimum_supporting_evidence=2, minimum_evidence_strength=0.7)
    case = HypothesisCase(statement="synthetic hypothesis", source="synthetic")
    case.ledger.add(evidence())
    with pytest.raises(ValueError, match="Insufficient evidence"):
        service.transition(case, HypothesisStatus.SUPPORTED, user_id="synthetic", role="analyst", rationale="synthetic")
    case.ledger.add(evidence())
    service.transition(case, HypothesisStatus.SUPPORTED, user_id="synthetic", role="analyst", rationale="synthetic")
    with pytest.raises(PermissionError):
        service.transition(case, HypothesisStatus.CONFIRMED, user_id="synthetic", role="analyst", rationale="synthetic")
    service.transition(case, HypothesisStatus.CONFIRMED, user_id="synthetic-reviewer", role="reviewer", rationale="synthetic human review")
    assert case.status == HypothesisStatus.CONFIRMED
    assert len(case.review_history) == 2


def test_insufficient_evidence_path_is_explicit():
    service = HypothesisService(minimum_supporting_evidence=2, minimum_evidence_strength=0.8)
    case = HypothesisCase(statement="synthetic hypothesis", source="synthetic")
    assert service.assess(case) == "Insufficient evidence"
    assert case.ledger.missing


def test_risk_engine_omits_uncalibrated_delay_probability():
    result = prioritize(delay_probability=0.99, probability_calibrated=False, affected_order_count=5,
                        supplier_exposure=2, evidence_strength=0.7, evidence_age_hours=10,
                        recurrence_count=1, missing_data_fraction=0.1)
    assert result["factors"]["delay_probability"]["available"] is False
    assert result["factors"]["delay_probability"]["weighted_contribution"] is None
    assert "factors" in result and result["priority_index"] is not None


def test_investigator_verifies_synthetic_audited_record_and_returns_unverified_hypotheses(tmp_path):
    archive = tmp_path / "synthetic_olist.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("olist_orders_dataset.csv",
                    "order_id,order_status,order_purchase_timestamp,order_estimated_delivery_date,order_delivered_customer_date,order_delivered_carrier_date\n"
                    "synthetic-order-1,delivered,2020-01-01,2020-01-02,2020-01-03,2020-01-02\n")
    item = {"dataset": "olist", "evidence_ref": "synthetic-order-1", "feature": "actual_delivery_days", "observed_value": 2}
    result = investigate(item, root=tmp_path)
    assert result["status"] == "evidence_found"
    assert result["evidence"]["record_refs"] == ["synthetic-order-1"]
    assert result["lifecycle_status"] == "UNVERIFIED"
    assert result["alternatives"]
    assert "feature contribution, not proven cause" in result["limitations"][1]


def test_investigator_rejects_mismatched_synthetic_observation(tmp_path):
    archive = tmp_path / "synthetic_olist.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("olist_orders_dataset.csv",
                    "order_id,order_status,order_purchase_timestamp,order_estimated_delivery_date,order_delivered_customer_date\n"
                    "synthetic-order-1,delivered,2020-01-01,2020-01-02,2020-01-03\n")
    result = investigate({"dataset": "olist", "record_ref": "synthetic-order-1", "feature": "actual_delivery_days",
                          "observed_value": 999}, root=tmp_path)
    assert result["status"] == "Insufficient evidence"


def test_explanation_disclaimer_is_fixed_text():
    assert EXPLANATION_NOTE == "feature contribution, not proven cause"
