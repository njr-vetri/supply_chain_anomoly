"""Unified explanations for fitted models, transparent rules and baselines."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.explainability.shap_explainer import explain_model

EXPLANATION_NOTE = "contribution, not cause"


def explain_result(*, method: str, record_ref: str, output_path: Path | str,
                   model: Any = None, model_version: str | None = None,
                   features: dict[str, Any] | None = None,
                   baseline: Any = None, rule: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write SHAP for compatible fitted estimators or a transparent rule/baseline trace."""
    destination = Path(output_path)
    if method == "model" and model is not None:
        if not (hasattr(model, "named_steps") or hasattr(model, "estimators_") or
                hasattr(model, "tree_") or hasattr(model, "coef_")):
            raise TypeError("SHAP requires a compatible fitted tree or linear model")
        frame = pd.DataFrame([features or {}], index=[record_ref])
        result = explain_model(model, frame, model_version=model_version or "UNKNOWN", output_path=destination)
        result["note"] = EXPLANATION_NOTE
        destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    if method not in {"rule", "baseline"}:
        raise ValueError("method must be model, rule, or baseline")
    result = {"record_ref": record_ref, "explanation_type": f"{method}_explanation",
              "method": method, "baseline": baseline, "rule": rule or {},
              "features": features or {}, "model_version": model_version,
              "note": EXPLANATION_NOTE,
              "limitations": ["This explanation describes the decision rule or baseline only."]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def explain_fitted_record(model: Any, sample: pd.DataFrame, *, model_version: str,
                          background: pd.DataFrame | None = None) -> dict[str, Any]:
    """Return a single-record SHAP explanation without writing an artifact."""
    try:
        import numpy as np
        import shap
        estimator = model.named_steps["model"] if hasattr(model, "named_steps") else model
        transformed = model.named_steps["features"].transform(sample) if hasattr(model, "named_steps") else sample
        if hasattr(transformed, "toarray"):
            transformed = transformed.toarray()
        transformed = np.asarray(transformed, dtype=float)
        if hasattr(model, "named_steps"):
            names = list(model.named_steps["features"].get_feature_names_out())
            background_frame = background if background is not None else sample
            train_features = model.named_steps["features"].transform(background_frame)
        else:
            names = list(sample.columns)
            train_features = transformed
        if hasattr(train_features, "toarray"):
            train_features = train_features.toarray()
        train_features = np.asarray(train_features, dtype=float)
        explainer = (shap.TreeExplainer(estimator) if hasattr(estimator, "tree_") or
                     hasattr(estimator, "estimators_") else shap.LinearExplainer(estimator, train_features))
        explanation = explainer(transformed)
        values = np.asarray(explanation.values)
        if values.ndim == 3:
            values = values[0, :, -1]
        else:
            values = values[0]
        base = np.asarray(explanation.base_values)
        base_value = float(base.flat[-1])
        return {"status": "COMPUTED", "method": "SHAP",
                "record_ref": str(sample.index[0]), "model_version": model_version,
                "base_value": base_value,
                "contributions": {name: float(value) for name, value in zip(names, values)},
                "note": EXPLANATION_NOTE}
    except Exception as exc:  # noqa: BLE001 - model scores remain available if explainability fails.
        return {"status": "NOT_COMPUTED", "method": "SHAP", "model_version": model_version,
                "reason": type(exc).__name__, "note": EXPLANATION_NOTE}
