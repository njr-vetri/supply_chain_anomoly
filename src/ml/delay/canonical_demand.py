"""Canonical transaction demand analysis, baseline forecasts and rolling backtests."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FORECAST_NOTE = "Demand pressure only; inventory and stockout status are not inferred."


def _granularity(span_days: int, settings: Any) -> str:
    if span_days >= settings.monthly_min_span_days and "monthly" in settings.allowed_granularities:
        return "monthly"
    if span_days >= settings.weekly_min_span_days and "weekly" in settings.allowed_granularities:
        return "weekly"
    if span_days <= settings.daily_max_span_days and "daily" in settings.allowed_granularities:
        return "daily"
    return "weekly" if "weekly" in settings.allowed_granularities else settings.allowed_granularities[0]


def forecast_canonical_demand(records: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
    """Choose time grain from span, then produce three simple demand baselines."""
    eligible = [record for record in records if record.get("product_id") is not None
                and record.get("quantity") is not None and record.get("event_timestamp") is not None]
    if not eligible:
        return {"status": "MISSING_DEMAND_DATA", "task": "demand pressure forecasting",
                "missing": ["product_id", "quantity", "event_timestamp"],
                "inventory_available": False, "label": FORECAST_NOTE}
    frame = pd.DataFrame(eligible)
    frame["event_timestamp"] = pd.to_datetime(frame["event_timestamp"], errors="coerce", utc=True)
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    frame = frame.dropna(subset=["event_timestamp", "quantity"])
    if frame.empty:
        return {"status": "MISSING_DEMAND_DATA", "task": "demand pressure forecasting",
                "missing": ["valid timestamps and numeric quantities"],
                "inventory_available": False, "label": FORECAST_NOTE}
    span = int((frame["event_timestamp"].max() - frame["event_timestamp"].min()).days)
    granularity = _granularity(span, settings)
    frequency = {"daily": "D", "weekly": "W-MON", "monthly": "MS"}[granularity]
    period = {"daily": "D", "weekly": "W", "monthly": "M"}[granularity]
    frame["period"] = frame["event_timestamp"].dt.tz_convert(None).dt.to_period(period).dt.start_time
    entities = ["product_id"] + (["warehouse_id"] if frame.get("warehouse_id", pd.Series(dtype=object)).notna().any() else [])
    panel = frame.groupby(entities + ["period"], as_index=False)["quantity"].sum()
    horizon = settings.horizon_periods
    seasonal = settings.seasonal_periods[granularity]
    methods = ("naive", "moving_average", "seasonal_naive")
    errors: dict[str, list[float]] = {method: [] for method in methods}
    forecasts: list[dict[str, Any]] = []
    tracking: list[dict[str, Any]] = []
    for entity_key, group in panel.groupby(entities, dropna=False, sort=True):
        if not isinstance(entity_key, tuple):
            entity_key = (entity_key,)
        series = group.set_index("period")["quantity"].sort_index()
        full_index = pd.date_range(series.index.min(), series.index.max(), freq=frequency)
        series = series.reindex(full_index, fill_value=0.0)
        if len(series) < settings.minimum_history_periods + horizon:
            continue
        origins = min(settings.backtest_folds, len(series) - settings.minimum_history_periods - horizon + 1)
        for fold in range(origins, 0, -1):
            cutoff = len(series) - fold * horizon
            history = series.iloc[:cutoff].to_numpy(dtype=float)
            observed = series.iloc[cutoff:cutoff + horizon].to_numpy(dtype=float)
            if not len(observed):
                continue
            predictions = {"naive": np.repeat(history[-1], len(observed)),
                           "moving_average": np.repeat(np.mean(history[-settings.moving_average_periods:]), len(observed))}
            if len(history) >= seasonal:
                predictions["seasonal_naive"] = np.asarray(
                    [history[-seasonal + (i % seasonal)] for i in range(len(observed))])
            for method, values in predictions.items():
                errors[method].extend((observed - values).tolist())
                tracking.extend({"entity": dict(zip(entities, entity_key)), "period": str(series.index[cutoff + i]),
                    "method": method, "predicted": float(values[i]), "observed": float(observed[i]),
                    "absolute_error": float(abs(observed[i] - values[i]))} for i in range(len(observed)))
        history = series.to_numpy(dtype=float)
        future = pd.date_range(series.index[-1], periods=horizon + 1, freq=frequency)[1:]
        predictions = {"naive": np.repeat(history[-1], horizon),
                       "moving_average": np.repeat(np.mean(history[-settings.moving_average_periods:]), horizon)}
        if len(history) >= seasonal:
            predictions["seasonal_naive"] = np.asarray(
                [history[-seasonal + (i % seasonal)] for i in range(horizon)])
        tail = 1 - settings.prediction_interval_level
        for method, values in predictions.items():
            residuals = np.asarray(errors[method], dtype=float)
            lo = float(np.quantile(residuals, tail / 2)) if len(residuals) else 0.0
            hi = float(np.quantile(residuals, 1 - tail / 2)) if len(residuals) else 0.0
            for i, value in enumerate(values):
                forecasts.append({"entity": dict(zip(entities, entity_key)), "period": str(future[i]),
                    "granularity": granularity, "method": method, "prediction": float(value),
                    "prediction_interval": {"lower": float(value + lo), "upper": float(value + hi),
                                            "level": settings.prediction_interval_level},
                    "label": FORECAST_NOTE})
    if not forecasts:
        return {"status": "INSUFFICIENT_HISTORY", "task": "demand pressure forecasting",
                "granularity": granularity, "records": len(eligible),
                "minimum_history_periods": settings.minimum_history_periods,
                "inventory_available": False, "label": FORECAST_NOTE}
    def _calc_smape(method_name: str) -> float | None:
        subset = [r for r in tracking if r["method"] == method_name]
        if not subset:
            return None
        smapes = [200.0 * abs(r["observed"] - r["predicted"]) / (abs(r["observed"]) + abs(r["predicted"]) + 1e-8)
                  for r in subset]
        return float(np.mean(smapes))

    metrics = {method: {"backtest_rows": sum(row["method"] == method for row in tracking),
                        "mae": float(np.mean([row["absolute_error"] for row in tracking
                                              if row["method"] == method])) if any(
                            row["method"] == method for row in tracking) else None,
                        "smape": _calc_smape(method)}
               for method in methods}
    return {"status": "COMPUTED", "task": "demand pressure forecasting", "granularity": granularity,
            "entity_roles": entities, "forecast_horizon_periods": horizon,
            "backtest": {"method": "rolling origin", "folds": settings.backtest_folds, "metrics": metrics},
            "forecasts": forecasts, "forecast_vs_actual": tracking,
            "inventory_available": bool(frame.get("snapshot_id", pd.Series(dtype=object)).notna().any()),
            "label": FORECAST_NOTE}
