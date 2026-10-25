"""Configurable, factor-by-factor risk prioritization (not a causal score)."""
from datetime import datetime, timezone
from typing import Any

from src.core.config import RiskSettings, load_settings


def prioritize(*, delay_probability: float | None, probability_calibrated: bool,
               affected_order_count: int, supplier_exposure: int, evidence_strength: float | None,
               evidence_age_hours: float | None, recurrence_count: int,
               missing_data_fraction: float, settings: RiskSettings | None = None) -> dict[str, Any]:
    """Return normalized factors, weighted contributions, and weighted aggregate."""
    config = settings or load_settings().risk
    if not 0 <= missing_data_fraction <= 1:
        raise ValueError("missing_data_fraction must be between zero and one")
    if evidence_strength is not None and not 0 <= evidence_strength <= 1:
        raise ValueError("evidence_strength must be between zero and one")
    if probability_calibrated and delay_probability is not None and not 0 <= delay_probability <= 1:
        raise ValueError("calibrated delay_probability must be between zero and one")
    raw: dict[str, tuple[float | None, str]] = {
        "delay_probability": (delay_probability if probability_calibrated else None,
                              "Used only when explicitly marked calibrated."),
        "affected_order_count": (min(max(affected_order_count, 0) / config.count_saturation, 1),
                                 f"Saturated at {config.count_saturation} affected orders."),
        "supplier_exposure": (min(max(supplier_exposure, 0) / config.supplier_exposure_saturation, 1),
                               f"Saturated at {config.supplier_exposure_saturation} exposure units."),
        "evidence_strength": (evidence_strength, "Evidence quality supplied by the evidence review."),
        "evidence_freshness": (None if evidence_age_hours is None else
            max(0.0, 1.0 - max(evidence_age_hours, 0) / config.freshness_max_age_hours),
            f"Linear decay across {config.freshness_max_age_hours} hours; unavailable without evidence age."),
        "recurrence": (min(max(recurrence_count, 0) / config.recurrence_saturation, 1),
                       f"Saturated at {config.recurrence_saturation} recurrences."),
        "uncertainty": ((missing_data_fraction + (1 - evidence_strength if evidence_strength is not None else 1)) / 2,
                        "Higher means more missing data or weaker/missing evidence."),
    }
    factors = {}
    for name, (normalized, rationale) in raw.items():
        weight = float(config.weights[name])
        factors[name] = {"available": normalized is not None, "normalized_value": normalized,
                         "weight": weight, "weighted_contribution": None if normalized is None else weight * normalized,
                         "rationale": rationale}
    available_weight = sum(item["weight"] for item in factors.values() if item["available"])
    aggregate = (sum(item["weighted_contribution"] for item in factors.values() if item["available"]) / available_weight
                 if available_weight else None)
    return {"priority_index": aggregate, "interpretation": "relative prioritization aid; not causal and not an action",
            "computed_at": datetime.now(timezone.utc).isoformat(), "factors": factors}
