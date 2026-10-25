"""Synthetic fixtures verify deterministic evaluation mechanics, not model performance."""
import pandas as pd
import pytest

from src.ml.delay.evaluation import chronological_split, subgroup_errors
from src.ml.delay.forecasting import dense_product_weeks, rolling_origin_cv
from src.ml.delay.run import (DATACO_FORBIDDEN_PREDICTORS, DATACO_MODEL_FEATURES,
                              derive_dataco_delay_label, derive_olist_delay_label, render_markdown)


def test_chronological_split_never_shuffles_synthetic_rows():
    frame = pd.DataFrame({"time": pd.to_datetime(["2020-03-01", "2020-01-01", "2020-02-01"]),
                          "id": [3, 1, 2]})
    train, validation, test = chronological_split(frame, "time", 1 / 3, 1 / 3)
    assert train["id"].tolist() == [1]
    assert validation["id"].tolist() == [2]
    assert test["id"].tolist() == [3]


def test_chronological_split_rejects_missing_timestamps():
    with pytest.raises(ValueError):
        chronological_split(pd.DataFrame({"time": [None]}), "time")


def test_subgroup_error_analysis_uses_synthetic_groups():
    result = subgroup_errors([0, 1, 0, 1], [0.1, 0.8, 0.7, 0.2], ["A", "A", "B", "B"])
    assert result["A"]["rows"] == 2
    assert result["B"]["false_positive_rate"] == 1.0
    assert result["B"]["false_negative_rate"] == 1.0


def test_synthetic_forecast_panel_and_cv_are_chronological():
    rows = []
    dates = pd.date_range("2020-01-06", periods=70, freq="W-MON")
    for product in ("synthetic-A", "synthetic-B"):
        for index, week in enumerate(dates):
            rows.append({"StockCode": product, "week": week, "weekly_quantity": index + 1})
    panel = dense_product_weeks(pd.DataFrame(rows))
    result = rolling_origin_cv(panel, folds=2, horizon=2, moving_average_weeks=4, seasonal_period_weeks=4)
    assert result["metric"] == "MAE"
    assert len(result["folds"]) == 2
    assert result["naive"]["mean_mae"] is not None


def test_report_says_metrics_not_computed_when_absent():
    report = render_markdown({"random_seed": 1, "classification": {"dataco": {"status": "NOT COMPUTED: synthetic"}},
                              "demand_forecasting": {"status": "NOT COMPUTED: synthetic"}})
    assert "Not computed: NOT COMPUTED: synthetic" in report
    assert "stockout" in report


def test_olist_label_uses_delivery_vs_estimate_and_omits_unknowns():
    frame = pd.DataFrame({"order_delivered_customer_date": ["2020-01-03", "2020-01-01", None],
                          "order_estimated_delivery_date": ["2020-01-02", "2020-01-02", "2020-01-03"]})
    assert derive_olist_delay_label(frame).tolist()[:2] == [1, 0]
    assert pd.isna(derive_olist_delay_label(frame).iloc[2])


def test_dataco_leakage_fields_excluded_from_feature_allowlist():
    assert not (set(DATACO_MODEL_FEATURES) & DATACO_FORBIDDEN_PREDICTORS)
    label = derive_dataco_delay_label(pd.DataFrame({"Late_delivery_risk": [1, 0]}))
    assert label.tolist() == [1, 0]


def test_forecast_cv_adapts_to_short_history_without_failure():
    # Only 20 weeks available, but configured CV would require 52 + 3*4 = 64 weeks
    dates = pd.date_range("2020-01-06", periods=20, freq="W-MON")
    rows = [{"StockCode": "P1", "week": d, "weekly_quantity": 10 + i} for i, d in enumerate(dates)]
    panel = dense_product_weeks(pd.DataFrame(rows))
    result = rolling_origin_cv(panel, folds=3, horizon=4, moving_average_weeks=4, seasonal_period_weeks=52)
    assert result["metric"] == "MAE"
    assert "seasonal_naive" in [s["name"] for s in result["baselines_skipped"]]
    assert "naive" in result["baselines_run"]
    assert "moving_average" in result["baselines_run"]
    assert result["naive"]["mean_mae"] is not None
    assert result["seasonal_naive"]["mean_mae"] is None
