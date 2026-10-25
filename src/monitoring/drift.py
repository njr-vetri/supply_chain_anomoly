"""Aggregate-only schema and feature drift profiles with configurable limits."""
from __future__ import annotations

from typing import Any

import pandas as pd


def profile_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Return aggregate statistics only; never include samples or category values."""
    columns: dict[str, Any] = {}
    for name in frame.columns:
        series = frame[name]
        item: dict[str, Any] = {
            "dtype": str(series.dtype),
            "null_rate": float(series.isna().mean()) if len(series) else 0.0,
            "unique_fraction": float(series.nunique(dropna=True) / max(len(series), 1)),
        }
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any() and (pd.api.types.is_numeric_dtype(series) or numeric.notna().mean() >= 0.95):
            values = numeric.dropna().astype(float)
            item["numeric"] = {
                "count": int(len(values)), "mean": float(values.mean()),
                "std": float(values.std(ddof=0)) if len(values) else 0.0,
                "q25": float(values.quantile(0.25)), "median": float(values.median()),
                "q75": float(values.quantile(0.75)),
            }
        else:
            item["category_concentration"] = (
                float(series.value_counts(normalize=True, dropna=True).head(1).sum())
                if series.notna().any() else 0.0
            )
        columns[str(name)] = item
    return {"row_count": int(len(frame)), "columns": columns}


def dataset_profile_to_drift_dict(profile: dict[str, Any] | Any) -> dict[str, Any]:
    """Normalize a DatasetProfileReport dict or standard profile dict to drift format."""
    if not isinstance(profile, dict):
        return {"row_count": 0, "columns": {}}
    if "columns" in profile and isinstance(profile["columns"], dict):
        return profile
    # If columns is a list (e.g. from DatasetProfileReport)
    columns_list = profile.get("columns", [])
    row_count = int(profile.get("total_rows") or profile.get("processed_rows") or profile.get("row_count", 0))
    columns: dict[str, Any] = {}
    if isinstance(columns_list, list):
        for col in columns_list:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name", ""))
            null_pct = float(col.get("null_percentage", 0.0) or 0.0)
            null_rate = float(col.get("null_rate", null_pct / 100.0 if null_pct > 1.0 else null_pct))
            item: dict[str, Any] = {
                "dtype": str(col.get("dtype", "unknown")),
                "null_rate": null_rate,
                "unique_fraction": float(col.get("uniqueness_ratio") or col.get("unique_fraction", 0.0) or 0.0),
            }
            num_stats = col.get("numeric_stats") or col.get("numeric")
            if num_stats and isinstance(num_stats, dict):
                item["numeric"] = {
                    "count": int(num_stats.get("count", row_count)),
                    "mean": float(num_stats.get("mean", 0.0) or 0.0),
                    "std": float(num_stats.get("std", 0.0) or 0.0),
                    "q25": float(num_stats.get("q25", num_stats.get("min", 0.0)) or 0.0),
                    "median": float(num_stats.get("median", num_stats.get("mean", 0.0)) or 0.0),
                    "q75": float(num_stats.get("q75", num_stats.get("max", 0.0)) or 0.0),
                }
            str_stats = col.get("string_stats")
            if str_stats and isinstance(str_stats, dict) and "top_frequency_ratio" in str_stats:
                item["category_concentration"] = float(str_stats["top_frequency_ratio"] or 0.0)
            elif "category_concentration" in col:
                item["category_concentration"] = float(col["category_concentration"] or 0.0)
            columns[name] = item
    return {"row_count": row_count, "columns": columns}


def compare_profiles(baseline: dict[str, Any], current: dict[str, Any], *,
                     max_row_count_change_fraction: float = 0.25,
                     max_null_rate_change: float = 0.1,
                     max_numeric_mean_shift: float = 1.0,
                     max_category_concentration_change: float = 0.2) -> dict[str, Any]:
    """Compare aggregate profile stats and return change flags without raw data."""
    baseline = dataset_profile_to_drift_dict(baseline)
    current = dataset_profile_to_drift_dict(current)
    base_columns = baseline.get("columns", {})
    current_columns = current.get("columns", {})
    added = sorted(set(current_columns) - set(base_columns))
    removed = sorted(set(base_columns) - set(current_columns))
    type_changes = {name: {"baseline": base_columns[name].get("dtype"), "current": current_columns[name].get("dtype")}
                    for name in sorted(set(base_columns) & set(current_columns))
                    if base_columns[name].get("dtype") != current_columns[name].get("dtype")}
    alerts: list[str] = []
    if added or removed or type_changes:
        alerts.append("schema_changed")
    previous_rows = max(int(baseline.get("row_count", 0)), 1)
    row_change = abs(int(current.get("row_count", 0)) - int(baseline.get("row_count", 0))) / previous_rows
    if row_change > max_row_count_change_fraction:
        alerts.append("row_count_change_exceeds_configured_threshold")
    null_changes: dict[str, float] = {}
    mean_shifts: dict[str, float] = {}
    concentration_changes: dict[str, float] = {}
    for name in sorted(set(base_columns) & set(current_columns)):
        prior, present = base_columns[name], current_columns[name]
        null_delta = abs(float(present.get("null_rate", 0)) - float(prior.get("null_rate", 0)))
        null_changes[name] = null_delta
        if null_delta > max_null_rate_change:
            alerts.append(f"null_rate_change:{name}")
        prior_numeric, current_numeric = prior.get("numeric"), present.get("numeric")
        if prior_numeric and current_numeric:
            scale = max(float(prior_numeric.get("std", 0)), 1e-12)
            shift = abs(float(current_numeric.get("mean", 0)) - float(prior_numeric.get("mean", 0))) / scale
            mean_shifts[name] = shift
            if shift > max_numeric_mean_shift:
                alerts.append(f"numeric_feature_drift:{name}")
        elif "category_concentration" in prior and "category_concentration" in present:
            change = abs(float(present["category_concentration"]) - float(prior["category_concentration"]))
            concentration_changes[name] = change
            if change > max_category_concentration_change:
                alerts.append(f"categorical_feature_drift:{name}")
    return {
        "status": "DRIFT_ALERT" if alerts else "WITHIN_CONFIGURED_LIMITS",
        "row_count_change_fraction": row_change,
        "schema": {"added_columns": added, "removed_columns": removed, "type_changes": type_changes},
        "null_rate_unit": "fraction",
        "units": {
            "row_count_change": "fraction",
            "null_rate_change": "fraction (0.0 to 1.0)",
            "numeric_mean_shift": "baseline_standard_deviations (z-units)",
            "category_concentration_change": "fraction (0.0 to 1.0)",
        },
        "numeric_mean_shift_in_baseline_std": mean_shifts,
        "category_concentration_changes": concentration_changes,
        "alerts": alerts,
        "drift_is_warning_only": True,
        "triggers_automatic_retrain": False,
        "warning": "Drift is a warning, never an automatic retrain trigger.",
        "limitations": [
            "Aggregate distribution changes are indicators, not proof of a cause.",
            "Drift is a warning only; automatic retraining is disallowed."
        ],
    }
