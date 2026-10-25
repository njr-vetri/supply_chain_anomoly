"""Project capability assessment from approved canonical mappings only."""
from __future__ import annotations

from typing import Any

FEATURES = ("anomaly_detection", "delay_prediction", "demand_analysis",
            "inventory_risk", "dependency_graph", "model_evaluation")

UNLOCKS = {
    "anomaly_detection": ["Mapped numeric measures and dated event records improve coverage."],
    "delay_prediction": ["Mapped roles: order_id, event_timestamp, promised_timestamp, delivered_timestamp."],
    "demand_analysis": ["Mapped roles: product_id, quantity, event_timestamp."],
    "inventory_risk": ["Inventory snapshots with product_id, warehouse_id, on-hand quantity, and observation time."],
    "dependency_graph": ["Approved order, supplier, product, shipment, carrier, and warehouse relationship keys."],
    "model_evaluation": ["Mapped delay prediction roles (order_id, event_timestamp, promised_timestamp, delivered_timestamp)."],
}


def assess_capabilities(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess a project's approved mapped roles without examining source values."""
    roles: set[str] = set()
    accepted_count = 0
    for source in sources:
        mapping = source.get("mapping") or {}
        if source.get("status") == "ACCEPTED":
            accepted_count += 1
            role_aliases = {"order_ts": "event_timestamp", "promised_ts": "promised_timestamp",
                            "delivered_ts": "delivered_timestamp"}
            roles.update(role_aliases.get(role, role) for role in mapping.get("mappings", {}).values())
    has_sales = {"product_id", "quantity", "event_timestamp"}.issubset(roles)
    has_delay = {"order_id", "event_timestamp", "promised_timestamp", "delivered_timestamp"}.issubset(roles)
    has_inventory = "inventory_snapshots" in {s.get("canonical_entity") for s in sources} or (
        {"product_id", "warehouse_id", "quantity", "event_timestamp"}.issubset(roles)
        and any("inventory" in str(s.get("name", "")).lower() for s in sources))
    has_graph = bool(roles & {"order_id", "supplier_id", "product_id", "shipment_id", "carrier", "warehouse_id"}) and accepted_count > 0
    definitions = {
        "anomaly_detection": ("AVAILABLE_WITH_LIMITATIONS" if roles & {"quantity", "price"} else
                              "AWAITING_CONFIGURATION" if accepted_count else "AWAITING_CONFIGURATION", []),
        "delay_prediction": ("AVAILABLE_WITH_LIMITATIONS" if has_delay else "AWAITING_CONFIGURATION",
                             [] if has_delay else
                             [r for r in ("order_id", "event_timestamp", "promised_timestamp", "delivered_timestamp") if r not in roles]),
        "demand_analysis": ("AVAILABLE" if has_sales else
                            "AWAITING_CONFIGURATION" if accepted_count else "AWAITING_CONFIGURATION",
                            [] if has_sales else [r for r in ("product_id", "quantity", "event_timestamp") if r not in roles]),
        "inventory_risk": ("AVAILABLE_WITH_LIMITATIONS" if has_inventory else "UNSUPPORTED",
                            [] if has_inventory else ["inventory_snapshot", "on_hand_quantity", "warehouse_id"]),
        "dependency_graph": ("AVAILABLE" if has_graph else "AWAITING_CONFIGURATION",
                             [] if has_graph else ["approved relationship keys between canonical entities"]),
        "model_evaluation": ("AVAILABLE_WITH_LIMITATIONS" if has_delay else
                             "AWAITING_CONFIGURATION", [] if has_delay else
                             [r for r in ("order_id", "event_timestamp", "promised_timestamp", "delivered_timestamp") if r not in roles]),
    }
    result = {}
    for feature in FEATURES:
        status, missing = definitions[feature]
        result[feature] = {"status": status, "missing_roles": missing,
                           "extra_data_to_unlock": UNLOCKS[feature],
                           "limitations": (["Mapped roles indicate potential capability; they do not establish model quality."]
                                           if status == "AVAILABLE_WITH_LIMITATIONS" else
                                           ["Canonical end-to-end implementation is not present."]
                                           if status == "NOT_IMPLEMENTED" else [])}
    return {"features": result, "approved_mapping_count": accepted_count,
            "canonical_roles": sorted(roles)}

