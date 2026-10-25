"""Shared output shape for detectors."""
import pandas as pd


def results(values: pd.Series, flags: pd.Series, scores: pd.Series, baseline: pd.Series, method: str) -> pd.DataFrame:
    return pd.DataFrame({"anomaly": flags.fillna(False).astype(bool), "anomaly_score": scores,
                         "baseline": baseline, "observed_value": values, "detector": method}, index=values.index)
