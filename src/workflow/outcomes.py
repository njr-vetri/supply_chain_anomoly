"""Verified action execution and later observed outcome comparisons."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.core.audit import AuditLog
from src.core.privacy import sanitize_for_log
from src.core.repository import ActionRow, ApprovalRow, OutcomeRow, PredictionRow, RecommendationRow, Repository
from src.core.schemas import Outcome


def record_execution_verification(repository: Repository, action_id: str, *, executed: bool,
                                  verified: bool, result: dict[str, Any] | None,
                                  actor: str, audit_log: AuditLog) -> dict[str, Any]:
    """Record whether an action really executed and whether that execution was verified."""
    action = repository.get(ActionRow, action_id)
    if action is None:
        raise KeyError("Action not found")
    if action.dry_run or action.status == "DRY_RUN":
        raise ValueError("A dry-run action cannot be recorded as executed")
    if action.status not in {"EXECUTED", "EXECUTED_PENDING_VERIFICATION", "EXECUTED_UNVERIFIED",
                             "EXECUTED_VERIFIED", "EXECUTION_FAILED"}:
        raise ValueError("Action must have a recorded execution attempt before verification")
    if not actor.strip():
        raise ValueError("Actor is required")
    action_class = (action.payload or {}).get("action_class")
    if action_class == "HIGH_IMPACT":
        approval = repository.get(ApprovalRow, action.approval_id) if action.approval_id else None
        if approval is None or approval.status.lower() != "approved":
            raise PermissionError("HIGH_IMPACT execution requires a recorded approved reviewer decision")
    if executed and result is None:
        raise ValueError("Executed actions require a structured result")
    now = datetime.now(timezone.utc)
    if not executed:
        status = "FAILED"
        action.status = "FAILED"
        execution_status = "FAILED"
    elif verified:
        status, execution_status = "EXECUTED_VERIFIED", "EXECUTED_VERIFIED"
        action.status = status
    else:
        status, execution_status = "EXECUTED_UNVERIFIED", "EXECUTION_UNVERIFIED"
        action.status = status
    action.payload = {**(action.payload or {}), "execution_status": execution_status,
                      "result": sanitize_for_log(result or {}), "verification_actor": actor,
                      "verified_at": now.isoformat() if verified and executed else None,
                      "execution_recorded_at": now.isoformat()}
    repository.add(action)
    audit_log.append(event_type="action_execution_verified" if verified and executed else "action_execution_recorded",
        actor=actor, source=action.source, record_refs=[action_id],
        details={"execution_status": execution_status, "result_recorded": result is not None})
    return {"action_id": action_id, "status": status, "execution_status": execution_status,
            "result": action.payload["result"], "recorded_at": now.isoformat()}


def record_observed_outcome(repository: Repository, *, action_id: str, source: str,
                            observed_at: datetime, facts: dict[str, Any], record_refs: list[str],
                            prediction_refs: list[str], recommendation_refs: list[str],
                            result: dict[str, Any] | None, audit_log: AuditLog,
                            actor: str, verified_alert_label: bool | None = None,
                            alert_was_raised: bool | None = None,
                            label_verified_by: str | None = None) -> dict[str, Any]:
    """Persist later observations and compare only to earlier recorded predictions/recommendations."""
    action = repository.get(ActionRow, action_id)
    if action is None:
        raise KeyError("Action not found")
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    label_values_provided = verified_alert_label is not None or alert_was_raised is not None
    if label_values_provided and (verified_alert_label is None or alert_was_raised is None
                                  or not label_verified_by or not label_verified_by.strip()):
        raise ValueError("Verified alert label and predicted alert state require a reviewer")
    predictions = []
    for prediction_id in prediction_refs:
        prediction_row = repository.get(PredictionRow, prediction_id)
        if prediction_row is None:
            raise KeyError("Prediction reference was not found")
        prediction_at = prediction_row.predicted_at
        if prediction_at.tzinfo is None:
            prediction_at = prediction_at.replace(tzinfo=timezone.utc)
        if prediction_at >= observed_at:
            raise ValueError("Outcome observations must occur after linked predictions")
        predictions.append(prediction_row)
    recommendations = []
    for recommendation_id in recommendation_refs:
        recommendation = repository.get(RecommendationRow, recommendation_id)
        if recommendation is None:
            raise KeyError("Recommendation reference was not found")
        created_at = recommendation.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at >= observed_at:
            raise ValueError("Outcome observations must occur after linked recommendations")
        recommendations.append(recommendation)
    comparisons = []
    for prediction in predictions:
        predicted = prediction.value
        observed = facts.get(prediction.target)
        comparable = observed is not None
        matched = None
        if comparable:
            try:
                matched = float(observed) == float(predicted)
            except (TypeError, ValueError):
                matched = str(observed) == str(predicted)
        comparisons.append({"type": "PREDICTION", "reference_id": prediction.id,
            "prediction_value": predicted, "observed_value": observed,
            "comparable": comparable, "matched": matched})
    for recommendation in recommendations:
        expected = (recommendation.payload or {}).get("expected_outcome")
        observed = facts.get(str((recommendation.payload or {}).get("outcome_field", "")))
        comparable = expected is not None and observed is not None
        matched = None
        if comparable:
            try:
                matched = float(expected) == float(observed)
            except (TypeError, ValueError):
                matched = str(expected) == str(observed)
        comparisons.append({"type": "RECOMMENDATION", "reference_id": recommendation.id,
            "expected_outcome": expected, "observed_value": observed,
            "comparable": comparable, "matched": matched,
            "limitation": "Outcome comparison does not establish recommendation causality."})
    safe_facts = sanitize_for_log(facts)
    outcome = Outcome(action_id=action_id, source=source, observed_at=observed_at,
        record_refs=list(dict.fromkeys(record_refs)), facts=safe_facts,
        recommendation_refs=recommendation_refs, prediction_refs=prediction_refs,
        execution_status=(action.payload or {}).get("execution_status", "UNKNOWN"),
        result=sanitize_for_log(result or {}),
        limitations=["Later outcomes can be associated with prior predictions and recommendations; association does not establish causality."])
    persisted = {**outcome.model_dump(mode="json"), "comparisons": comparisons,
        "verified_alert_label": verified_alert_label if label_values_provided else None,
        "alert_was_raised": alert_was_raised if label_values_provided else None,
        "verified_by": label_verified_by.strip() if label_values_provided else None}
    row = OutcomeRow(id=outcome.id, action_id=action_id,
        prediction_id=predictions[0].id if predictions else None, source=source,
        observed_at=observed_at, payload=persisted)
    repository.add(row)
    audit_log.append(event_type="outcome_recorded", actor=actor, source=source,
        record_refs=outcome.record_refs, details={"outcome_id": outcome.id,
        "prediction_refs": prediction_refs, "recommendation_refs": recommendation_refs,
        "execution_status": outcome.execution_status, "comparison_count": len(comparisons),
        "alert_label_verified": label_values_provided, "label_verifier": label_verified_by})
    return {"outcome": outcome, "comparisons": comparisons}
