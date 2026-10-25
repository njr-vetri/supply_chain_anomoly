"""Entity-aware anomaly detection for canonical metric records."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

ENGINE_VERSION = "canonical-anomaly-v1"
LIMITATIONS = [
    "An anomaly is an unusual value, not evidence of cause or operational severity.",
    "Seasonal baselines are used only when configured minimum matching periods exist.",
    "Isolation Forest is fitted once on the initial minimum historical baseline to bound CPU cost.",
]


class AnomalyResultList(list):
    """List subclass preserving total anomaly count and cap status for callers."""
    def __init__(self, items: list[dict[str, Any]], total_anomalies: int, cap: int, is_capped: bool):
        super().__init__(items)
        self.total_anomalies = total_anomalies
        self.cap = cap
        self.is_capped = is_capped

    def get(self, key: str, default: Any = None) -> Any:
        if key == "anomalies":
            return list(self)
        if key == "total_anomalies":
            return self.total_anomalies
        if key == "cap":
            return self.cap
        if key == "is_capped":
            return self.is_capped
        return default


def detect_canonical_anomalies(records: list[dict[str, Any]], settings: Any) -> AnomalyResultList:
    """Run configured detectors against earlier observations in each entity window."""
    frame = pd.DataFrame(records)
    if frame.empty or "event_timestamp" not in frame:
        return AnomalyResultList([], 0, 2000, False)
    frame["_time"] = pd.to_datetime(frame["event_timestamp"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["_time"])
    output: list[dict[str, Any]] = []

    for metric, spec in settings.canonical_metrics.items():
        if metric not in frame:
            continue
        frame["_value"] = pd.to_numeric(frame[metric], errors="coerce")
        groupings = [[role for role in grouping if role in frame.columns]
                     for grouping in spec.get("entity_groupings", [spec.get("entity_roles", [])])]
        groupings = [roles for roles in groupings if roles] or [["_all_records"]]
        if groupings == [["_all_records"]]:
            frame["_all_records"] = "all"

        for entity_roles in groupings:
            grouped = frame.groupby(entity_roles, dropna=False, sort=False)
            for _entity_value, group in grouped:
                ordered = group.sort_values("_time", kind="stable")
                if len(ordered) > 1000:
                    ordered = ordered.tail(1000)

                vals = ordered["_value"].to_numpy(dtype=float)
                ref_series = ordered.get("source_record_ref")
                if ref_series is None or ref_series.isna().all():
                    ref_series = ordered.get("event_id", pd.Series(range(len(ordered))))
                refs = ref_series.astype(str).to_numpy()

                initial_clean = vals[~np.isnan(vals)][:settings.minimum_baseline_records]
                isolation_model = None
                if len(initial_clean) >= settings.minimum_baseline_records:
                    try:
                        from sklearn.ensemble import IsolationForest
                        isolation_model = IsolationForest(
                            contamination=settings.isolation_forest_contamination,
                            n_estimators=min(50, settings.isolation_forest_estimators),
                            random_state=settings.random_seed,
                        )
                        isolation_model.fit(initial_clean.reshape(-1, 1))
                    except (ImportError, ValueError):
                        pass

                entity_dict = {}
                first_row = ordered.iloc[0]
                for role in entity_roles:
                    if role != "_all_records":
                        entity_dict[role] = first_row[role]

                threshold = float(spec.get("rule_threshold", 0))
                direction = spec.get("rule_direction", "above")
                sev_crit = float(spec.get("severity_critical", 6))
                sev_high = float(spec.get("severity_high", 3))

                for position in range(len(vals)):
                    value = vals[position]
                    if np.isnan(value):
                        continue
                    window_start = max(0, position - settings.rolling_window_records)
                    history = vals[window_start:position]
                    history = history[~np.isnan(history)]
                    if len(history) < settings.minimum_baseline_records:
                        continue

                    median = float(np.median(history))
                    q1, q3 = float(np.percentile(history, 25)), float(np.percentile(history, 75))
                    spread = q3 - q1
                    mad = float(np.median(np.abs(history - median)))
                    scale = 1.4826 * mad
                    lower = q1 - settings.iqr_multiplier * spread
                    upper = q3 + settings.iqr_multiplier * spread

                    # Clip lower bound for non-negative measures to avoid negative thresholds
                    if len(history) > 0 and np.nanmin(history) >= 0.0:
                        lower = max(0.0, lower)

                    robust_score = abs(value - median) / scale if scale > 0 else 0.0

                    rule_flag = (abs(value) > threshold if direction == "absolute" else
                                 value > threshold if direction == "above" else value < threshold)
                    methods = {
                        "rule": (rule_flag, median, value - median),
                        "robust_zscore": (robust_score > settings.robust_z_threshold, median, robust_score),
                        "iqr": (value < lower or value > upper,
                                median, max(lower - value, value - upper, 0.0)),
                    }
                    if isolation_model is not None and position >= settings.minimum_baseline_records:
                        pt = np.array([[value]])
                        # Isolation Forest assigns individual sample anomaly score to each record
                        methods["isolation_forest"] = (
                            bool(isolation_model.predict(pt)[0] == -1),
                            median, float(-isolation_model.score_samples(pt)[0]),
                        )

                    severity_score = max(
                        robust_score,
                        float(value - upper) / max(abs(upper), 1.0),
                        float(lower - value) / max(abs(lower), 1.0),
                    )
                    severity = ("CRITICAL" if severity_score >= sev_crit else
                                "HIGH" if severity_score >= sev_high else "LOW")

                    for method, (flagged, baseline, score) in methods.items():
                        if not flagged:
                            continue
                        output.append({
                            "entity": entity_dict,
                            "entity_grouping": entity_roles,
                            "record_refs": [refs[position]],
                            "metric": metric,
                            "observed_value": float(value),
                            "baseline": float(baseline),
                            "expected_range": {"lower": float(lower), "upper": float(upper)},
                            "method": method,
                            "version": ENGINE_VERSION,
                            "severity": severity,
                            "score": float(score),
                            "limitations": LIMITATIONS.copy(),
                            "seasonal_baseline_used": False,
                        })

    # Weekly aggregated demand anomalies per product (detect sudden demand spikes)
    prod_col = next((c for c in ("product_id", "sku", "item_id") if c in frame.columns), None)
    qty_col = next((c for c in ("quantity", "order_quantity", "demand") if c in frame.columns), None)
    if prod_col and qty_col and "_time" in frame.columns:
        frame_copy = frame.copy()
        frame_copy["_week"] = frame_copy["_time"].dt.to_period("W").dt.to_timestamp()
        frame_copy["_qty_num"] = pd.to_numeric(frame_copy[qty_col], errors="coerce").fillna(0.0)

        for p_val, p_group in frame_copy.groupby(prod_col):
            weekly = p_group.groupby("_week", as_index=False).agg(
                weekly_qty=("_qty_num", "sum"),
                refs=("source_record_ref", lambda s: list(s.dropna().astype(str))[:5] if "source_record_ref" in p_group.columns else [])
            ).sort_values("_week")

            p_vals = weekly["weekly_qty"].to_numpy(dtype=float)
            if len(p_vals) < 3:
                continue
            p_refs = weekly["refs"].tolist()
            p_weeks = weekly["_week"].tolist()

            for pos in range(len(p_vals)):
                val = p_vals[pos]
                hist = p_vals[:pos] if pos >= 3 else p_vals
                hist = hist[~np.isnan(hist)]
                if len(hist) < 3:
                    continue
                med = float(np.median(hist))
                q1, q3 = float(np.percentile(hist, 25)), float(np.percentile(hist, 75))
                iqr_sp = q3 - q1
                up_bound = q3 + 2.0 * iqr_sp
                mad = float(np.median(np.abs(hist - med)))
                scale = 1.4826 * mad
                rob_score = (val - med) / scale if scale > 0 else 0.0

                if val > up_bound and (val - med) > 0 and rob_score > 2.5:
                    sample_refs = p_refs[pos] if p_refs[pos] else [f"{p_val}@{p_weeks[pos].isoformat()}"]
                    output.append({
                        "entity": {prod_col: p_val},
                        "entity_grouping": [prod_col],
                        "record_refs": sample_refs,
                        "metric": "weekly_demand",
                        "observed_value": float(val),
                        "baseline": float(med),
                        "expected_range": {"lower": 0.0, "upper": float(up_bound)},
                        "method": "weekly_demand_spike",
                        "version": ENGINE_VERSION,
                        "severity": "CRITICAL" if rob_score >= 5.0 else "HIGH",
                        "score": float(rob_score),
                        "limitations": LIMITATIONS.copy(),
                        "seasonal_baseline_used": False,
                    })

    # Rank anomalies by severity descending, then score descending
    sev_rank = {"CRITICAL": 3, "HIGH": 2, "LOW": 1}
    def rank_key(a: dict[str, Any]) -> tuple[int, float]:
        s_val = sev_rank.get(str(a.get("severity", "LOW")).upper(), 0)
        return (s_val, float(a.get("score") or 0.0))

    sorted_output = sorted(output, key=rank_key, reverse=True)
    total_anomalies = len(sorted_output)
    cap = 2000
    is_capped = total_anomalies > cap
    capped_list = sorted_output[:cap]

    return AnomalyResultList(capped_list, total_anomalies=total_anomalies, cap=cap, is_capped=is_capped)
