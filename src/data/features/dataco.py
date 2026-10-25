"""DataCo shipping features, separating pre-shipment fields from outcomes."""

import pandas as pd


def build_dataco_shipping_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return features and observed delivery outcome columns with explicit names."""
    out = pd.DataFrame(index=frame.index)
    source_for = {
        "scheduled_shipping_days": "Days for shipment (scheduled)",
        "shipping_mode": "Shipping Mode",
        "order_timestamp": "order date (DateOrders)",
        "order_region": "Order Region",
    }
    for target, source in source_for.items():
        if source in frame:
            out[target] = frame[source]
    if "order_timestamp" in out:
        out["order_timestamp"] = pd.to_datetime(out["order_timestamp"], errors="coerce", format="mixed", utc=True)
        out["order_weekday"] = out["order_timestamp"].dt.dayofweek
    # Actual shipping time and risk label are outcomes and never included as predictor features.
    if "Days for shipping (real)" in frame:
        out["observed_actual_shipping_days"] = pd.to_numeric(frame["Days for shipping (real)"], errors="coerce")
    if "Late_delivery_risk" in frame:
        out["observed_late_delivery_risk"] = frame["Late_delivery_risk"]
    return out
