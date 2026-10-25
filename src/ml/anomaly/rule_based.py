"""Configurable domain-rule detector."""
import pandas as pd
from src.ml.anomaly.common import results


def detect(values: pd.Series, threshold: float, *, direction: str = "above") -> pd.DataFrame:
    numeric = pd.to_numeric(values, errors="coerce")
    if direction not in {"above", "below", "absolute"}:
        raise ValueError("direction must be above, below, or absolute")
    flags = numeric.gt(threshold) if direction == "above" else numeric.lt(threshold) if direction == "below" else numeric.abs().gt(threshold)
    return results(numeric, flags, (numeric - threshold).abs(), pd.Series(threshold, index=numeric.index), "rule")
