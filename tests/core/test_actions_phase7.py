"""Synthetic action fixtures verify guardrails; no external actions are performed."""
from datetime import datetime, timezone

import pytest

from src.core.actions import (ActionClass, ActionExecutor, ActionRequest, ApprovalStatus,
                              ApprovalWorkflow, OutcomeTracker, compare_outcome)
from src.core.audit import AuditLog
from src.core.schemas import Outcome, Prediction


def local_settings(**overrides):
    settings = {"rate_limit_actions": 10, "rate_limit_window_seconds": 60,
                "circuit_breaker_failures": 2, "circuit_breaker_cooldown_seconds": 20,
                "retries": 0, "retry_backoff_seconds": 0, "max_retry_backoff_seconds": 1}
    settings.update(overrides)
    return settings


def request(action_class=ActionClass.LOW_IMPACT_REVERSIBLE, **kwargs):
    return ActionRequest(action_class=action_class, operation="synthetic_notify", idempotency_key="synthetic-key",
                         **kwargs)


def test_dry_run_is_not_success_and_does_not_call_handler(tmp_path):
    called = []
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=True,
                              handlers={"synthetic_notify": lambda payload: called.append(payload)})
    result = executor.execute(request(payload={"text": "synthetic request"}))
    assert result["status"] == "DRY_RUN" and result["success"] is False
    assert called == []


def test_kill_switch_blocks_mutation(tmp_path):
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=False, kill_switch=True,
                              handlers={"synthetic_notify": lambda payload: "executed"})
    result = executor.execute(request())
    assert result["status"] == "BLOCKED_KILL_SWITCH" and result["success"] is False


def test_high_impact_requires_recorded_approval(tmp_path):
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=False,
                              handlers={"synthetic_notify": lambda payload: "done"})
    with pytest.raises(PermissionError, match="approved reviewer"):
        executor.execute(request(ActionClass.HIGH_IMPACT))


def test_high_impact_accepts_only_approval_recorded_by_workflow(tmp_path):
    audit = AuditLog(tmp_path / "approval.jsonl")
    workflow = ApprovalWorkflow(audit)
    pending = workflow.request("synthetic-recommendation")
    approved = workflow.decide(pending.recommendation_id, decision=ApprovalStatus.APPROVED,
        reviewer_id="synthetic-reviewer", role="reviewer", reason="synthetic approval")
    executor = ActionExecutor(audit_log=audit, dry_run=False, approval_workflow=workflow,
                              handlers={"synthetic_notify": lambda payload: "done"})
    req = ActionRequest(action_class=ActionClass.HIGH_IMPACT, operation="synthetic_notify", idempotency_key="k",
                        recommendation_id="synthetic-recommendation", approval_id=approved.id, approval=approved)
    assert executor.execute(req)["success"]


def test_registered_handler_discards_untrusted_text(tmp_path):
    received = []
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=False,
                              handlers={"synthetic_notify": lambda payload: received.append(payload) or "done"})
    result = executor.execute(request(payload={"safe_value": 1, "instruction": "synthetic destroy everything"}))
    assert result["status"] == "EXECUTED" and result["success"] is True
    assert received == [{"safe_value": 1}]
    with pytest.raises(PermissionError, match="not registered"):
        executor.execute(ActionRequest(action_class=ActionClass.LOW_IMPACT_REVERSIBLE, operation="destroy",
                                       idempotency_key="other"))


def test_rate_limit_and_idempotency(tmp_path):
    current = [100.0]
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=False,
        settings=local_settings(rate_limit_actions=1), clock=lambda: current[0],
        handlers={"synthetic_notify": lambda payload: "done"})
    first = executor.execute(request())
    assert first["success"]
    assert executor.execute(request())["status"] == "DUPLICATE_SUPPRESSED"
    second = ActionRequest(action_class=ActionClass.LOW_IMPACT_REVERSIBLE, operation="synthetic_notify",
                           idempotency_key="synthetic-key-2")
    assert executor.execute(second)["status"] == "BLOCKED_RATE_LIMIT"


def test_retry_uses_backoff_and_reports_success_only_after_execution(tmp_path):
    attempts, delays = [0], []
    def handler(payload):
        attempts[0] += 1
        if attempts[0] == 1:
            raise RuntimeError("synthetic transient failure")
        return "synthetic completed"
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=False,
        settings=local_settings(retries=1, retry_backoff_seconds=0.5), sleeper=delays.append,
        handlers={"synthetic_notify": handler})
    result = executor.execute(request())
    assert result["status"] == "EXECUTED" and result["attempts"] == 2
    assert delays == [0.5]


def test_circuit_breaker_opens_after_configured_failures(tmp_path):
    executor = ActionExecutor(audit_log=AuditLog(tmp_path / "audit.jsonl"), dry_run=False,
        settings=local_settings(circuit_breaker_failures=1),
        handlers={"synthetic_notify": lambda payload: (_ for _ in ()).throw(RuntimeError("synthetic failure"))})
    failed = executor.execute(request())
    assert failed["status"] == "FAILED" and failed["success"] is False
    second = ActionRequest(action_class=ActionClass.LOW_IMPACT_REVERSIBLE, operation="synthetic_notify",
                           idempotency_key="different")
    assert executor.execute(second)["status"] == "BLOCKED_CIRCUIT_BREAKER"


def test_approval_pending_decision_and_audit(tmp_path):
    audit = AuditLog(tmp_path / "approval.jsonl")
    workflow = ApprovalWorkflow(audit)
    pending = workflow.request("synthetic-recommendation")
    assert pending.status == "pending"
    with pytest.raises(PermissionError):
        workflow.decide(pending.recommendation_id, decision=ApprovalStatus.APPROVED,
                        reviewer_id="synthetic-user", role="operator", reason="synthetic reason")
    approved = workflow.decide(pending.recommendation_id, decision=ApprovalStatus.APPROVED,
        reviewer_id="synthetic-reviewer", role="reviewer", reason="synthetic approval rationale")
    assert approved.status == "approved" and approved.reviewer_id == "synthetic-reviewer"
    assert [event.event_type for event in audit.read_all()] == ["approval_pending", "approval_approved"]


def test_outcome_comparison_is_linked_to_earlier_prediction():
    prediction = Prediction(target="synthetic", value=3, model_version_id="synthetic-v1", source="synthetic",
                            predicted_at=datetime.now(timezone.utc))
    outcome = Outcome(action_id="synthetic-action", source="synthetic", observed_at=datetime.now(timezone.utc),
                      facts={"observed": 4})
    comparison = compare_outcome(prediction, outcome, outcome_field="observed")
    assert comparison.comparable and comparison.difference == 1
    assert comparison.prediction_id == prediction.id and comparison.outcome_id == outcome.id


def test_outcome_tracker_records_and_audits_observation(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    tracker = OutcomeTracker(tmp_path / "outcomes.jsonl", audit)
    prediction = Prediction(target="synthetic", value=3, model_version_id="synthetic-v1", source="synthetic",
                            predicted_at=datetime.now(timezone.utc))
    outcome = Outcome(action_id="synthetic-action", source="synthetic", observed_at=datetime.now(timezone.utc),
                      facts={"observed": 3})
    result = tracker.record(prediction, outcome, outcome_field="observed")
    assert result.matched is True
    assert "outcome_observed" == audit.read_all()[0].event_type
    assert (tmp_path / "outcomes.jsonl").exists()


def test_outcome_comparison_rejects_non_temporal_prediction():
    prediction = Prediction(target="synthetic", value=3, model_version_id="synthetic-v1", source="synthetic",
                            predicted_at=datetime(2025, 1, 2, tzinfo=timezone.utc))
    outcome = Outcome(action_id="synthetic-action", source="synthetic", observed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                      facts={"observed": 3})
    result = compare_outcome(prediction, outcome, outcome_field="observed")
    assert result.comparable is False
