"""Rolling-origin demand forecasting baselines for product-week transaction quantities."""
from __future__ import annotations

import numpy as np
import pandas as pd


def dense_product_weeks(weekly: pd.DataFrame) -> pd.DataFrame:
    """Create a product-week panel; absent transaction weeks are recorded as zero demand."""
    pieces = []
    for product, group in weekly.groupby("StockCode", sort=False):
        series = group.set_index("week")["weekly_quantity"].sort_index()
        index = pd.date_range(series.index.min(), series.index.max(), freq="W-MON")
        # Normalize observed week starts to the same weekly index.
        series.index = series.index.to_period("W").start_time
        index = index.to_period("W").start_time
        dense = series.groupby(level=0).sum().reindex(index, fill_value=0)
        pieces.append(pd.DataFrame({"StockCode": product, "week": dense.index, "demand": dense.values}))
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=["StockCode", "week", "demand"])


def rolling_origin_cv(panel: pd.DataFrame, *, folds: int, horizon: int, moving_average_weeks: int,
                      seasonal_period_weeks: int) -> dict[str, object]:
    """Evaluate naive, moving-average, seasonal-naive over increasing chronological cutoffs."""
    weeks = sorted(pd.to_datetime(panel["week"]).unique())
    n_weeks = len(weeks)
    if n_weeks < 2:
        return {
            "metric": "MAE",
            "baselines_run": [],
            "baselines_skipped": [{"name": "all", "reason": f"Insufficient history: {n_weeks} weeks, need >= 2"}],
            "folds": [],
            "naive": {"fold_mae": [], "mean_mae": None},
            "moving_average": {"fold_mae": [], "mean_mae": None},
            "seasonal_naive": {"fold_mae": [], "mean_mae": None},
        }

    baselines_run: list[str] = []
    baselines_skipped: list[dict[str, str]] = []

    run_seasonal = True
    if n_weeks <= seasonal_period_weeks + horizon:
        run_seasonal = False
        baselines_skipped.append({
            "name": "seasonal_naive",
            "reason": f"Insufficient history for seasonal period: {n_weeks} weeks <= {seasonal_period_weeks} + {horizon} window",
        })
    else:
        baselines_run.append("seasonal_naive")

    # Adapt folds and horizon if necessary
    min_train = max(moving_average_weeks, 1)
    adapted_folds = folds
    adapted_horizon = horizon

    while adapted_folds > 1 and (adapted_folds * adapted_horizon + min_train) > n_weeks:
        adapted_folds -= 1

    if (adapted_folds * adapted_horizon + min_train) > n_weeks:
        adapted_horizon = max(1, (n_weeks - min_train) // max(1, adapted_folds))

    results: dict[str, list[float]] = {"naive": [], "moving_average": []}
    if run_seasonal:
        results["seasonal_naive"] = []

    baselines_run.extend(["naive", "moving_average"])

    cutoffs = []
    for fold in range(adapted_folds, 0, -1):
        cutoff_index = n_weeks - fold * adapted_horizon
        cutoff = weeks[cutoff_index - 1]
        train = panel[panel["week"] <= cutoff]
        test_weeks = weeks[cutoff_index:cutoff_index + adapted_horizon]
        if len(test_weeks) != adapted_horizon:
            continue
        predictions: dict[str, list[float]] = {key: [] for key in results}
        actual: list[float] = []
        for product, future in panel[panel["week"].isin(test_weeks)].groupby("StockCode"):
            history = train[train["StockCode"] == product].sort_values("week")["demand"].to_numpy()
            if len(history) == 0:
                continue
            for _, row in future.sort_values("week").iterrows():
                actual.append(float(row["demand"]))
                predictions["naive"].append(float(history[-1]))
                predictions["moving_average"].append(float(np.mean(history[-moving_average_weeks:])))
                if run_seasonal:
                    if len(history) < seasonal_period_weeks:
                        predictions["seasonal_naive"].append(0.0)
                    else:
                        predictions["seasonal_naive"].append(float(history[-seasonal_period_weeks]))
        for name, predicted in predictions.items():
            if predicted and len(predicted) == len(actual):
                errors = np.asarray(actual) - np.asarray(predicted)
                results[name].append(float(np.mean(np.abs(errors))))
        cutoffs.append({"train_through": str(cutoff), "test_start": str(test_weeks[0]), "test_end": str(test_weeks[-1])})

    output: dict[str, Any] = {
        name: {"fold_mae": values, "mean_mae": float(np.mean(values)) if values else None}
        for name, values in results.items()
    }
    if not run_seasonal:
        output["seasonal_naive"] = {"fold_mae": [], "mean_mae": None}

    output["baselines_run"] = sorted(set(baselines_run))
    output["baselines_skipped"] = baselines_skipped
    output["folds"] = cutoffs
    output["metric"] = "MAE"
    output["cv_adapted"] = (adapted_folds != folds or adapted_horizon != horizon)
    output["configured_folds"] = folds
    output["configured_horizon"] = horizon
    output["adapted_folds"] = adapted_folds
    output["adapted_horizon"] = adapted_horizon
    return output
