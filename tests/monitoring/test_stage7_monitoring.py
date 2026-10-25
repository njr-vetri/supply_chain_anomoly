"""Synthetic fixtures exercise drift and verified-outcome monitoring only."""
import pandas as pd

from src.monitoring.drift import compare_profiles, profile_frame
from src.monitoring.outcomes import evaluate_verified_alerts


def test_schema_and_numeric_feature_drift_use_statistics_only():
    baseline = profile_frame(pd.DataFrame({"quantity": [1, 2, 3, 4], "region": ["a", "b", "a", "b"]}))
    current = profile_frame(pd.DataFrame({"quantity": [10, 11, 12, 13], "new_field": [1, 1, 1, 1]}))
    result = compare_profiles(baseline, current, max_numeric_mean_shift=1.0)
    assert result["status"] == "DRIFT_ALERT"
    assert result["schema"]["added_columns"] == ["new_field"]
    assert result["schema"]["removed_columns"] == ["region"]
    assert "numeric_feature_drift:quantity" in result["alerts"]
    assert result["category_concentration_changes"] == {}
    assert "'a'" not in str(result)


def test_verified_alert_precision_and_missed_event_counts():
    result = evaluate_verified_alerts([
        {"verified_alert_label": True, "alert_was_raised": True, "verified_by": "reviewer"},
        {"verified_alert_label": False, "alert_was_raised": True, "verified_by": "reviewer"},
        {"verified_alert_label": True, "alert_was_raised": False, "verified_by": "reviewer"},
        {"verified_alert_label": True, "alert_was_raised": True, "verified_by": "reviewer"},
        {"verified_alert_label": True, "alert_was_raised": False, "verified_by": None},
    ])
    assert result["verified_rows"] == 4
    assert result["alert_precision"] == 2 / 3
    assert result["missed_events"] == 1


def test_no_verified_labels_does_not_compute_metrics():
    result = evaluate_verified_alerts([{"verified_alert_label": True, "alert_was_raised": True}])
    assert result["status"] == "INSUFFICIENT_VERIFIED_LABELS"
    assert result["alert_precision"] is None
    assert result["missed_events"] is None
