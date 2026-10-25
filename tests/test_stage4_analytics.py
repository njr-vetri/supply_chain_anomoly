"""Synthetic Stage 4 checks; these fixtures make no performance claim."""
from datetime import datetime, timedelta, timezone

from src.core.config import load_settings
from src.explainability.generic import explain_result
from src.ml.anomaly.canonical import detect_canonical_anomalies
from src.ml.delay.canonical import evaluate_canonical_delay
from src.ml.delay.canonical_demand import forecast_canonical_demand


def test_delay_allowlist_blocks_a_leaky_post_outcome_role():
    settings = load_settings().delay_prediction.model_copy(
        update={"feature_allowlist": ["post_outcome"],
                "feature_availability": {"post_outcome": "event_timestamp"}})
    result = evaluate_canonical_delay([], settings)
    assert result["status"] == "LEAKAGE_BLOCKED"
    assert result["trained"] is False
    assert "post_outcome" in result["blocked_features"]


def test_delay_allowlist_blocks_dataset_specific_outcome_alias():
    settings = load_settings().delay_prediction.model_copy(
        update={"feature_allowlist": ["Late_delivery_risk"],
                "feature_availability": {"Late_delivery_risk": "event_timestamp"}})
    result = evaluate_canonical_delay([], settings)
    assert result["status"] == "LEAKAGE_BLOCKED"
    assert result["trained"] is False


def test_delay_missing_labels_does_not_train():
    settings = load_settings().delay_prediction
    rows = [{"event_id": "synthetic-1", "event_timestamp": "2026-01-01T00:00:00Z",
             "quantity": 3}]
    result = evaluate_canonical_delay(rows, settings)
    assert result["status"] == "MISSING_LABELS"
    assert result["trained"] is False
    assert "post_outcome" in result["missing"]


def test_labelled_delay_fixture_uses_time_split_and_separates_rule_from_model():
    settings = load_settings().delay_prediction.model_copy(
        update={"feature_allowlist": ["quantity"], "feature_availability": {"quantity": "event_timestamp"},
                "minimum_training_rows": 10})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = [{"event_id": f"synthetic-{i}", "source_record_ref": f"fixture:{i}",
                "event_timestamp": (start + timedelta(days=i)).isoformat(), "quantity": i % 7,
                "supplier_id": f"supplier-{i % 2}", "post_outcome": i % 2}
               for i in range(50)]
    result = evaluate_canonical_delay(records, settings)
    assert result["status"] == "COMPUTED"
    assert result["split"]["method"] == "chronological"
    assert result["leakage_check"]["post_outcome_used_as_predictor"] is False
    assert result["models"]["supplier_history_rule"]["kind"] == "rule"
    assert result["models"]["supplier_history_rule"]["trained"] is False
    assert result["models"]["logistic_regression"]["trained"] is True
    explanation = result["explanations"]["logistic_regression"]
    assert explanation["status"] == "COMPUTED"
    assert explanation["note"] == "contribution, not cause"


def test_transactions_without_inventory_return_demand_pressure_not_stockout():
    settings = load_settings().forecasting.model_copy(
        update={"minimum_history_periods": 8, "horizon_periods": 3, "backtest_folds": 2})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = [{"event_id": f"synthetic-{day}", "source_record_ref": f"fixture:{day}",
                "event_timestamp": (start + timedelta(days=day)).isoformat(),
                "product_id": "sku-synthetic", "quantity": day % 5 + 1}
               for day in range(35)]
    result = forecast_canonical_demand(records, settings)
    assert result["status"] == "COMPUTED"
    assert result["task"] == "demand pressure forecasting"
    assert result["inventory_available"] is False
    assert "stockout status are not inferred" in result["label"]
    assert result["forecasts"]
    assert all("prediction_interval" in forecast for forecast in result["forecasts"])
    assert result["backtest"]["method"] == "rolling origin"


def test_canonical_anomaly_has_entity_baseline_methods_and_limitations():
    settings = load_settings().anomaly.model_copy(update={"canonical_metrics": {
        "quantity": {"entity_groupings": [["supplier_id"], ["product_id"]],
                     "rule_threshold": 500, "rule_direction": "above",
                     "severity_high": 3, "severity_critical": 6}},
        "rolling_window_records": 20, "minimum_baseline_records": 5,
        "seasonality_minimum_records": 20})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = [{"event_id": f"synthetic-{i}", "source_record_ref": f"fixture:{i}",
                "event_timestamp": (start + timedelta(days=i)).isoformat(),
                "supplier_id": "supplier-synthetic", "product_id": "sku-synthetic",
                "quantity": 1 if i < 15 else 1000}
               for i in range(16)]
    found = detect_canonical_anomalies(records, settings)
    assert found
    assert all(item["entity"] for item in found)
    assert all(item["record_refs"] and item["baseline"] is not None for item in found)
    assert all(item["expected_range"] and item["version"] and item["limitations"] for item in found)


def test_rule_explanation_is_marked_as_contribution_not_cause(tmp_path):
    result = explain_result(method="rule", record_ref="synthetic-record",
        output_path=tmp_path / "explanation.json", rule={"threshold": 10}, features={"quantity": 20})
    assert result["note"] == "contribution, not cause"


def test_identifier_columns_excluded_from_model_features():
    settings = load_settings().delay_prediction.model_copy(
        update={
            "feature_allowlist": ["quantity", "order_id", "shipment_id", "source"],
            "feature_availability": {
                "quantity": "event_timestamp",
                "order_id": "event_timestamp",
                "shipment_id": "event_timestamp",
                "source": "event_timestamp",
            },
            "minimum_training_rows": 10,
        }
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = [
        {
            "event_id": f"synthetic-{i}",
            "source_record_ref": f"fixture:{i}",
            "order_id": f"ORD-{i}",
            "shipment_id": f"SHIP-{i}",
            "source": "test_src",
            "event_timestamp": (start + timedelta(days=i)).isoformat(),
            "quantity": i % 7 + 1,
            "post_outcome": i % 2,
        }
        for i in range(30)
    ]
    result = evaluate_canonical_delay(records, settings)
    assert result["status"] == "COMPUTED"
    used_features = set(result.get("features", []))
    assert not ({"order_id", "shipment_id", "source", "event_id", "source_record_ref"} & used_features), f"Identifiers leaked into features: {used_features}"
