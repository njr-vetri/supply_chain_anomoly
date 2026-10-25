"""Guarded action execution with approvals, dry-run, kill switch, limits and retries."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import json
import time
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.audit import AuditLog
from src.core.audit import _redact
from src.core.config import load_settings
from src.core.schemas import Approval, Outcome, OutcomeComparison, Prediction


class ActionClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOW_IMPACT_REVERSIBLE = "LOW_IMPACT_REVERSIBLE"
    HIGH_IMPACT = "HIGH_IMPACT"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionRequest(BaseModel):
    """Structured action intent. Free text is inert and excluded from executor payload."""
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action_class: ActionClass
    operation: str
    idempotency_key: str
    recommendation_id: str | None = None
    approval_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    approval: Approval | None = None


class ApprovalWorkflow:
    def __init__(self, audit_log: AuditLog):
        self.audit_log = audit_log
        self._records: dict[str, Approval] = {}

    def request(self, recommendation_id: str) -> Approval:
        approval = Approval(recommendation_id=recommendation_id, status=ApprovalStatus.PENDING.value, rationale="")
        self._records[recommendation_id] = approval
        self.audit_log.append(event_type="approval_pending", actor="system", record_refs=[recommendation_id],
                              details={"status": ApprovalStatus.PENDING.value})
        return approval

    def decide(self, recommendation_id: str, *, decision: ApprovalStatus, reviewer_id: str,
               role: str, reason: str) -> Approval:
        if role != "reviewer":
            raise PermissionError("Approval decisions require reviewer role")
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("Decision must be approved or rejected")
        if not reviewer_id.strip() or not reason.strip():
            raise ValueError("Reviewer and reason are required")
        current = self._records.get(recommendation_id)
        if current is None or current.status != ApprovalStatus.PENDING.value:
            raise ValueError("Approval is not pending")
        record = Approval(recommendation_id=recommendation_id, reviewer_id=reviewer_id,
                          status=decision.value, approved=decision == ApprovalStatus.APPROVED,
                          reviewed_at=datetime.now(timezone.utc), rationale=reason)
        self._records[recommendation_id] = record
        self.audit_log.append(event_type=f"approval_{decision.value}", actor=reviewer_id,
                              record_refs=[recommendation_id], details={"reason": reason, "status": decision.value})
        return record

    def get(self, recommendation_id: str) -> Approval | None:
        return self._records.get(recommendation_id)


class ActionExecutor:
    def __init__(self, *, audit_log: AuditLog, dry_run: bool | None = None, kill_switch: bool | None = None,
                 settings: dict[str, Any] | None = None, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep,
                 handlers: dict[str, Callable[[dict[str, Any]], Any]] | None = None,
                 approval_workflow: ApprovalWorkflow | None = None):
        loaded = load_settings()
        self.settings = settings or loaded.actions
        self.dry_run = loaded.operations.dry_run if dry_run is None else dry_run
        self.kill_switch = loaded.operations.kill_switch if kill_switch is None else kill_switch
        self.audit_log, self.clock, self.sleeper = audit_log, clock, sleeper
        # The operation registry is trusted application code, not inbound natural-language text.
        self.handlers = handlers or {}
        self.approval_workflow = approval_workflow
        self._timestamps: deque[float] = deque()
        self._idempotent: dict[str, dict[str, Any]] = {}
        self._failures = 0
        self._open_until = 0.0

    @staticmethod
    def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
        # Natural-language fields cannot define or alter an operation.
        ignored = {"text", "message", "prompt", "instruction", "instructions", "command"}
        return {key: value for key, value in payload.items() if key.lower() not in ignored}

    def execute(self, request: ActionRequest) -> dict[str, Any]:
        """Execute only an operation registered by trusted application code."""
        if not request.operation.strip() or not request.idempotency_key.strip():
            raise ValueError("Operation and idempotency key are required")
        if request.operation not in self.handlers:
            raise PermissionError("Operation is not registered by trusted application code")
        if request.action_class == ActionClass.HIGH_IMPACT:
            recorded = (self.approval_workflow.get(request.recommendation_id)
                        if self.approval_workflow is not None and request.recommendation_id else None)
            if (request.approval is None or recorded is None or
                    request.approval.status != ApprovalStatus.APPROVED.value or
                    recorded.status != ApprovalStatus.APPROVED.value or
                    not request.approval.reviewer_id or request.approval.id != recorded.id or
                    request.approval_id != recorded.id):
                raise PermissionError("HIGH_IMPACT action requires a recorded approved reviewer decision")
        if self.kill_switch and request.action_class != ActionClass.READ_ONLY:
            return {"status": "BLOCKED_KILL_SWITCH", "success": False, "action_id": request.action_id}
        if request.idempotency_key in self._idempotent:
            return {"status": "DUPLICATE_SUPPRESSED", "success": False,
                    "original_status": self._idempotent[request.idempotency_key]["status"],
                    "action_id": request.action_id}
        if self.dry_run:
            result = {"status": "DRY_RUN", "label": "DRY_RUN", "success": False,
                      "action_id": request.action_id, "operation": request.operation}
            self.audit_log.append(event_type="action_dry_run", actor="system", record_refs=[request.action_id],
                                  details={"operation": request.operation, "action_class": request.action_class.value})
            return result
        now = self.clock()
        if now < self._open_until:
            return {"status": "BLOCKED_CIRCUIT_BREAKER", "success": False, "action_id": request.action_id}
        window = self.settings["rate_limit_window_seconds"]
        while self._timestamps and now - self._timestamps[0] >= window:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.settings["rate_limit_actions"]:
            return {"status": "BLOCKED_RATE_LIMIT", "success": False, "action_id": request.action_id}
        self._timestamps.append(now)
        payload = self._safe_payload(request.payload)
        retries = self.settings["retries"]
        for attempt in range(retries + 1):
            try:
                value = self.handlers[request.operation](payload)
                result = {"status": "EXECUTED", "success": True, "action_id": request.action_id,
                          "operation": request.operation, "result": value, "attempts": attempt + 1}
                self._failures = 0
                self._idempotent[request.idempotency_key] = result
                self.audit_log.append(event_type="action_executed", actor="system", record_refs=[request.action_id],
                                      details={"operation": request.operation, "action_class": request.action_class.value,
                                               "attempts": attempt + 1})
                return result
            except Exception as exc:  # retry policy is bounded and recorded without logging exception payloads
                self._failures += 1
                if self._failures >= self.settings["circuit_breaker_failures"]:
                    self._open_until = self.clock() + self.settings["circuit_breaker_cooldown_seconds"]
                if attempt >= retries:
                    self.audit_log.append(event_type="action_failed", actor="system", record_refs=[request.action_id],
                                          details={"operation": request.operation, "error_type": type(exc).__name__})
                    return {"status": "FAILED", "success": False, "action_id": request.action_id,
                            "error_type": type(exc).__name__, "attempts": attempt + 1}
                delay = min(self.settings["retry_backoff_seconds"] * (2 ** attempt),
                            self.settings["max_retry_backoff_seconds"])
                self.sleeper(delay)


def compare_outcome(prediction: Prediction, outcome: Outcome, *, prediction_field: str | None = None,
                    outcome_field: str | None = None) -> OutcomeComparison:
    """Compare observed outcome to an earlier prediction without implying causation."""
    p_value = prediction.value
    o_value = outcome.facts.get(outcome_field) if outcome_field else outcome.facts
    if prediction_field and isinstance(p_value, dict):
        p_value = p_value.get(prediction_field)
    temporal_order_valid = prediction.predicted_at < outcome.observed_at
    comparable = temporal_order_valid and o_value is not None and isinstance(p_value, (int, float, str, bool))
    matched, difference = None, None
    if comparable:
        try:
            difference = float(o_value) - float(p_value)
            matched = difference == 0
        except (TypeError, ValueError):
            matched = str(o_value) == str(p_value)
    limitations = ["Comparison records agreement only; it does not establish that an action caused the outcome."]
    if not temporal_order_valid:
        limitations.append("Prediction must predate the observed outcome.")
    return OutcomeComparison(prediction_id=prediction.id, outcome_id=outcome.id, comparable=comparable,
                             prediction_value=p_value, observed_value=o_value, matched=matched, difference=difference,
                             limitations=limitations)


class OutcomeTracker:
    """Append observed outcomes and linked prediction comparisons to local JSONL history."""
    def __init__(self, path: Path | str, audit_log: AuditLog):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log = audit_log

    def record(self, prediction: Prediction, outcome: Outcome, *, prediction_field: str | None = None,
               outcome_field: str | None = None) -> OutcomeComparison:
        comparison = compare_outcome(prediction, outcome, prediction_field=prediction_field,
                                     outcome_field=outcome_field)
        event = {"outcome": outcome.model_dump(mode="json"), "prediction_id": prediction.id,
                 "comparison": comparison.model_dump(mode="json")}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_redact(event), ensure_ascii=False, default=str) + "\n")
        self.audit_log.append(event_type="outcome_observed", actor="system", source=outcome.source,
                              record_refs=outcome.record_refs, details={"outcome_id": outcome.id,
                              "prediction_id": prediction.id, "comparable": comparison.comparable,
                              "matched": comparison.matched})
        return comparison
