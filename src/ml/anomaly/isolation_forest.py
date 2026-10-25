"""Optional scikit-learn Isolation Forest adapter."""
import pandas as pd


def detect(values: pd.Series, contamination: float = 0.01, estimators: int = 100, random_seed: int = 0) -> pd.DataFrame:
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError as exc:
        raise RuntimeError("Isolation Forest requires scikit-learn from requirements.txt") from exc
    from src.ml.anomaly.common import results

    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.dropna()
    flags = pd.Series(False, index=numeric.index)
    scores = pd.Series(float("nan"), index=numeric.index)
    baseline = pd.Series(numeric.median(), index=numeric.index)
    if len(valid) >= 2:
        model = IsolationForest(contamination=contamination, n_estimators=estimators, random_state=random_seed)
        model.fit(valid.to_frame())
        flags.loc[valid.index] = model.predict(valid.to_frame()) == -1
        scores.loc[valid.index] = -model.score_samples(valid.to_frame())
    return results(numeric, flags, scores, baseline, "isolation_forest")
