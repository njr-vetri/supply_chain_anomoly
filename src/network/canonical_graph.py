"""Canonical, provenance-bearing supply-chain graph and descriptive analytics."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import networkx as nx

NODE_FIELDS = {
    "Supplier": ("supplier_id", "supplier", "vendor_code", "vendor_id"),
    "Product": ("product_id", "product", "product_group", "sku"),
    "Order": ("order_id", "po_number", "order_number"),
    "Shipment": ("shipment_id", "shipment_ref", "tracking_number"),
    "Warehouse": ("warehouse_id", "warehouse", "warehouse_code"),
    "Carrier": ("carrier_id", "carrier", "carrier_name"),
    "Region": ("region", "country", "route", "destination", "customer_state"),
    "Incident": ("incident_id",),
}


def build_canonical_graph(records: Iterable[dict[str, Any]], *, source: str,
                          mapping_version: str, source_hash: str,
                          approved_relationships: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Build edges only from canonical co-occurrence or explicitly approved links."""
    graph = nx.MultiDiGraph()
    omitted = {kind: "no mapped identifiers were present" for kind in NODE_FIELDS}

    def add_node(kind: str, value: Any, row: dict[str, Any], ref: str) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        # Namespace by source so equal IDs from separate data sources never imply a link.
        node_id = f"{kind.lower()}:{source}:{value}"
        graph.add_node(node_id, type=kind, identifier=str(value), company_id=row.get("company_id"),
                       source=source, source_record_ref=ref,
                       valid_from=_timestamp(row.get("event_timestamp")), valid_to=None)
        return node_id

    def add_edge(left: str, right: str, meaning: str, ref: str, flag: str,
                 edge_source: str = source, provenance: str | None = None,
                 valid_from: str | None = None, valid_to: str | None = None) -> None:
        graph.add_edge(left, right, meaning=meaning, source=edge_source,
                       source_record_ref=ref,
                       provenance=provenance or f"mapping_version={mapping_version};source_sha256={source_hash}",
                       validity_period={"from": valid_from, "to": valid_to}, flag=flag)

    for index, row in enumerate(records):
        ref = str(row.get("source_record_ref") or row.get("event_id") or f"record-{index}")
        nodes = {kind: add_node(kind, next((row.get(field) for field in fields if row.get(field) is not None), None), row, ref)
                 for kind, fields in NODE_FIELDS.items() if kind != "Incident"}
        supplier, product, order = nodes.get("Supplier"), nodes.get("Product"), nodes.get("Order")
        shipment, warehouse, carrier = nodes.get("Shipment"), nodes.get("Warehouse"), nodes.get("Carrier")
        if supplier and product:
            add_edge(supplier, product, "supplier supplies product in this canonical record", ref, "ESTABLISHED")
        if supplier and order:
            add_edge(supplier, order, "supplier is associated with order in this canonical record", ref, "ESTABLISHED")
        if order and product:
            add_edge(order, product, "order contains product in this canonical record", ref, "ESTABLISHED")
        if shipment and order:
            add_edge(shipment, order, "shipment is associated with order in this canonical record", ref, "ESTABLISHED")
        if carrier and shipment:
            add_edge(carrier, shipment, "carrier is associated with shipment in this canonical record", ref, "ESTABLISHED")
        if warehouse and product:
            add_edge(warehouse, product, "warehouse is associated with product in this canonical record", ref, "ESTABLISHED")
    for relation in approved_relationships:
        left, right = relation.get("left_node_id"), relation.get("right_node_id")
        if left not in graph or right not in graph:
            continue
        add_edge(left, right, str(relation.get("meaning") or "approved user-entered relationship"),
                 str(relation.get("source_record_ref") or relation.get("id") or "approved-relationship"),
                 "USER_ENTERED", str(relation.get("source") or "user"),
                 str(relation.get("provenance") or relation.get("approval_id") or "approval"),
                 relation.get("valid_from"), relation.get("valid_to"))
    present = {data["type"] for _, data in graph.nodes(data=True)}
    omitted = {kind: reason for kind, reason in omitted.items() if kind not in present}
    nodes = [{"id": node_id, **data} for node_id, data in graph.nodes(data=True)]
    edges = [{"from": left, "to": right, **data} for left, right, _key, data in graph.edges(keys=True, data=True)]
    return {"graph": graph, "nodes": nodes, "edges": edges, "omitted_node_types": omitted,
            "limitations": ["Graph links are derived from confirmed mappings or approved relationships.",
                            "Edges describe recorded relationships, not causation."]}


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def downstream_trace(graph: nx.MultiDiGraph, node_id: str, *, max_nodes: int = 500) -> dict[str, Any]:
    """Trace exposure along established edges only."""
    if node_id not in graph:
        return {"label": "exposure", "nodes": [], "edges": [], "limitations": ["Node not found."]}
    allowed = nx.DiGraph()
    allowed.add_nodes_from(graph.nodes(data=True))
    for left, right, data in graph.edges(data=True):
        if data.get("flag") == "ESTABLISHED":
            allowed.add_edge(left, right, **data)
    reached = list(nx.descendants(allowed, node_id))[:max_nodes]
    selected = {node_id, *reached}
    edges = [{"from": left, "to": right, **data} for left, right, data in allowed.edges(data=True)
             if left in selected and right in selected]
    return {"label": "exposure", "nodes": [{"id": item, **graph.nodes[item]} for item in selected],
            "edges": edges, "truncated": len(nx.descendants(allowed, node_id)) > max_nodes,
            "limitations": ["Established-edge reachability is exposure, not confirmed causation."]}


def upstream_trace(graph: nx.MultiDiGraph, node_id: str, *, max_nodes: int = 500) -> dict[str, Any]:
    """Trace upstream along established edges only."""
    reverse = graph.reverse(copy=True)
    return downstream_trace(reverse, node_id, max_nodes=max_nodes) | {"label": "hypothesis", "direction": "upstream"}


def graph_analytics(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Return exposure summaries without causal claims."""
    suppliers = [node for node, data in graph.nodes(data=True) if data.get("type") == "Supplier"]
    supplier_orders = {supplier: {n for n in downstream_trace(graph, supplier, max_nodes=len(graph))["nodes"]
                                  if n.startswith("order:")} for supplier in suppliers}
    order_total = sum(len(items) for items in supplier_orders.values())
    shares = [len(items) / order_total for items in supplier_orders.values() if order_total]
    concentration = sum(value * value for value in shares) if shares else None
    product_suppliers: dict[str, set[str]] = {}
    for supplier, product, data in graph.edges(data=True):
        if data.get("flag") == "ESTABLISHED" and graph.nodes[supplier].get("type") == "Supplier" and graph.nodes[product].get("type") == "Product":
            product_suppliers.setdefault(product, set()).add(supplier)
    faulty_health = {supplier: {"downstream_order_exposure": len(orders), "label": "exposure"}
                     for supplier, orders in supplier_orders.items()}
    observed = {supplier: int(graph.nodes[supplier].get("incident_count", 0)) for supplier in suppliers}
    peer_average = sum(observed.values()) / len(observed) if observed else None
    health = {supplier: {"incident_count": count, "peer_average": peer_average,
                         "difference_from_peer_average": count - peer_average if peer_average is not None else None,
                         "label": "hypothesis", "meaning": "stored incidents associated with supplier-linked records"}
              for supplier, count in observed.items()}
    return {"node_health_vs_peers": health if observed and any(observed.values()) else {
                "status": "NOT_COMPUTED", "reason": "No incident labels are linked to graph source records."},
            "concentration_risk": {"hhi": concentration, "supplier_count": len(suppliers), "label": "exposure"},
            "single_source_dependencies": [{"product_id": product, "supplier_id": next(iter(owners)), "label": "hypothesis"}
                                           for product, owners in product_suppliers.items() if len(owners) == 1],
            "downstream_impact": faulty_health,
            "limitations": ["No health comparison is computed without observed anomaly/incident labels.",
                            "Concentration and dependency summaries are exposure indicators, not causal findings."]}
