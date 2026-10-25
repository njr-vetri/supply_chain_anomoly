"""Synthetic injected anomalies check code paths only, not real-world performance."""
import pandas as pd

from src.core.config import load_settings
from src.data.features.dataco import build_dataco_shipping_features
from src.data.features.olist import build_olist_delivery_features
from src.data.features.online_retail_ii import build_product_week_demand
from src.ml.anomaly.isolation_forest import detect as isolation_detect
from src.ml.anomaly.rule_based import detect as rule_detect
from src.ml.anomaly.statistical import iqr, robust_zscore


def test_rule_and_statistical_detectors_flag_injected_synthetic_extreme():
    values = pd.Series([10, 11, 9, 10, 12, 500], dtype=float)
    assert rule_detect(values, 100)["anomaly"].tolist()[-1]
    assert robust_zscore(values, 3)["anomaly"].tolist()[-1]
    assert iqr(values, 1.5)["anomaly"].tolist()[-1]


def test_isolation_forest_wrapper_or_explicit_dependency_error():
    values = pd.Series([10, 11, 9, 10, 500], dtype=float)
    try:
        result = isolation_detect(values, contamination=0.2, estimators=20)
    except RuntimeError as exc:
        assert "scikit-learn" in str(exc)
    else:
        assert result["detector"].eq("isolation_forest").all()


def test_olist_seller_history_uses_only_earlier_orders():
    orders = pd.DataFrame({
        "order_id": ["synth-1", "synth-2"],
        "order_purchase_timestamp": ["2020-01-01", "2020-01-03"],
        "order_estimated_delivery_date": ["2020-01-05", "2020-01-07"],
        "order_delivered_customer_date": ["2020-01-04", "2020-01-08"],
    })
    items = pd.DataFrame({"order_id": ["synth-1", "synth-2"], "seller_id": ["seller-synth", "seller-synth"]})
    features = build_olist_delivery_features(orders, items)
    assert pd.isna(features.loc[0, "prior_seller_delivery_days_mean"])
    assert features.loc[1, "prior_seller_delivery_days_mean"] == 3


def test_dataco_separates_outcome_and_predictor_fields():
    result = build_dataco_shipping_features(pd.DataFrame({
        "Days for shipment (scheduled)": [3], "Days for shipping (real)": [5],
        "Late_delivery_risk": [1], "Shipping Mode": ["synthetic"],
    }))
    assert "scheduled_shipping_days" in result
    assert "observed_actual_shipping_days" in result
    assert "observed_late_delivery_risk" in result


def test_retail_lags_use_prior_product_weeks_only():
    frame = pd.DataFrame({"StockCode": ["synth-A"] * 3, "InvoiceDate": ["2020-01-01", "2020-01-08", "2020-01-15"],
                          "Quantity": [2, 4, 1000]})
    weekly = build_product_week_demand(frame, lags=(1,))
    assert weekly.loc[2, "quantity_lag_1w"] == 4
    assert weekly.loc[1, "quantity_lag_1w"] == 2


def test_anomaly_thresholds_are_configurable():
    settings = load_settings()
    assert settings.anomaly.robust_z_threshold > 0
    assert "dataco_scheduled_days" in settings.anomaly.rule_thresholds
