"""Bridge from profile-selected source frames to existing source-local features."""
from pathlib import Path
import pandas as pd


def build_feature_groups(dataset: str, frames: list[tuple[str, pd.DataFrame]], settings):
    """Compute within-source features; no source frame is joined to another dataset."""
    named: dict[str, pd.DataFrame] = {}
    for member, frame in frames:
        table = Path(member.split(" [")[0]).stem.lower()
        named[table] = pd.concat([named[table], frame], ignore_index=True) if table in named else frame.copy()
    outputs = []
    if dataset == "olist":
        from src.data.features.olist import build_olist_delivery_features
        orders, items = named.get("olist_orders_dataset", pd.DataFrame()), named.get("olist_order_items_dataset", pd.DataFrame())
        if not orders.empty and not items.empty:
            features = build_olist_delivery_features(orders, items)
            outputs.append({"source": dataset, "frame": features, "record_ids": features["order_id"].astype(str),
                "monitored": [("delivery_deviation_days", settings.pipeline.feature_thresholds[
                    "olist_delivery_deviation_days"], "absolute")]})
    elif dataset == "dataco":
        from src.data.features.dataco import build_dataco_shipping_features
        if frames:
            raw = pd.concat([frame for _, frame in frames], ignore_index=True)
            features = build_dataco_shipping_features(raw)
            outputs.append({"source": dataset, "frame": features,
                "record_ids": raw.get("Order Item Id", raw.get("Order Id", pd.Series(raw.index))).astype(str),
                "monitored": [("scheduled_shipping_days", settings.pipeline.feature_thresholds[
                    "dataco_shipping_days"], "above"), ("observed_actual_shipping_days", settings.pipeline.feature_thresholds[
                    "dataco_shipping_days"], "above")]})
    elif dataset == "online_retail_ii":
        from src.data.features.online_retail_ii import build_product_week_demand
        for member, frame in frames:
            weekly = build_product_week_demand(frame)
            ids = weekly["StockCode"].astype(str) + "@" + weekly["week"].astype(str)
            outputs.append({"source": dataset, "frame": weekly, "record_ids": ids,
                "timestamp": weekly["week"], "sheet": member,
                "monitored": [("weekly_quantity", settings.pipeline.feature_thresholds[
                    "online_retail_weekly_quantity"], "above")]})
    else:
        raise ValueError(f"Unknown adapter feature profile: {dataset}")
    return outputs
