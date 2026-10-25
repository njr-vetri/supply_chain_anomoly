"""Rule-based recommendations with rationale, assumptions, uncertainty and evidence links."""
from typing import Any

from src.core.config import load_settings


def recommend(*, evidence_refs: list[str], seller_recurrence: int = 0, shipment_status_known: bool = True,
              monitoring_recurrence: int = 0, calibrated_delay_probability: float | None = None,
              probability_calibrated: bool = False, constraints: list[str] | None = None) -> list[dict[str, Any]]:
    settings = load_settings().recommendations
    should_recommend = (seller_recurrence >= settings["seller_recurrence_threshold"] or not shipment_status_known or
        monitoring_recurrence >= settings["monitoring_recurrence_threshold"] or
        (probability_calibrated and calibrated_delay_probability is not None and
         calibrated_delay_probability >= settings["notify_probability_threshold"]))
    if should_recommend and not evidence_refs:
        raise ValueError("Recommendations require linked evidence references")
    constraints = constraints or ["Human approval required before external or high-impact action.", "Dry-run by default."]
    recommendations = []
    def add(action: str, rationale: str, assumptions: list[str], uncertainty: list[str]) -> None:
        recommendations.append({"action": action, "rationale": rationale, "assumptions": assumptions,
                                 "uncertainty": uncertainty, "constraints": list(constraints),
                                 "evidence_refs": list(evidence_refs), "human_approval_required": True,
                                 "dry_run": True})

    if seller_recurrence >= settings["seller_recurrence_threshold"]:
        add("investigate seller pattern", "Repeated linked records warrant review of the seller's historical pattern.",
            ["Recurrence count is based on source-linked records."],
            ["Exposure does not establish seller fault or causation."])
    if not shipment_status_known:
        add("verify shipment status", "Shipment status is missing or unverified in the available evidence.",
            ["A status source may be available outside the audited extract."],
            ["The current archive may be stale or incomplete."])
    if monitoring_recurrence >= settings["monitoring_recurrence_threshold"]:
        add("increase monitoring", "A repeated signal supports closer observation while evidence is reviewed.",
            ["Monitoring can be increased without changing shipment operations."],
            ["Repeated anomalies may reflect data issues or expected variation."])
    if (probability_calibrated and calibrated_delay_probability is not None and
            calibrated_delay_probability >= settings["notify_probability_threshold"]):
        add("notify operator", "A calibrated delay probability meets the configured notification threshold.",
            ["Probability is calibrated for the relevant population and time period."],
            ["Calibration may drift; operator review is required."])
    return recommendations
