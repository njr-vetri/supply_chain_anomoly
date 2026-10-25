"""Olist delivery features; actual outcomes are explicitly post-delivery only."""

import pandas as pd


def build_olist_delivery_features(orders: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    """Build one row/order; seller history uses only earlier order purchase dates."""
    required = {"order_id", "order_purchase_timestamp", "order_estimated_delivery_date",
                "order_delivered_customer_date"}
    if missing := required - set(orders.columns):
        raise ValueError(f"Missing Olist order columns: {sorted(missing)}")
    out = orders.copy()
    for column in ("order_purchase_timestamp", "order_estimated_delivery_date", "order_delivered_customer_date"):
        out[column] = pd.to_datetime(out[column], errors="coerce", format="mixed", utc=True)
    out["estimated_transit_days"] = (out["order_estimated_delivery_date"] - out["order_purchase_timestamp"]).dt.total_seconds() / 86400
    out["actual_delivery_days"] = (out["order_delivered_customer_date"] - out["order_purchase_timestamp"]).dt.total_seconds() / 86400
    out["delivery_deviation_days"] = out["actual_delivery_days"] - out["estimated_transit_days"]
    # Aggregate prior deliveries only; the current and future outcomes are excluded.
    if "seller_id" in items.columns:
        seller_orders = items[["order_id", "seller_id"]].drop_duplicates().merge(
            out[["order_id", "order_purchase_timestamp", "actual_delivery_days"]], on="order_id", how="inner")
        seller_orders = seller_orders.sort_values(["seller_id", "order_purchase_timestamp", "order_id"])
        grouped = seller_orders.groupby("seller_id")["actual_delivery_days"]
        seller_orders["prior_seller_delivery_days_mean"] = grouped.transform(lambda values: values.shift().expanding().mean())
        seller_orders["prior_seller_order_count"] = seller_orders.groupby("seller_id").cumcount()
        history = seller_orders.groupby("order_id", as_index=False).agg(
            prior_seller_delivery_days_mean=("prior_seller_delivery_days_mean", "mean"),
            prior_seller_order_count=("prior_seller_order_count", "sum"),
        )
        out = out.merge(history, on="order_id", how="left")
    return out
