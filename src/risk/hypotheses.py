"""Evidence ledger and role-gated hypothesis status transitions."""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.config import load_settings
from src.core.schemas import HypothesisStatus, ReviewEntry


class LedgerEvidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    classification: str
    source: str
    record_refs: list[str]
    observed_at: datetime
    strength: float = Field(ge=0, le=1)
    description: str


class EvidenceLedger(BaseModel):
    supporting: list[LedgerEvidence] = Field(default_factory=list)
    contradicting: list[LedgerEvidence] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)

    def add(self, evidence: LedgerEvidence) -> None:
        if evidence.classification == "supporting":
            self.supporting.append(evidence)
        elif evidence.classification == "contradicting":
            self.contradicting.append(evidence)
        else:
            raise ValueError("Evidence classification must be supporting or contradicting")


class HypothesisCase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    statement: str
    source: str
    status: HypothesisStatus = HypothesisStatus.UNVERIFIED
    ledger: EvidenceLedger = Field(default_factory=EvidenceLedger)
    review_history: list[ReviewEntry] = Field(default_factory=list)


class HypothesisService:
    def __init__(self, *, minimum_supporting_evidence: int | None = None,
                 minimum_evidence_strength: float | None = None):
        risk = load_settings().risk
        self.minimum_count = minimum_supporting_evidence or risk.minimum_supporting_evidence
        self.minimum_strength = (risk.minimum_evidence_strength if minimum_evidence_strength is None
                                  else minimum_evidence_strength)

    def assess(self, case: HypothesisCase) -> str:
        strong = [e for e in case.ledger.supporting if e.strength >= self.minimum_strength]
        if len(strong) < self.minimum_count:
            case.ledger.missing.append(f"Need {self.minimum_count} supporting evidence items with strength >= {self.minimum_strength}")
            return "Insufficient evidence"
        return "Evidence threshold met; human review is still required."

    def transition(self, case: HypothesisCase, new_status: HypothesisStatus, *, user_id: str,
                   role: str, rationale: str) -> HypothesisCase:
        allowed = {
            HypothesisStatus.UNVERIFIED: {HypothesisStatus.SUPPORTED, HypothesisStatus.REJECTED, HypothesisStatus.CLOSED},
            HypothesisStatus.SUPPORTED: {HypothesisStatus.CONFIRMED, HypothesisStatus.REJECTED, HypothesisStatus.CLOSED},
            HypothesisStatus.CONFIRMED: {HypothesisStatus.CLOSED},
            HypothesisStatus.REJECTED: {HypothesisStatus.CLOSED},
            HypothesisStatus.CLOSED: set(),
        }
        if new_status not in allowed[case.status]:
            raise ValueError(f"Invalid hypothesis transition: {case.status.value} -> {new_status.value}")
        if new_status == HypothesisStatus.SUPPORTED and self.assess(case) == "Insufficient evidence":
            raise ValueError("Insufficient evidence to mark hypothesis SUPPORTED")
        if new_status == HypothesisStatus.CONFIRMED:
            if role != "reviewer":
                raise PermissionError("Only a user with reviewer role can confirm a hypothesis")
            if self.assess(case) == "Insufficient evidence":
                raise ValueError("Insufficient evidence to confirm hypothesis")
        if not user_id.strip() or not rationale.strip():
            raise ValueError("user_id and rationale are required for a status transition")
        previous = case.status
        case.review_history.append(ReviewEntry(reviewer_id=user_id, previous_status=previous,
            new_status=new_status, rationale=rationale, reviewed_at=datetime.now(timezone.utc)))
        case.status = new_status
        return case
