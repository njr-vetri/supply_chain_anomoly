"""Synthetic-only checks for schemas, settings and the audit chain."""
from datetime import datetime, timezone

import pytest

from src.core.audit import AuditLog
from src.core.config import load_settings
from src.core.schemas import Hypothesis, HypothesisStatus, Prediction, ReviewEntry


def test_schema_keeps_hypothesis_and_prediction_distinct() -> None:
    hypothesis = Hypothesis(statement="synthetic", source="synthetic", status=HypothesisStatus.UNVERIFIED)
    prediction = Prediction(target="synthetic_target", value=1, model_version_id="synthetic-v1", source="synthetic",
                            predicted_at=datetime.now(timezone.utc))
    assert hypothesis.status == HypothesisStatus.UNVERIFIED
    assert "status" not in prediction.model_dump()


def test_confirmation_requires_human_review_record() -> None:
    with pytest.raises(ValueError):
        Hypothesis(statement="synthetic", source="synthetic", status=HypothesisStatus.CONFIRMED)
    review = ReviewEntry(reviewer_id="synthetic-human-reviewer", previous_status=HypothesisStatus.SUPPORTED,
                         new_status=HypothesisStatus.CONFIRMED, rationale="synthetic review")
    model = Hypothesis(statement="synthetic", source="synthetic", status=HypothesisStatus.CONFIRMED,
                       review_history=[review])
    assert model.status == HypothesisStatus.CONFIRMED


def test_settings_are_loaded_from_yaml() -> None:
    settings = load_settings()
    assert settings.dry_run is True
    assert settings.kill_switch is False
    assert settings.operations.rate_limit_actions > 0


def test_audit_chain_appends_verifies_and_redacts(tmp_path) -> None:
    log = AuditLog(tmp_path / "synthetic.jsonl")
    first = log.append(event_type="synthetic", actor="test", details={"email": "not-real@example.test", "count": 2})
    log.append(event_type="synthetic2", actor="test")
    assert first.details["email"] == "[REDACTED]"
    assert log.verify()
    assert len(log.read_all()) == 2


def test_audit_detects_tampering(tmp_path) -> None:
    path = tmp_path / "synthetic.jsonl"
    log = AuditLog(path)
    log.append(event_type="synthetic", actor="test")
    path.write_text(path.read_text().replace('"actor":"test"', '"actor":"changed"'), encoding="utf-8")
    assert not log.verify()
