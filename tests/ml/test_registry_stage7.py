"""Synthetic registry fixtures verify approval and rollback mechanics only."""
import json

import pytest
import pandas as pd

from src.ml.delay.evaluation import evaluate_classification
from src.ml.registry import compare_candidate, promote_candidate, rollback_model, set_initial_current


def _registry(tmp_path):
    path = tmp_path / "registry.json"
    context = {"method": "chronological", "test_data_hash": "synthetic-hash", "test_rows": 10}
    base = {"dataset": "synthetic", "name": "linear", "evaluation_context": context,
            "metrics": {"test": {"macro_f1": 0.60, "brier_score": 0.20}}, "lifecycle": "CURRENT"}
    candidate = {"dataset": "synthetic", "name": "linear", "evaluation_context": context,
                  "metrics": {"test": {"macro_f1": 0.66, "brier_score": 0.21}}, "lifecycle": "CANDIDATE"}
    path.write_text(json.dumps({"models": [{**base, "version": "synthetic-v1"},
        {**candidate, "version": "synthetic-v2"}],
        "current_model_versions": {"synthetic:linear": "synthetic-v1"}, "promotion_history": []}))
    return path


def test_candidate_acceptance_requires_same_evaluation_context_and_metrics(tmp_path):
    path = _registry(tmp_path)
    result = compare_candidate(path, "synthetic-v2", acceptance={"primary_metric": "macro_f1",
        "minimum_improvement": 0.02, "maximum_brier_increase": 0.02, "require_brier": True})
    assert result["status"] == "ACCEPTANCE_MET"
    data = json.loads(path.read_text())
    data["models"][1]["evaluation_context"]["test_data_hash"] = "different-synthetic-split"
    path.write_text(json.dumps(data))
    assert compare_candidate(path, "synthetic-v2", acceptance={"primary_metric": "macro_f1"})["status"] == "INCOMPARABLE_EVALUATION_CONTEXT"


def test_first_current_model_requires_explicit_human_selection(tmp_path):
    path = tmp_path / "initial.json"
    path.write_text(json.dumps({"models": [{"dataset": "synthetic", "name": "linear",
        "version": "synthetic-v1", "lifecycle": "CANDIDATE"}]}))
    with pytest.raises(ValueError, match="Reviewer"):
        set_initial_current(path, "synthetic-v1", reviewer="", reason="synthetic")
    selected = set_initial_current(path, "synthetic-v1", reviewer="synthetic-reviewer",
                                   reason="synthetic initial approval")
    assert selected["status"] == "CURRENT"
    with pytest.raises(ValueError, match="current model already exists"):
        set_initial_current(path, "synthetic-v1", reviewer="synthetic-reviewer", reason="synthetic")


def test_promotion_requires_criteria_and_reviewer_then_allows_rollback(tmp_path):
    path = _registry(tmp_path)
    criteria = {"primary_metric": "macro_f1", "minimum_improvement": 0.02,
                "maximum_brier_increase": 0.02, "require_brier": True}
    with pytest.raises(ValueError, match="Reviewer"):
        promote_candidate(path, "synthetic-v2", acceptance=criteria, reviewer="", reason="synthetic")
    result = promote_candidate(path, "synthetic-v2", acceptance=criteria,
                               reviewer="synthetic-reviewer", reason="synthetic approval")
    assert result["status"] == "PROMOTED"
    rollback = rollback_model(path, "synthetic:linear", reviewer="synthetic-reviewer", reason="synthetic rollback")
    assert rollback["to_version"] == "synthetic-v1"
    registry = json.loads(path.read_text())
    assert registry["current_model_versions"]["synthetic:linear"] == "synthetic-v1"
    assert [event["event"] for event in registry["promotion_history"]] == ["MODEL_PROMOTED", "MODEL_ROLLED_BACK"]


def test_model_promotion_rejects_candidate_that_misses_acceptance(tmp_path):
    path = _registry(tmp_path)
    with pytest.raises(ValueError, match="acceptance criteria"):
        promote_candidate(path, "synthetic-v2", acceptance={"primary_metric": "macro_f1",
            "minimum_improvement": 0.10}, reviewer="synthetic-reviewer", reason="synthetic approval")


def test_evaluation_saves_reproducible_report_per_model_version(tmp_path):
    frame = pd.DataFrame({"event_time": pd.date_range("2025-01-01", periods=60, freq="D"),
                          "signal": [i % 2 for i in range(60)],
                          "group": ["synthetic-a" if i % 2 else "synthetic-b" for i in range(60)],
                          "label": [i % 2 for i in range(60)]})
    config = {"train_fraction": 0.6, "validation_fraction": 0.2, "random_seed": 7,
              "tree_max_depth": 2, "random_forest_estimators": 3,
              "simple_rule_feature": "signal", "simple_rule_threshold": 0}
    result = evaluate_classification("synthetic", frame, label="label", timestamp="event_time",
        features=["signal"], subgroup="group", archive_hash="synthetic-input-hash",
        config=config, models_dir=tmp_path / "models", registry_path=tmp_path / "registry.json")
    assert result["models"]
    registry = json.loads((tmp_path / "registry.json").read_text())
    for item in registry["models"]:
        report = tmp_path / "models" / "evaluations" / f"{item['version']}.json"
        content = json.loads(report.read_text())
        assert content["data_hash"] == "synthetic-input-hash"
        assert content["evaluation_context"]["test_rows"] == 12
        assert content["config"] == config
        assert "macro_f1" in content["metrics"]["test"]
