"""Versioned company risk scoring with separate factor outputs and qualitative fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SeverityThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    low_max: float = Field(default=0.25, ge=0, le=1)
    medium_max: float = Field(default=0.5, ge=0, le=1)
    high_max: float = Field(default=0.75, ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if not self.low_max < self.medium_max < self.high_max:
            raise ValueError("Severity thresholds must be strictly increasing")
        return self


class CompanyRiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="risk-v1", min_length=1, max_length=64)
    weights: dict[str, float] = Field(default_factory=lambda: {
        "likelihood": 0.35, "impact": 0.30, "evidence_strength": 0.20, "uncertainty": 0.15})
    thresholds: SeverityThresholds = Field(default_factory=SeverityThresholds)

    @model_validator(mode="after")
    def valid_weights(self):
        expected = {"likelihood", "impact", "evidence_strength", "uncertainty"}
        if set(self.weights) != expected or any(value < 0 for value in self.weights.values()):
            raise ValueError("Weights must define likelihood, impact, evidence_strength and uncertainty as non-negative values")
        if sum(self.weights.values()) <= 0:
            raise ValueError("At least one scoring weight must be positive")
        return self


def score_company_risk(*, config: CompanyRiskConfig, likelihood: float | None,
                       likelihood_calibrated: bool, impact: float | None,
                       evidence_strength: float | None, uncertainty: float | None) -> dict[str, Any]:
    """Score defensible inputs; uncalibrated/missing likelihood forces qualitative output."""
    inputs = {"likelihood": likelihood if likelihood_calibrated else None,
              "impact": impact, "evidence_strength": evidence_strength, "uncertainty": uncertainty}
    for name, value in inputs.items():
        if value is not None and not 0 <= value <= 1:
            raise ValueError(f"{name} must be between zero and one")
    factors = {name: {"value": value, "weight": config.weights[name],
                      "weighted_contribution": (None if value is None else value * config.weights[name]),
                      "available": value is not None}
               for name, value in inputs.items()}
    known = [(name, item["value"], config.weights[name]) for name, item in factors.items()
             if item["available"]]
    total_weight = sum(weight for _, _, weight in known)
    weighted_index = sum(value * weight for _, value, weight in known) / total_weight if total_weight else None
    numeric_defensible = factors["likelihood"]["available"] and factors["impact"]["available"]
    score = weighted_index if numeric_defensible else None
    if score is not None:
        t = config.thresholds
        severity = "LOW" if score <= t.low_max else "MEDIUM" if score <= t.medium_max else "HIGH" if score <= t.high_max else "CRITICAL"
        basis = "numeric score: calibrated likelihood and impact are both available"
        rating = None
    else:
        severity = None
        rating = ("HIGHLY_UNCERTAIN" if inputs["likelihood"] is None or inputs["evidence_strength"] is None
                  or (inputs["uncertainty"] is not None and inputs["uncertainty"] >= 0.5)
                  else "QUALITATIVE_REVIEW")
        basis = "qualitative fallback: numeric likelihood/impact score is not defensible"
    return {"configuration_version": config.version, "score": score,
            "severity": severity, "qualitative_rating": rating, "basis": basis,
            "factors": factors, "computed_at": datetime.now(timezone.utc).isoformat(),
            "limitations": ["Risk prioritization is not a causal finding.",
                            "Likelihood is omitted unless explicitly marked calibrated."]}
