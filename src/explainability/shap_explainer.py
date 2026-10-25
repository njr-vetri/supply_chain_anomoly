"""Persist SHAP feature contributions for a selected tree or linear classifier."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EXPLANATION_NOTE = "feature contribution, not proven cause"


def explain_model(model: Any, samples: pd.DataFrame, *, model_version: str,
                  output_path: Path | str) -> dict[str, Any]:
    """Explain a fitted sklearn estimator/pipeline and write a versioned JSON record."""
    try:
        import shap
    except ImportError as exc:
        raise RuntimeError("SHAP explanations require the shap dependency") from exc
    pipeline = hasattr(model, "named_steps") and "model" in model.named_steps
    estimator = model.named_steps["model"] if pipeline else model
    transformed = model.named_steps["features"].transform(samples) if pipeline else samples
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    transformed = np.asarray(transformed)
    if pipeline:
        try:
            feature_names = list(model.named_steps["features"].get_feature_names_out())
        except Exception:
            feature_names = [f"feature_{i}" for i in range(transformed.shape[1])]
    else:
        feature_names = list(samples.columns)
    if hasattr(estimator, "estimators_") or hasattr(estimator, "tree_"):
        explainer = shap.TreeExplainer(estimator)
        explanation = explainer(transformed)
    elif hasattr(estimator, "coef_"):
        background = transformed[: min(len(transformed), 100)]
        explainer = shap.LinearExplainer(estimator, background)
        explanation = explainer(transformed)
    else:
        raise TypeError("Selected model must be a fitted tree or linear estimator")
    values = np.asarray(explanation.values)
    if values.ndim == 3:
        values = values[:, :, -1]
    base_values = np.asarray(explanation.base_values)
    if base_values.ndim > 1:
        base_values = base_values[:, -1]
    artifact = {
        "model_version": model_version,
        "explanation_type": "SHAP feature contributions",
        "note": EXPLANATION_NOTE,
        "samples": [{"record_ref": str(index), "base_value": float(base_values[i] if base_values.ndim else base_values),
                     "contributions": {name: float(value) for name, value in zip(feature_names, values[i])}}
                    for i, (index, _) in enumerate(samples.iterrows())],
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact
