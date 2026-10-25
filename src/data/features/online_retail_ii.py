"""Product-week transaction demand and strictly backward-looking lags."""

import pandas as pd


def build_product_week_demand(frame: pd.DataFrame, lags: tuple[int, ...] = (1, 2, 4)) -> pd.DataFrame:
    """Aggregate quantities by product/week then attach only prior-week demand lags."""
    required = {"StockCode", "InvoiceDate", "Quantity"}
    if missing := required - set(frame.columns):
        raise ValueError(f"Missing retail columns: {sorted(missing)}")
    work = frame[["StockCode", "InvoiceDate", "Quantity"]].copy()
    work["InvoiceDate"] = pd.to_datetime(work["InvoiceDate"], errors="coerce", format="mixed", utc=True)
    work["Quantity"] = pd.to_numeric(work["Quantity"], errors="coerce")
    work = work.dropna(subset=["StockCode", "InvoiceDate", "Quantity"])
    work["week"] = work["InvoiceDate"].dt.tz_convert(None).dt.to_period("W").dt.start_time
    weekly = work.groupby(["StockCode", "week"], as_index=False)["Quantity"].sum().rename(columns={"Quantity": "weekly_quantity"})
    weekly = weekly.sort_values(["StockCode", "week"]).reset_index(drop=True)
    for lag in lags:
        if lag < 1:
            raise ValueError("Lag periods must be positive")
        weekly[f"quantity_lag_{lag}w"] = weekly.groupby("StockCode")["weekly_quantity"].shift(lag)
    return weekly
