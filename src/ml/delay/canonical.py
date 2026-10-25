"""Leakage-checked, chronological delay-risk evaluation on canonical records."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from src.ml.delay.evaluation import chronological_split, classification_metrics

LEAKAGE_NOTE = "Rule or model output is a prediction, not an observed outcome or cause."
OUTCOME_TOKENS = (
    "postoutcome", "outcome", "actual", "delivered", "late", "delayrisk",
    "deliveryrisk", "shippingreal", "daysforshippingreal", "status", "arrival",
    "delay", "delivered_timestamp", "delivered_ts", "arrival_date", "days_late",
    "delivery_status",
)
IDENTIFIER_ROLES = {
    "order_id", "shipment_id", "source", "event_id", "source_record_ref",
    "snapshot_id", "custom_fields", "id", "_quarantine_reason", "_source",
}


def _normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _detect_column_leakage_reason(name: str, series: pd.Series | None = None,
                                  delay_label: pd.Series | None = None) -> str | None:
    """Detect whether a column leaks post-outcome information and return the reason."""
    norm = _normalized(name)
    if "delivered" in norm or norm in {"arrivaldate", "arrivalts", "deliveredts", "deliveredtimestamp"}:
        return f"Column '{name}' is mapped to or represents delivered time (temporal outcome leakage)"
    for token in ("status", "late", "delay", "actual", "arrival", "outcome", "postoutcome"):
        if token in norm:
            return f"Outcome-style name '{token}' in '{name}' indicates post-event outcome information"
    if series is not None and delay_label is not None and len(series) == len(delay_label):
        try:
            num_series = pd.to_numeric(series, errors="coerce")
            if num_series.notna().sum() > 20 and delay_label.notna().sum() > 20:
                corr = abs(float(num_series.corr(delay_label)))
                if corr >= 0.95:
                    return f"Column '{name}' has near-perfect correlation ({corr:.4f} >= 0.95) with delay outcome"
        except Exception:
            pass
    return None


def evaluate_canonical_delay(records: list[dict[str, Any]], settings: Any,
                             overrides: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Fit logistic regression only when chronological records exist, blocking post-outcome features."""
    overrides = overrides or []
    override_map = {item.get("column", ""): item.get("reason", "") for item in overrides if item.get("column")}

    # Check allowlist for leaky tokens early
    raw_allowlist = list(getattr(settings, "feature_allowlist", ["quantity", "price", "supplier_id", "product_id", "carrier"]))
    leaky_in_allowlist = [f for f in raw_allowlist if _detect_column_leakage_reason(f) and f not in override_map]
    if leaky_in_allowlist and not records:
        return {
            "status": "LEAKAGE_BLOCKED",
            "trained": False,
            "blocked": leaky_in_allowlist,
            "blocked_features": leaky_in_allowlist,
            "missing": ["clean feature allowlist"],
            "message": f"Allowlist contains leaky outcome features: {leaky_in_allowlist}",
            "limitations": [LEAKAGE_NOTE],
        }

    if not records:
        return {"status": "MISSING_DATA", "trained": False, "missing": ["canonical records"]}

    # 1. Derive or locate binary delay label
    target = getattr(settings, "label_role", "post_outcome")
    records_df = pd.DataFrame(records)

    # Unpack custom_fields if available
    if "custom_fields" in records_df.columns:
        for col in ("days_late", "delivery_status", "status", "carrier", "route"):
            if col not in records_df.columns:
                records_df[col] = records_df["custom_fields"].apply(
                    lambda cf: cf.get(col) if isinstance(cf, dict) else None
                )

    # If records come from multiple tables sharing an order key, consolidate order attributes
    if "order_id" in records_df.columns and records_df["order_id"].notna().any():
        order_records = records_df.dropna(subset=["order_id"]).groupby("order_id", as_index=False).first()
        non_order = records_df[records_df["order_id"].isna()]
        records_df = pd.concat([order_records, non_order], ignore_index=True) if not non_order.empty else order_records

    # Derive label if not explicitly present or if target is post_outcome
    derived_target = False
    if target not in records_df.columns or target == "post_outcome":
        has_dates = "delivered_timestamp" in records_df.columns and "promised_timestamp" in records_df.columns
        if has_dates:
            p_dt = pd.to_datetime(records_df["promised_timestamp"], errors="coerce", utc=True)
            d_dt = pd.to_datetime(records_df["delivered_timestamp"], errors="coerce", utc=True)
            valid_mask = p_dt.notna() & d_dt.notna()
            if valid_mask.sum() >= 10:
                records_df["delay_label"] = np.nan
                records_df.loc[valid_mask, "delay_label"] = (d_dt[valid_mask] > p_dt[valid_mask]).astype(int)
                target = "delay_label"
                derived_target = True
        if not derived_target and "days_late" in records_df.columns:
            nums = pd.to_numeric(records_df["days_late"], errors="coerce")
            if nums.notna().sum() >= 10:
                records_df["delay_label"] = (nums > 0).astype(int)
                target = "delay_label"
                derived_target = True
        elif not derived_target and "status" in records_df.columns:
            status_series = records_df["status"].astype(str).str.lower()
            if (status_series == "late").sum() >= 10:
                records_df["delay_label"] = (status_series == "late").astype(int)
                target = "delay_label"
                derived_target = True
        elif not derived_target and "delivery_status" in records_df.columns:
            status_series = records_df["delivery_status"].astype(str).str.lower()
            if (status_series == "late").sum() >= 10:
                records_df["delay_label"] = (status_series == "late").astype(int)
                target = "delay_label"
                derived_target = True

    if target not in records_df.columns:
        return {
            "status": "MISSING_LABELS",
            "trained": False,
            "missing": [getattr(settings, "label_role", "post_outcome"), "order_id", "promised_timestamp", "delivered_timestamp"],
            "message": "Missing canonical delay target or promised/delivered timestamp pair",
        }

    pred_time_col = getattr(settings, "prediction_time_role", "event_timestamp")
    if pred_time_col not in records_df.columns:
        if "order_ts" in records_df.columns:
            pred_time_col = "order_ts"
        elif "event_timestamp" in records_df.columns:
            pred_time_col = "event_timestamp"
        else:
            pred_time_col = records_df.columns[0]

    # Filter usable records
    records_df[pred_time_col] = pd.to_datetime(records_df[pred_time_col], errors="coerce", utc=True)
    usable_df = records_df.dropna(subset=[pred_time_col, target]).copy()
    usable_df[target] = pd.to_numeric(usable_df[target], errors="coerce").astype(int)

    if len(usable_df) < getattr(settings, "minimum_training_rows", 20):
        return {
            "status": "INSUFFICIENT_HISTORY",
            "trained": False,
            "labelled_rows": len(usable_df),
            "required_training_rows": getattr(settings, "minimum_training_rows", 20),
            "missing": ["more chronological training records"],
            "limitations": [LEAKAGE_NOTE],
        }

    # 2. Exclude identifier columns (order_id, shipment_id, source, etc.)
    # and perform automatic leakage screening
    candidate_features = [
        c for c in records_df.columns
        if c not in {target, pred_time_col} and c not in IDENTIFIER_ROLES and not c.startswith("_")
    ]
    all_candidates = list(dict.fromkeys([
        c for c in raw_allowlist if c not in IDENTIFIER_ROLES and c in usable_df.columns
    ] + [c for c in candidate_features if c in usable_df.columns]))

    blocked_columns: list[dict[str, str]] = []
    allowed_features: list[str] = []
    recorded_overrides: list[dict[str, str]] = []

    for col in all_candidates:
        if col not in usable_df.columns or col == target or col in IDENTIFIER_ROLES:
            continue
        leak_reason = _detect_column_leakage_reason(col, usable_df[col], usable_df[target])
        if leak_reason:
            if col in override_map and override_map[col].strip():
                recorded_overrides.append({"column": col, "reason": override_map[col], "status": "ANALYST_OVERRIDDEN"})
                allowed_features.append(col)
            else:
                blocked_columns.append({"column": col, "reason": leak_reason})
        else:
            allowed_features.append(col)

    # Clean allowed features (must be present with non-null values and not identifiers)
    allowed_features = [
        f for f in allowed_features
        if f in usable_df.columns and usable_df[f].notna().sum() > 0 and f not in IDENTIFIER_ROLES
    ]
    if not allowed_features:
        allowed_features = [
            c for c in ("quantity", "price", "supplier_id", "product_id", "carrier")
            if c in usable_df.columns and c not in IDENTIFIER_ROLES
        ]

    # 3. Chronological Train / Val / Test Split
    train_frac = getattr(settings, "train_fraction", 0.7)
    val_frac = getattr(settings, "validation_fraction", 0.15)
    usable_df = usable_df.sort_values(pred_time_col, kind="stable").reset_index(drop=True)
    train, validation, test = chronological_split(usable_df, pred_time_col, train_frac, val_frac)

    # 4. Train baselines and Logistic Regression
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer

    y_train = train[target].astype(int)
    y_test = test[target].astype(int)

    majority = DummyClassifier(strategy="most_frequent").fit(train[allowed_features], y_train)
    baseline_probs = majority.predict_proba(test[allowed_features])[:, 1]

    # Supplier rate heuristic rule
    sup_col = next((c for c in ("supplier_id", "vendor_code") if c in usable_df.columns), None)
    if sup_col:
        rates = train.groupby(sup_col)[target].mean().to_dict()
        global_rate = float(y_train.mean())
        rule_probs = test[sup_col].map(rates).fillna(global_rate).to_numpy()
    else:
        rule_probs = np.full(len(test), float(y_train.mean()))

    # ML Model (Logistic Regression)
    numeric = [f for f in allowed_features if pd.api.types.is_numeric_dtype(usable_df[f])]
    categorical = [f for f in allowed_features if f not in numeric]

    transformer = ColumnTransformer([
        ("numeric", Pipeline([("fill", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
        ("categorical", Pipeline([("fill", SimpleImputer(strategy="most_frequent")),
                                   ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
    ], remainder="drop")

    model = Pipeline([
        ("features", transformer),
        ("model", LogisticRegression(max_iter=1000, random_state=getattr(settings, "random_seed", 42), class_weight="balanced")),
    ])
    try:
        model.fit(train[allowed_features], y_train)
        model_probs = model.predict_proba(test[allowed_features])[:, 1]
        trained = True
    except Exception:
        model_probs = rule_probs
        trained = False

    prob_threshold = getattr(settings, "probability_threshold", 0.5)

    # 5. Extract drivers of delay with weekly change-point detection & interaction pairs
    overall_mean = float(usable_df[target].mean())

    # Build interaction pairs if columns are available
    if "carrier" in usable_df.columns and "route" in usable_df.columns:
        usable_df["carrier_x_route"] = usable_df["carrier"].astype(str) + " x " + usable_df["route"].astype(str)
    if "supplier_id" in usable_df.columns and "product_id" in usable_df.columns:
        usable_df["supplier_x_product"] = usable_df["supplier_id"].astype(str) + " x " + usable_df["product_id"].astype(str)

    usable_df["_week"] = usable_df[pred_time_col].dt.to_period("W").dt.to_timestamp()

    candidate_factors = [
        c for c in ("supplier_id", "carrier", "warehouse_id", "product_id", "route", "carrier_x_route", "supplier_x_product")
        if c in usable_df.columns
    ]

    all_driver_candidates: list[dict[str, Any]] = []

    for d_col in candidate_factors:
        grouped = usable_df.groupby(d_col).agg(
            total=(target, "count"),
            delays=(target, "sum"),
            delay_rate=(target, "mean"),
        ).reset_index()

        valid_groups = grouped[grouped["total"] >= 15].copy()
        for _, grow in valid_groups.iterrows():
            d_val = str(grow[d_col])
            d_rate = float(grow["delay_rate"])
            diff = d_rate - overall_mean
            if diff > 0.02:
                # Change-point detection on weekly late-rate series
                sub_df = usable_df[usable_df[d_col].astype(str) == d_val].sort_values(pred_time_col)
                weekly_series = sub_df.groupby("_week").agg(
                    w_total=(target, "count"),
                    w_late=(target, "sum"),
                ).reset_index().sort_values("_week")

                est_start_date = None
                pre_rate = overall_mean
                post_rate = d_rate
                pre_sup = 0
                post_sup = int(grow["total"])

                if len(weekly_series) >= 2:
                    best_shift = -999.0
                    best_tau = 0
                    for tau in range(1, len(weekly_series)):
                        pre_slice = weekly_series.iloc[:tau]
                        post_slice = weekly_series.iloc[tau:]
                        p_tot = pre_slice["w_total"].sum()
                        po_tot = post_slice["w_total"].sum()
                        if p_tot >= 3 and po_tot >= 3:
                            pr_r = pre_slice["w_late"].sum() / p_tot
                            po_r = post_slice["w_late"].sum() / po_tot
                            shift = po_r - pr_r
                            if shift > best_shift:
                                best_shift = shift
                                best_tau = tau
                                pre_rate = pr_r
                                post_rate = po_r
                                pre_sup = int(p_tot)
                                post_sup = int(po_tot)

                    if best_tau > 0:
                        est_start_date = weekly_series.iloc[best_tau]["_week"].isoformat()

                if est_start_date is None:
                    earliest = sub_df[sub_df[target] == 1][pred_time_col].min()
                    est_start_date = earliest.isoformat() if pd.notna(earliest) else None

                all_driver_candidates.append({
                    "driver": f"{d_col}: {d_val}",
                    "factor": d_col,
                    "value": d_val,
                    "delay_rate": round(d_rate, 4),
                    "baseline_delay_rate": round(overall_mean, 4),
                    "difference": round(diff, 4),
                    "estimated_start_date": est_start_date,
                    "pre_change_rate": round(pre_rate, 4),
                    "post_change_rate": round(post_rate, 4),
                    "pre_support": pre_sup,
                    "post_support": post_sup,
                    "sample_size": int(grow["total"]),
                    "status": "UNVERIFIED",
                })

    # Sort all candidates by difference descending
    all_driver_candidates = sorted(all_driver_candidates, key=lambda x: x["difference"], reverse=True)

    # 6. Confounding check: re-test other drivers excluding the top driver's records
    top_drivers: list[dict[str, Any]] = []
    if all_driver_candidates:
        top_driver = all_driver_candidates[0]
        top_driver["confounded"] = False
        top_driver["confounding_status"] = "primary_driver"
        top_drivers.append(top_driver)

        # Subset excluding top driver records
        top_col = top_driver["factor"]
        top_val = str(top_driver["value"])
        unconfounded_df = usable_df[usable_df[top_col].astype(str) != top_val]
        unconfounded_mean = float(unconfounded_df[target].mean()) if len(unconfounded_df) > 0 else overall_mean

        for candidate in all_driver_candidates[1:]:
            c_col = candidate["factor"]
            c_val = str(candidate["value"])
            c_sub = unconfounded_df[unconfounded_df[c_col].astype(str) == c_val]

            if len(c_sub) >= 5:
                c_new_rate = float(c_sub[target].mean())
                c_new_diff = c_new_rate - unconfounded_mean
                if c_new_diff <= 0.02:
                    candidate["confounded"] = True
                    candidate["confounding_status"] = f"explained by {top_driver['driver']}"
                    candidate["difference_after_exclusion"] = round(c_new_diff, 4)
                else:
                    candidate["confounded"] = False
                    candidate["confounding_status"] = "independent"
                    candidate["difference_after_exclusion"] = round(c_new_diff, 4)
            else:
                candidate["confounded"] = True
                candidate["confounding_status"] = f"explained by {top_driver['driver']}"
                candidate["difference_after_exclusion"] = 0.0

            top_drivers.append(candidate)

    # Limit top drivers to 5 ranked candidates
    top_drivers = top_drivers[:5]

    return {
        "status": "COMPUTED",
        "trained": trained,
        "prediction_time_role": pred_time_col,
        "label_role": target,
        "features": allowed_features,
        "split": {
            "method": "chronological",
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "train_end": str(train[pred_time_col].max()),
            "test_start": str(test[pred_time_col].min()),
        },
        "models": {
            "majority_baseline": {
                "kind": "baseline",
                "trained": False,
                "metrics": classification_metrics(y_test, baseline_probs, prob_threshold),
            },
            "supplier_history_rule": {
                "kind": "rule",
                "trained": False,
                "metrics": classification_metrics(y_test, rule_probs, prob_threshold),
            },
            "logistic_regression": {
                "kind": "trained_model",
                "trained": trained,
                "metrics": classification_metrics(y_test, model_probs, prob_threshold),
            },
        },
        "explanations": {
            "logistic_regression": {
                "status": "COMPUTED" if trained else "NOT_TRAINED",
                "note": "contribution, not cause",
            },
        },
        "top_drivers": top_drivers,
        "leakage_handling": {
            "blocked_columns": blocked_columns,
            "allowed_features": allowed_features,
            "overrides": recorded_overrides,
            "split_method": "temporal_chronological_split",
        },
        "leakage_check": {
            "post_outcome_used_as_predictor": any(col == "post_outcome" for col in allowed_features),
            "blocked_columns": [b["column"] for b in blocked_columns],
        },
        "limitations": [
            LEAKAGE_NOTE,
            "Training output is not proof of a delay cause.",
            "Post-outcome columns and near-perfect correlation features are blocked to prevent leakage.",
            "Identifier roles are strictly excluded from model feature sets.",
        ],
    }
