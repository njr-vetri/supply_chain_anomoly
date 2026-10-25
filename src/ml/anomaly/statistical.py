"""Robust median/MAD z-score and IQR outlier detectors."""
import pandas as pd
from src.ml.anomaly.common import results


def robust_zscore(values: pd.Series, threshold: float = 3.5) -> pd.DataFrame:
    numeric = pd.to_numeric(values, errors="coerce")
    median = numeric.median()
    mad = (numeric - median).abs().median()
    score = (numeric - median) / (1.4826 * mad) if pd.notna(mad) and mad > 0 else pd.Series(0.0, index=numeric.index)
    return results(numeric, score.abs().gt(threshold), score.abs(), pd.Series(median, index=numeric.index), "robust_zscore")


def iqr(values: pd.Series, multiplier: float = 1.5) -> pd.DataFrame:
    numeric = pd.to_numeric(values, errors="coerce")
    q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
    spread = q3 - q1
    lower, upper = q1 - multiplier * spread, q3 + multiplier * spread
    score = pd.concat([(lower - numeric).clip(lower=0), (numeric - upper).clip(lower=0)], axis=1).max(axis=1)
    return results(numeric, score.gt(0), score, pd.Series((q1 + q3) / 2, index=numeric.index), "iqr")
