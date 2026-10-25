"""Time-ordered classification evaluation, model baselines and reproducible artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def chronological_split(frame: pd.DataFrame, timestamp_column: str, train_fraction: float = 0.6,
                        validation_fraction: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Sort by timestamp and split without shuffling; missing timestamps are rejected."""
    if timestamp_column not in frame:
        raise ValueError(f"Missing timestamp column: {timestamp_column}")
    ordered = frame.sort_values(timestamp_column, kind="stable").reset_index(drop=True)
    if ordered[timestamp_column].isna().any():
        raise ValueError("Chronological split requires non-null timestamps")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("Split fractions must be positive and sum to less than one")
    train_end = int(len(ordered) * train_fraction)
    validation_end = train_end + int(len(ordered) * validation_fraction)
    return ordered.iloc[:train_end], ordered.iloc[train_end:validation_end], ordered.iloc[validation_end:]


def classification_metrics(y_true: Any, probabilities: Any, threshold: float = 0.5) -> dict[str, Any]:
    """Compute requested metrics, calibration bins and confusion matrix."""
    from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                                 f1_score, precision_score, recall_score, roc_auc_score)
    from sklearn.calibration import calibration_curve

    y = np.asarray(y_true, dtype=int)
    prob = np.asarray(probabilities, dtype=float)
    pred = prob >= threshold
    matrix = confusion_matrix(y, pred, labels=[0, 1]).tolist()
    calibration_true, calibration_pred = calibration_curve(y, prob, n_bins=10, strategy="uniform")
    return {
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "pr_auc": float(average_precision_score(y, prob)),
        "roc_auc": float(roc_auc_score(y, prob)) if len(np.unique(y)) == 2 else None,
        "confusion_matrix_labels_0_1": matrix,
        "brier_score": float(brier_score_loss(y, prob)),
        "calibration_curve": [{"mean_predicted_probability": float(p), "fraction_positive": float(t)}
                              for t, p in zip(calibration_true, calibration_pred)],
        "threshold": threshold,
    }


def subgroup_errors(y_true: Any, probabilities: Any, groups: Any, threshold: float = 0.5) -> dict[str, Any]:
    """Summarize subgroup count and false-positive/false-negative rates."""
    y = np.asarray(y_true, dtype=int)
    pred = np.asarray(probabilities, dtype=float) >= threshold
    group_series = pd.Series(groups).fillna("UNKNOWN").astype(str)
    result = {}
    for group in sorted(group_series.unique()):
        mask = group_series.to_numpy() == group
        positives, negatives = y[mask] == 1, y[mask] == 0
        result[group] = {
            "rows": int(mask.sum()),
            "false_positive_rate": float(((pred[mask] == 1) & negatives).sum() / negatives.sum()) if negatives.any() else None,
            "false_negative_rate": float(((pred[mask] == 0) & positives).sum() / positives.sum()) if positives.any() else None,
        }
    return result


def data_hash(frame: pd.DataFrame) -> str:
    """Stable SHA-256 over ordered feature/label CSV serialization."""
    return hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()


def build_models(seed: int, max_depth: int, forest_estimators: int) -> dict[str, Any]:
    """Construct requested models with fixed seed; returns sklearn estimators."""
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier

    def pipeline(model: Any, numeric: list[str], categorical: list[str], scale: bool = False) -> Pipeline:
        num_steps = [("imputer", SimpleImputer(strategy="median"))]
        if scale:
            num_steps.append(("scaler", StandardScaler()))
        transform = ColumnTransformer([
            ("numeric", Pipeline(num_steps), numeric),
            ("categorical", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                                       ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ])
        return Pipeline([("features", transform), ("model", model)])

    return {"logistic_regression": lambda n, c: pipeline(LogisticRegression(max_iter=1000, random_state=seed), n, c, True),
            "decision_tree": lambda n, c: pipeline(DecisionTreeClassifier(max_depth=max_depth, random_state=seed), n, c),
            "random_forest": lambda n, c: pipeline(RandomForestClassifier(n_estimators=forest_estimators,
                                                                           max_depth=max_depth, random_state=seed,
                                                                           n_jobs=1, class_weight="balanced"), n, c)}


def evaluate_classification(dataset: str, frame: pd.DataFrame, *, label: str, timestamp: str,
                            features: list[str], subgroup: str, archive_hash: str,
                            config: dict[str, Any], models_dir: Path | str = "models",
                            audit_log_path: Path | str | None = None,
                            registry_path: Path | str = "src/ml/model_registry.json") -> dict[str, Any]:
    """Train baselines/models, evaluate validation/test, save artifacts and registry."""
    from sklearn.dummy import DummyClassifier
    import joblib
    train, validation, test = chronological_split(frame, timestamp, config["train_fraction"], config["validation_fraction"])
    if train.empty or validation.empty or test.empty:
        raise ValueError("Time split produced an empty partition")
    categorical = [c for c in features if not pd.api.types.is_numeric_dtype(frame[c])]
    numeric = [c for c in features if c not in categorical]
    y_train, y_val, y_test = train[label].astype(int), validation[label].astype(int), test[label].astype(int)
    output: dict[str, Any] = {"dataset": dataset, "split": {"method": "chronological", "train_rows": len(train),
        "validation_rows": len(validation), "test_rows": len(test), "train_end": str(train[timestamp].max()),
        "validation_end": str(validation[timestamp].max()), "test_start": str(test[timestamp].min())}, "models": {}}
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    specs: dict[str, Any] = {"baseline_majority": DummyClassifier(strategy="most_frequent"),
                             "baseline_simple_rule": None}
    specs.update({name: factory(numeric, categorical) for name, factory in build_models(
        config["random_seed"], config["tree_max_depth"], config["random_forest_estimators"]).items()})
    for name, model in specs.items():
        if name == "baseline_simple_rule":
            # Transparent rule baseline uses the split's scheduled/estimated duration feature.
            rule_feature = config.get("simple_rule_feature")
            cutoff = config.get("simple_rule_threshold")
            if not rule_feature or rule_feature not in features:
                continue
            val_prob = (validation[rule_feature].astype(float) <= cutoff).astype(float).to_numpy()
            test_prob = (test[rule_feature].astype(float) <= cutoff).astype(float).to_numpy()
        else:
            model.fit(train[features], y_train)
            val_prob = model.predict_proba(validation[features])[:, 1]
            test_prob = model.predict_proba(test[features])[:, 1]
        model_result = {"validation": classification_metrics(y_val, val_prob),
                        "test": classification_metrics(y_test, test_prob),
                        "test_subgroup_errors": subgroup_errors(y_test, test_prob, test[subgroup]) if subgroup in test else {}}
        output["models"][name] = model_result
        version = f"{dataset}-{name}-v1"
        artifact_path = models_dir / f"{version}.joblib" if model is not None else None
        if model is not None:
            joblib.dump(model, artifact_path)
        test_frame = test[[*features, label]].copy()
        evaluation_context = {"method": "chronological", "timestamp": timestamp,
            "test_rows": int(len(test)), "test_start": str(test[timestamp].min()),
            "test_end": str(test[timestamp].max()), "test_data_hash": data_hash(test_frame)}
        entry = {"dataset": dataset, "name": name, "version": version,
            "artifact": str(artifact_path) if artifact_path else None,
            "data_hash": archive_hash, "features": features, "label": label,
            "config": config, "metrics": model_result, "evaluation_context": evaluation_context}
        from src.ml.registry import register_model
        register_model(registry_path, entry)
        if audit_log_path is not None:
            from src.core.audit import AuditLog
            AuditLog(audit_log_path).append(event_type="model_version_registered", actor="system",
                source=dataset, record_refs=[version], details={"model_name": name,
                    "data_hash": archive_hash, "evaluation_context": evaluation_context,
                    "feature_names": features, "config": config})
        report_path = models_dir / "evaluations" / f"{version}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_payload = {
            "model_version": version,
            "dataset": dataset,
            "data_version": str(config.get("data_version") or archive_hash),
            "data_hash": archive_hash,
            "mapping_version": str(config.get("mapping_version", "v1")),
            "seed": int(config.get("random_seed", 42)),
            "features": features,
            "label": label,
            "config": config,
            "split": output["split"],
            "evaluation_context": evaluation_context,
            "metrics": model_result,
            "limitations": [
                "Evaluation describes this chronological holdout only.",
                "Feature contribution, not proven cause.",
            ],
        }
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return output
