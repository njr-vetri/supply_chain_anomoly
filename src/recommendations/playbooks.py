"""Evidence-bound recommendation playbooks selected from detected driver types."""
from __future__ import annotations

from typing import Any

from src.core.config import load_settings


PLAYBOOKS: dict[str, dict[str, Any]] = {
    "supplier": {
        "action": "Supplier performance audit & secondary sourcing allocation",
        "required_roles": ["supplier_id", "order_id"],
        "rationale": "Supplier demonstrates statistically significant late delivery change-point elevation.",
        "assumptions": ["Supplier and purchase order line items are verified."],
        "uncertainty": ["Supplier delay association does not prove supplier default; upstream supply constraints may exist."],
        "tradeoffs": ["Secondary allocation may alter unit cost or tier discount structures."],
        "preconditions": ["Review supplier delivery history and active open orders before volume diversion."],
    },
    "carrier": {
        "action": "Carrier SLA audit & transit capacity re-allocation",
        "required_roles": ["carrier_id", "shipment_id"],
        "rationale": "Carrier demonstrates elevated late rate relative to peer carriers on assigned routes.",
        "assumptions": ["Carrier tracking timestamps and handover handshakes are valid."],
        "uncertainty": ["Carrier delay may be attributable to origin dispatch delays or regional customs."],
        "tradeoffs": ["Switching to expedited freight increases logistics expense."],
        "preconditions": ["Confirm carrier tracking IDs and transit corridors."],
    },
    "route": {
        "action": "Transit corridor re-routing & regional hub optimization",
        "required_roles": ["route"],
        "rationale": "Transit lane demonstrates multi-carrier transit delay bottlenecks.",
        "assumptions": ["Route origin and destination mappings are accurate."],
        "uncertainty": ["Corridor congestion may be temporary due to seasonal weather or infrastructure."],
        "tradeoffs": ["Alternative routes may introduce additional transit mileage."],
        "preconditions": ["Check alternative corridor transit capacity and toll profiles."],
    },
    "product": {
        "action": "SKU safety stock buffer calibration & production lead-time review",
        "required_roles": ["product_id"],
        "rationale": "Product SKU fulfillment and lead-time patterns show significant localized deviation.",
        "assumptions": ["Product SKU mapping is verified across order lines."],
        "uncertainty": ["Product lead-time variance may stem from component shortages rather than assembly."],
        "tradeoffs": ["Increasing safety stock buffers increases inventory holding costs."],
        "preconditions": ["Verify current inventory levels and open backorders for the SKU."],
    },
    "demand": {
        "action": "Dynamic reorder point adjustment & customer demand re-baselining",
        "required_roles": ["product_id"],
        "rationale": "Weekly aggregated demand spiked significantly above historical baseline.",
        "assumptions": ["Demand spike reflects genuine customer order volume."],
        "uncertainty": ["Sudden demand spikes may be transient bulk orders or promotional anomalies."],
        "tradeoffs": ["Raising reorder points ties up working capital."],
        "preconditions": ["Review customer order commitments and order backlog."],
    },
    "region": {
        "action": "Regional distribution center re-balancing",
        "required_roles": ["region"],
        "rationale": "A mapped region differs in observed affected-record rate.",
        "assumptions": ["Region is present in the source data."],
        "uncertainty": ["Regional differences may reflect unmeasured mix changes."],
        "tradeoffs": ["Additional review may be required across local operating teams."],
        "preconditions": ["Confirm region definition and reporting period."],
    },
    "mode": {
        "action": "review transport-mode pattern",
        "required_roles": ["mode"],
        "rationale": "A transport mode is associated with the detected pattern.",
        "assumptions": ["Mode labels are consistently mapped."],
        "uncertainty": ["No carrier capacity or service-level assumption is made."],
        "tradeoffs": ["Changing the mode could introduce cost or service effects that are unknown."],
        "preconditions": ["Verify mode and shipment records before considering a change."],
    },
    "week": {
        "action": "increase monitoring for the observed period",
        "required_roles": ["event_timestamp"],
        "rationale": "The time grouping shows a descriptive change or concentration.",
        "assumptions": ["Timestamps use the configured source timezone."],
        "uncertainty": ["A change point does not identify its cause."],
        "tradeoffs": ["Increased monitoring can create review workload."],
        "preconditions": ["Check source freshness and the comparison window."],
    },
}

ROLE_ALIASES = {
    "carrier_id": {"carrier", "carrier_id"},
    "shipment_id": {"shipment_id", "order_id"},
    "supplier_id": {"supplier_id", "vendor_id"},
    "product_id": {"product_id", "sku", "item_id"},
    "route": {"route", "lane"},
    "region": {"region", "destination", "customer_state"},
}


def recommend_for_driver(*, driver: dict[str, Any], available_roles: set[str],
                         evidence_refs: list[str], history: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a transparent playbook record; estimates are emitted only from supplied history or calibrated driver rates."""
    dimension = str(driver.get("dimension") or driver.get("factor") or "").lower()
    # Normalize dimension
    if "supplier" in dimension:
        dimension = "supplier"
    elif "carrier" in dimension:
        dimension = "carrier"
    elif "route" in dimension or "lane" in dimension:
        dimension = "route"
    elif "product" in dimension or "sku" in dimension:
        dimension = "product"
    elif "demand" in dimension:
        dimension = "demand"
    elif "region" in dimension:
        dimension = "region"

    playbook = PLAYBOOKS.get(dimension)
    if playbook is None:
        return {"status": "NOT_AVAILABLE", "reason": f"No playbook is configured for driver type: {dimension}"}

    # Role resolution with aliases
    expanded_roles = set(available_roles)
    for target_role, aliases in ROLE_ALIASES.items():
        if aliases & available_roles:
            expanded_roles.add(target_role)

    missing = sorted(set(playbook["required_roles"]) - expanded_roles)
    if missing:
        return {"status": "NEEDS_DATA", "missing_roles": missing,
                "reason": "Required mapped fields are unavailable; no action recommendation was generated."}
    if not evidence_refs:
        return {"status": "Insufficient evidence", "reason": "At least one source record reference is required."}

    settings = load_settings().recommendations
    start_date = driver.get("estimated_start_date") or driver.get("start_date")
    pre_rate = driver.get("pre_change_rate")
    post_rate = driver.get("post_change_rate")

    clean_refs = list(dict.fromkeys(evidence_refs))
    item: dict[str, Any] = {
        "type": "RECOMMENDATION",
        "driver_type": dimension,
        "driver_value": driver.get("value"),
        "action": playbook["action"],
        "rationale": playbook["rationale"],
        "evidence_refs": clean_refs,
        "evidence_ids": clean_refs,
        "start_date": start_date,
        "pre_change_rate": pre_rate,
        "post_change_rate": post_rate,
        "assumptions": list(playbook["assumptions"]),
        "uncertainty": list(playbook["uncertainty"]),
        "tradeoffs": list(playbook["tradeoffs"]),
        "preconditions": list(playbook["preconditions"]),
        "approvals": {"required": True, "role": "reviewer"},
        "status": "PROPOSED",
        "result": None,
        "dry_run": True,
        "constraints": ["No external or high-impact action is executed by recommendation generation."],
    }

    history = history or {}
    min_rows = int(settings.get("minimum_history_rows_for_effect_estimate", 30))
    effect = history.get("observed_effect")
    support = history.get("row_count")

    if isinstance(effect, (int, float)) and isinstance(support, int) and support >= min_rows:
        item["estimated_effect"] = {
            "value": effect,
            "label": "HYPOTHETICAL",
            "source": "supplied historical comparison",
            "support_rows": support,
            "assumptions": ["Historical comparison is representative of the future scenario."],
        }
    elif pre_rate is not None and post_rate is not None:
        diff_val = round(abs(float(post_rate) - float(pre_rate)), 4)
        item["estimated_effect"] = {
            "value": round(diff_val * 0.7, 4),
            "label": "HYPOTHETICAL",
            "source": "projected delay reduction from mitigating identified driver",
            "support_rows": driver.get("sample_size") or driver.get("post_support", 0),
            "assumptions": ["Intervention restores performance toward observed pre-change baseline."],
        }
    else:
        item["estimated_effect"] = None
        item["estimated_effect_status"] = "NOT_ESTIMATED: insufficient qualifying history"

    return item
