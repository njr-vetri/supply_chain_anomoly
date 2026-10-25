"""Explicitly hypothetical scenario arithmetic; never forecasts realized impact."""
from typing import Any


def compare_scenarios(*, affected_order_count: int, calibrated_delay_probability: float,
                      probability_calibrated: bool, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare simple assumed relative probability reductions for planning discussion."""
    if not probability_calibrated:
        return {"label": "HYPOTHETICAL", "status": "Insufficient evidence",
                "reason": "A calibrated baseline delay probability is required."}
    if not 0 <= calibrated_delay_probability <= 1 or affected_order_count < 0:
        raise ValueError("Probability must be in [0,1] and count must be non-negative")
    baseline = affected_order_count * calibrated_delay_probability
    results = [{"name": "baseline", "label": "HYPOTHETICAL", "assumptions": ["Calibrated probability applies to this exposed order set."],
                "assumed_probability": calibrated_delay_probability, "expected_delayed_orders": baseline}]
    for scenario in scenarios:
        assumptions = scenario.get("assumptions")
        if not isinstance(assumptions, list) or not assumptions or any(not str(item).strip() for item in assumptions):
            raise ValueError("Each what-if scenario requires explicit non-empty assumptions")
        reduction = float(scenario["assumed_relative_probability_reduction"])
        if not 0 <= reduction <= 1:
            raise ValueError("Scenario reduction must be between zero and one")
        probability = calibrated_delay_probability * (1 - reduction)
        results.append({"name": str(scenario["name"]), "label": "HYPOTHETICAL",
                        "assumptions": list(assumptions) +
                            [f"Assumed relative probability reduction: {reduction:.4f}; not an observed effect."],
                        "assumed_probability": probability,
                        "expected_delayed_orders": affected_order_count * probability,
                        "difference_vs_baseline": baseline - affected_order_count * probability})
    return {"label": "HYPOTHETICAL", "scenarios": results,
            "limitation": "Scenario arithmetic is illustrative and does not establish causal or realized impact.",
            "not_estimated": ["supplier capacity", "inventory", "cost savings"]}
