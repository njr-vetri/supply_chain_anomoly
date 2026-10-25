"""Typed domain records with distinct fact, prediction, hypothesis and action types."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)


class Evidence(Record):
    """Observed fact with source provenance; never a prediction or hypothesis."""
    evidence_type: str
    source: str
    record_refs: list[str] = Field(default_factory=list)
    observed_at: datetime
    facts: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None


class HypothesisStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUPPORTED = "SUPPORTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class ReviewEntry(BaseModel):
    reviewed_at: datetime = Field(default_factory=utc_now)
    reviewer_id: str
    previous_status: HypothesisStatus
    new_status: HypothesisStatus
    rationale: str


class Hypothesis(Record):
    statement: str
    status: HypothesisStatus = HypothesisStatus.UNVERIFIED
    evidence_refs: list[str] = Field(default_factory=list)
    source: str
    record_refs: list[str] = Field(default_factory=list)
    review_history: list[ReviewEntry] = Field(default_factory=list)

    @computed_field
    @property
    def status_label(self) -> str:
        """Readable presentation text; status remains the authoritative lifecycle value."""
        return {HypothesisStatus.UNVERIFIED: "Unverified",
                HypothesisStatus.SUPPORTED: "Supported by evidence",
                HypothesisStatus.CONFIRMED: "Human confirmed",
                HypothesisStatus.REJECTED: "Rejected",
                HypothesisStatus.CLOSED: "Closed"}[self.status]

    @model_validator(mode="after")
    def confirmed_by_human_review(self) -> "Hypothesis":
        if self.status == HypothesisStatus.CONFIRMED:
            if not self.review_history or self.review_history[-1].new_status != HypothesisStatus.CONFIRMED:
                raise ValueError("CONFIRMED requires a human review history entry")
        return self


class Incident(Record):
    title: str
    description: str
    source: str
    record_refs: list[str] = Field(default_factory=list)
    occurred_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)
    hypothesis_refs: list[str] = Field(default_factory=list)


class Prediction(Record):
    target: str
    value: str | float | int | bool
    model_version_id: str
    source: str
    record_refs: list[str] = Field(default_factory=list)
    predicted_at: datetime
    confidence: float | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)


class Recommendation(Record):
    action: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    prediction_refs: list[str] = Field(default_factory=list)
    hypothesis_refs: list[str] = Field(default_factory=list)
    source: str
    record_refs: list[str] = Field(default_factory=list)
    human_approval_required: bool = True
    driver_type: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    approvals: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    status: str = "PROPOSED"
    result: dict[str, Any] | None = None
    estimated_effect: dict[str, Any] | None = None


class Approval(Record):
    recommendation_id: str
    reviewer_id: str | None = None
    status: str = "pending"
    approved: bool | None = None
    reviewed_at: datetime = Field(default_factory=utc_now)
    rationale: str


class OutcomeComparison(Record):
    prediction_id: str
    outcome_id: str
    comparable: bool
    prediction_value: Any = None
    observed_value: Any = None
    matched: bool | None = None
    difference: float | None = None
    limitations: list[str] = Field(default_factory=list)


class Action(Record):
    recommendation_id: str
    approval_id: str | None = None
    source: str
    record_refs: list[str] = Field(default_factory=list)
    dry_run: bool = True
    executed_at: datetime | None = None
    verified_at: datetime | None = None
    execution_status: str = "NOT_EXECUTED"
    result: dict[str, Any] | None = None
    status: str = "PLANNED"


class Outcome(Record):
    action_id: str
    source: str
    record_refs: list[str] = Field(default_factory=list)
    observed_at: datetime
    facts: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    recommendation_refs: list[str] = Field(default_factory=list)
    prediction_refs: list[str] = Field(default_factory=list)
    execution_status: str = "UNKNOWN"
    result: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(Record):
    event_type: str
    actor: str
    source: str | None = None
    record_refs: list[str] = Field(default_factory=list)
    occurred_at: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str
    event_hash: str


class ModelVersion(Record):
    name: str
    version: str
    artifact_hash: str
    trained_at: datetime | None = None
    training_data_version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class DatasetVersion(Record):
    dataset: str
    source: str
    source_hash: str
    record_refs: list[str] = Field(default_factory=list)
    observed_at: datetime
    transform_steps: list[str] = Field(default_factory=list)
    license_status: str = "UNKNOWN"
