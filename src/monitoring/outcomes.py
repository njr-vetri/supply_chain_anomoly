"""Alert performance summaries and post-outcome evaluations computed only from reviewer-verified labels."""
from __future__ import annotations

from typing import Any

from src.core.repository import OutcomeRow, Repository


def evaluate_forecast_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute forecast vs actual metrics (MAE, MAPE, bias) only where verified actuals exist."""
    pairs: list[dict[str, Any]] = []
    for outcome in outcomes:
        comparisons = outcome.get("comparisons", [])
        for comp in comparisons:
            comp_type = str(comp.get("type", "")).upper()
            target = str(comp.get("target", "")).lower()
            ref_id = str(comp.get("reference_id", "")).lower()
            is_forecast = (
                comp_type in ("FORECAST", "DEMAND")
                or any(k in target for k in ("demand", "forecast", "qty", "quantity"))
                or any(k in ref_id for k in ("demand", "forecast"))
            )
            if not is_forecast:
                continue
            pred_val = comp.get("prediction_value")
            obs_val = comp.get("observed_value")
            if pred_val is None or obs_val is None:
                continue
            try:
                p_num = float(pred_val)
                o_num = float(obs_val)
                pairs.append({
                    "reference_id": comp.get("reference_id"),
                    "forecast": p_num,
                    "actual": o_num,
                    "error": p_num - o_num,
                    "absolute_error": abs(p_num - o_num),
                })
            except (ValueError, TypeError):
                continue

    if not pairs:
        return {
            "status": "INSUFFICIENT_VERIFIED_OUTCOMES",
            "message": "not enough verified outcomes",
            "count": 0,
            "mae": None,
            "mape": None,
            "bias": None,
            "comparisons": [],
            "limitations": ["Forecast evaluation requires verified observed outcomes linked to earlier forecasts."],
        }

    n = len(pairs)
    mae = sum(p["absolute_error"] for p in pairs) / n
    bias = sum(p["error"] for p in pairs) / n
    nonzero_actuals = [p for p in pairs if p["actual"] != 0]
    mape = (sum(p["absolute_error"] / abs(p["actual"]) for p in nonzero_actuals) / len(nonzero_actuals)) if nonzero_actuals else None

    return {
        "status": "COMPUTED_FROM_VERIFIED_OUTCOMES",
        "count": n,
        "mae": float(mae),
        "mape": float(mape) if mape is not None else None,
        "bias": float(bias),
        "comparisons": pairs,
        "limitations": ["Outcome comparison does not establish forecast or recommendation causality."],
    }


def evaluate_prediction_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute prediction vs outcome metrics (accuracy, precision, recall, brier) where verified labels exist."""
    pairs: list[dict[str, Any]] = []
    for outcome in outcomes:
        comparisons = outcome.get("comparisons", [])
        for comp in comparisons:
            comp_type = str(comp.get("type", "")).upper()
            target = str(comp.get("target", "")).lower()
            ref_id = str(comp.get("reference_id", "")).lower()
            if comp_type in ("FORECAST", "DEMAND") or any(k in target for k in ("demand", "forecast")) or any(k in ref_id for k in ("demand", "forecast")):
                continue
            if comp_type != "PREDICTION":
                continue
            pred_val = comp.get("prediction_value")
            obs_val = comp.get("observed_value")
            if pred_val is None or obs_val is None:
                continue
            try:
                # Binary classification checks
                if obs_val in (0, 1, "0", "1", True, False):
                    y_true = int(bool(obs_val) if isinstance(obs_val, bool) else int(obs_val))
                    y_prob = float(pred_val)
                    y_pred = int(y_prob >= 0.5) if (0.0 <= y_prob <= 1.0) else int(float(pred_val) >= 1.0)
                    pairs.append({
                        "reference_id": comp.get("reference_id"),
                        "predicted_probability": y_prob,
                        "predicted_label": y_pred,
                        "observed_label": y_true,
                    })
            except (ValueError, TypeError):
                continue

    if not pairs:
        return {
            "status": "INSUFFICIENT_VERIFIED_OUTCOMES",
            "message": "not enough verified outcomes",
            "count": 0,
            "accuracy": None,
            "precision": None,
            "recall": None,
            "brier_score": None,
            "confusion_matrix": None,
            "comparisons": [],
            "limitations": ["Prediction evaluation requires verified observed outcomes linked to earlier predictions."],
        }

    n = len(pairs)
    tp = sum(1 for p in pairs if p["predicted_label"] == 1 and p["observed_label"] == 1)
    tn = sum(1 for p in pairs if p["predicted_label"] == 0 and p["observed_label"] == 0)
    fp = sum(1 for p in pairs if p["predicted_label"] == 1 and p["observed_label"] == 0)
    fn = sum(1 for p in pairs if p["predicted_label"] == 0 and p["observed_label"] == 1)

    accuracy = (tp + tn) / n
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    brier_score = sum((p["predicted_probability"] - p["observed_label"]) ** 2 for p in pairs) / n

    return {
        "status": "COMPUTED_FROM_VERIFIED_OUTCOMES",
        "count": n,
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "brier_score": float(brier_score),
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "comparisons": pairs,
        "limitations": ["Prediction evaluation reflects available verified outcomes only."],
    }


def evaluate_verified_alerts(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute precision and missed-event counts from explicitly verified binary labels."""
    verified = [row for row in outcomes if row.get("verified_alert_label") is not None
                and row.get("alert_was_raised") is not None and row.get("verified_by")]
    if not verified:
        return {
            "status": "INSUFFICIENT_VERIFIED_LABELS",
            "message": "not enough verified outcomes",
            "verified_rows": 0,
            "alert_precision": None,
            "missed_events": None,
            "limitations": ["No reviewer-verified alert labels are available."]
        }
    tp = sum(bool(r["alert_was_raised"]) and bool(r["verified_alert_label"]) for r in verified)
    fp = sum(bool(r["alert_was_raised"]) and not bool(r["verified_alert_label"]) for r in verified)
    fn = sum(not bool(r["alert_was_raised"]) and bool(r["verified_alert_label"]) for r in verified)
    denominator = tp + fp
    return {
        "status": "COMPUTED_FROM_VERIFIED_LABELS",
        "verified_rows": len(verified),
        "true_positive_alerts": tp,
        "false_positive_alerts": fp,
        "missed_events": fn,
        "alert_precision": tp / denominator if denominator else None,
        "limitations": ["Metrics cover only outcomes with reviewer-verified event labels."]
    }


def evaluate_repository_alerts(repository: Repository) -> dict[str, Any]:
    rows = repository.list_rows(OutcomeRow, limit=100000)
    return evaluate_verified_alerts([row.payload for row in rows])


def evaluate_company_outcomes(repository: Repository) -> dict[str, Any]:
    """Provide complete outcome evaluation (forecasts, predictions, alerts) scoped to the company."""
    rows = repository.list_rows(OutcomeRow, limit=100000)
    payloads = [row.payload for row in rows]
    return {
        "status": "EVALUATION_REPORT",
        "company_id": repository.company_id,
        "total_outcomes_recorded": len(payloads),
        "forecast_vs_actual": evaluate_forecast_outcomes(payloads),
        "prediction_vs_outcome": evaluate_prediction_outcomes(payloads),
        "alerts": evaluate_verified_alerts(payloads),
        "limitations": [
            "Evaluations require verified observed outcomes recorded after prior predictions.",
            "Outcome association does not establish causality.",
        ],
    }
