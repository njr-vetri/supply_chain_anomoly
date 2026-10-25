"""
Aggregated, group-level supply-chain network engine.
Nodes represent groups (Supplier, Product, Carrier, Warehouse, Route/Lane, CustomerRegion).
Individual orders are aggregated into grouped nodes and weighted flows.
Computes peer-relative health, time-bucketed health series, intelligent capping,
missing roles reporting, and upstream/downstream exposure tracing.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

import networkx as nx


CANONICAL_GROUP_TYPES = (
    "Supplier",
    "Product",
    "Carrier",
    "Warehouse",
    "Route/Lane",
    "CustomerRegion",
)


def _format_time_bucket(dt: datetime | str | None, unit: str = "week") -> str:
    """Format timestamp into an ISO week (e.g. 2026-W01) or month (e.g. 2026-01)."""
    if dt is None:
        return "UNKNOWN_TIME"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return "UNKNOWN_TIME"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if unit == "month":
        return dt.strftime("%Y-%m")
    cal = dt.isocalendar()
    return f"{cal.year}-W{cal.week:02d}"


def build_aggregated_supply_network(
    records: Iterable[dict[str, Any]],
    *,
    source: str,
    company_id: str,
    anomalies: list[dict[str, Any]] | None = None,
    incidents: list[dict[str, Any]] | None = None,
    approved_relationships: list[dict[str, Any]] | None = None,
    max_nodes: int = 150,
    selected_incident_id: str | None = None,
    time_bucket_unit: str = "week",
) -> dict[str, Any]:
    """
    Builds an aggregated supply-chain group graph from canonical records.
    Never returns individual order nodes.
    Capping clusters the least exposed tail nodes into 'other' nodes when count > max_nodes.
    """
    anomalies = anomalies or []
    incidents = incidents or []
    approved_relationships = approved_relationships or []

    records_list = list(records)

    # Map anomalies & incidents to record references
    anomaly_record_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anom in anomalies:
        ref = anom.get("record_ref")
        if ref:
            anomaly_record_map[str(ref)].append(anom)

    incident_record_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incident_ref_set: set[str] = set()
    for inc in incidents:
        refs = inc.get("record_refs") or (inc.get("payload") or {}).get("record_refs") or []
        for r in refs:
            incident_record_map[str(r)].append(inc)
            if inc.get("id") == selected_incident_id:
                incident_ref_set.add(str(r))

    # Pre-index order attributes to enable order-shipment joins across tables
    order_join_data: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in records_list:
        oid = row.get("order_id")
        if oid:
            o_str = str(oid)
            for k in ("supplier_id", "vendor_id", "product_id", "sku", "item_id", "carrier", "carrier_id",
                      "warehouse_id", "warehouse", "route", "lane", "region", "destination", "customer_state", "country"):
                val = row.get(k)
                if val is not None and k not in order_join_data[o_str]:
                    order_join_data[o_str][k] = val

    # Track raw group frequencies and anomaly associations
    entity_data: dict[str, dict[str, Any]] = {}
    time_series_by_node: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"volume": 0, "anomalies": 0, "delays": 0}))
    all_time_buckets: set[str] = set()

    # Track flow aggregations: (source_node_id, target_node_id, edge_type, flag) -> {weight, refs}
    flow_aggregates: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {"weight": 0, "refs": []})

    seen_types: set[str] = set()

    for idx, row in enumerate(records_list):
        ref = str(row.get("source_record_ref") or row.get("event_id") or f"rec-{idx}")
        raw_ts = row.get("event_timestamp") or row.get("order_ts") or row.get("valid_from")
        bucket = _format_time_bucket(raw_ts, time_bucket_unit)
        all_time_buckets.add(bucket)

        anom_list = anomaly_record_map.get(ref, [])
        anom_count = len(anom_list)
        is_incident_rec = ref in incident_ref_set

        # Determine delay status for delay-capability health calculation
        is_delayed = bool(
            row.get("is_delayed")
            or (row.get("delay_days") is not None and float(row.get("delay_days", 0) or 0) > 0)
            or (row.get("late_days") is not None and float(row.get("late_days", 0) or 0) > 0)
            or (isinstance(row.get("delivery_status"), str) and row.get("delivery_status").lower() == "late")
            or (isinstance(row.get("status"), str) and row.get("status").lower() == "late")
        )

        row_source = str(row.get("source") or source)

        # Enrich row from joined order if available
        oid = row.get("order_id")
        joined_info = order_join_data.get(str(oid), {}) if oid else {}

        sup_id = row.get("supplier_id") or row.get("vendor_id") or joined_info.get("supplier_id") or joined_info.get("vendor_id")
        prod_id = row.get("product_id") or row.get("sku") or row.get("item_id") or joined_info.get("product_id") or joined_info.get("sku") or joined_info.get("item_id")
        carr_id = row.get("carrier") or row.get("carrier_id") or joined_info.get("carrier") or joined_info.get("carrier_id")
        wh_id = row.get("warehouse_id") or row.get("warehouse") or joined_info.get("warehouse_id") or joined_info.get("warehouse")
        route_id = row.get("route") or row.get("lane") or joined_info.get("route") or joined_info.get("lane")
        reg_id = row.get("region") or row.get("destination") or row.get("customer_state") or row.get("country") or joined_info.get("region") or joined_info.get("destination") or joined_info.get("customer_state")

        node_keys: list[tuple[str, str, str]] = []  # (kind, raw_id, node_id)

        if sup_id:
            s_id = f"supplier:{sup_id}"
            node_keys.append(("Supplier", str(sup_id), s_id))
            seen_types.add("Supplier")

        if prod_id:
            p_id = f"product:{prod_id}"
            node_keys.append(("Product", str(prod_id), p_id))
            seen_types.add("Product")

        if carr_id:
            c_id = f"carrier:{carr_id}"
            node_keys.append(("Carrier", str(carr_id), c_id))
            seen_types.add("Carrier")

        if wh_id:
            w_id = f"warehouse:{wh_id}"
            node_keys.append(("Warehouse", str(wh_id), w_id))
            seen_types.add("Warehouse")

        if route_id:
            rt_id = f"route:{route_id}"
            node_keys.append(("Route/Lane", str(route_id), rt_id))
            seen_types.add("Route/Lane")

        if reg_id and not route_id:
            r_id = f"region:{reg_id}"
            node_keys.append(("CustomerRegion", str(reg_id), r_id))
            seen_types.add("CustomerRegion")

        # Record group statistics
        for kind, raw_id, n_id in node_keys:
            if n_id not in entity_data:
                entity_data[n_id] = {
                    "id": n_id,
                    "type": kind,
                    "label": f"{kind}: {raw_id}",
                    "raw_id": raw_id,
                    "company_id": company_id,
                    "exposure": 0,
                    "anomaly_count": 0,
                    "late_count": 0,
                    "contributing_sources": set(),
                    "evidence_refs": set(),
                    "linked_incident_count": 0,
                    "is_incident_affected": False,
                }
            entity_data[n_id]["exposure"] += 1
            entity_data[n_id]["anomaly_count"] += anom_count
            if is_delayed:
                entity_data[n_id]["late_count"] += 1
            entity_data[n_id]["contributing_sources"].add(row_source)
            if is_incident_rec:
                entity_data[n_id]["is_incident_affected"] = True
            for a in anom_list:
                entity_data[n_id]["evidence_refs"].add(a.get("id") or ref)
            if ref in incident_record_map:
                entity_data[n_id]["linked_incident_count"] += len(incident_record_map[ref])

            # Time series
            time_series_by_node[n_id][bucket]["volume"] += 1
            time_series_by_node[n_id][bucket]["anomalies"] += anom_count
            if is_delayed:
                time_series_by_node[n_id][bucket]["delays"] += 1

        # Register group flows from mapped roles & relationships
        # 1. Supplier supplies Product (ESTABLISHED)
        if sup_id and prod_id:
            key = (f"supplier:{sup_id}", f"product:{prod_id}", "SUPPLIES", "ESTABLISHED")
            flow_aggregates[key]["weight"] += 1
            if len(flow_aggregates[key]["refs"]) < 5:
                flow_aggregates[key]["refs"].append(ref)

        # 2. Supplier uses Carrier via order-shipment join (INFERRED)
        if sup_id and carr_id:
            key = (f"supplier:{sup_id}", f"carrier:{carr_id}", "USES", "INFERRED")
            flow_aggregates[key]["weight"] += 1
            if len(flow_aggregates[key]["refs"]) < 5:
                flow_aggregates[key]["refs"].append(ref)

        # 3. Carrier serves Route or Region (ESTABLISHED)
        if carr_id and route_id:
            key = (f"carrier:{carr_id}", f"route:{route_id}", "SERVES", "ESTABLISHED")
            flow_aggregates[key]["weight"] += 1
            if len(flow_aggregates[key]["refs"]) < 5:
                flow_aggregates[key]["refs"].append(ref)
        elif carr_id and reg_id:
            key = (f"carrier:{carr_id}", f"region:{reg_id}", "SERVES", "ESTABLISHED")
            flow_aggregates[key]["weight"] += 1
            if len(flow_aggregates[key]["refs"]) < 5:
                flow_aggregates[key]["refs"].append(ref)

        # 4. Product stored at Warehouse (ESTABLISHED)
        if prod_id and wh_id:
            key = (f"product:{prod_id}", f"warehouse:{wh_id}", "STORED_AT", "ESTABLISHED")
            flow_aggregates[key]["weight"] += 1
            if len(flow_aggregates[key]["refs"]) < 5:
                flow_aggregates[key]["refs"].append(ref)

        # 5. Warehouse fulfills in Region or Route (ESTABLISHED)
        if wh_id and reg_id:
            key = (f"warehouse:{wh_id}", f"region:{reg_id}", "FULFILLS_IN", "ESTABLISHED")
            flow_aggregates[key]["weight"] += 1
            if len(flow_aggregates[key]["refs"]) < 5:
                flow_aggregates[key]["refs"].append(ref)

    # Missing roles reporting
    omitted_node_types: dict[str, str] = {}
    if "Carrier" not in seen_types:
        omitted_node_types["Carrier"] = "No carrier identifier present in dataset or schema mapping."
    if "Warehouse" not in seen_types:
        omitted_node_types["Warehouse"] = "No warehouse identifier present in dataset or schema mapping."
    if "CustomerRegion" not in seen_types and "Route/Lane" not in seen_types:
        omitted_node_types["CustomerRegion"] = "No customer region/destination present in dataset or schema mapping."
    if "Supplier" not in seen_types:
        omitted_node_types["Supplier"] = "No supplier identifier mapped in canonical profile."
    if "Product" not in seen_types:
        omitted_node_types["Product"] = "No product identifier mapped in canonical profile."

    # Compute Peer Baselines & Node Health
    has_delay_info = any(n["late_count"] > 0 for n in entity_data.values())

    type_nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in entity_data.values():
        type_nodes[n["type"]].append(n)

    for kind, nodes in type_nodes.items():
        if has_delay_info:
            rates = [n["late_count"] / max(1, n["exposure"]) for n in nodes if n["exposure"] >= 5]
            if not rates:
                rates = [n["late_count"] / max(1, n["exposure"]) for n in nodes]
        else:
            rates = [n["anomaly_count"] / max(1, n["exposure"]) for n in nodes if n["exposure"] >= 5]
            if not rates:
                rates = [n["anomaly_count"] / max(1, n["exposure"]) for n in nodes]

        mean_rate = sum(rates) / len(rates) if rates else 0.0
        variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates) if len(rates) > 1 else 0.0
        std_rate = math.sqrt(variance)

        for n in nodes:
            exp = n["exposure"]
            late_rate = n["late_count"] / max(1, exp)
            anom_rate = n["anomaly_count"] / max(1, exp)
            primary_rate = late_rate if has_delay_info else anom_rate

            diff = primary_rate - mean_rate
            z_score = (diff / std_rate) if std_rate > 0.001 else (0.0 if diff == 0 else (2.5 if diff > 0 else -1.0))

            min_support = 5
            has_support = exp >= min_support

            # Strict peer rule: Nodes at or below peer average are HEALTHY.
            # Never label a node UNHEALTHY with a negative or zero z-score.
            if diff <= 0 or z_score <= 0:
                health = "HEALTHY"
                health_status = "HEALTHY"
            elif not has_support:
                health = "HEALTHY"
                health_status = "HEALTHY"
            elif z_score >= 1.75 or (diff > 0.15 and z_score >= 1.5):
                health = "PROBLEM"
                health_status = "UNHEALTHY"
            elif z_score >= 0.75 or diff > 0.05:
                health = "WATCH"
                health_status = "UNHEALTHY"
            else:
                health = "HEALTHY"
                health_status = "HEALTHY"

            n["health"] = health
            n["health_status"] = health_status
            n["metrics_vs_peer_baseline"] = {
                "rate": round(primary_rate, 4),
                "late_rate": round(late_rate, 4),
                "anomaly_rate": round(anom_rate, 4),
                "peer_average_rate": round(mean_rate, 4),
                "difference_from_peer_average": round(diff, 4),
                "z_score": round(z_score, 2),
                "total_exposure": exp,
                "total_late": n["late_count"],
                "total_anomalies": n["anomaly_count"],
                "has_minimum_support": has_support,
            }

            # Build time-bucketed health series
            series = []
            for b_name in sorted(all_time_buckets):
                b_stat = time_series_by_node[n["id"]][b_name]
                b_vol = b_stat["volume"]
                b_anom = b_stat["anomalies"]
                b_delays = b_stat["delays"]
                b_rate = (b_delays if has_delay_info else b_anom) / max(1, b_vol)
                if b_vol == 0:
                    b_health = "UNKNOWN"
                elif (b_delays if has_delay_info else b_anom) == 0:
                    b_health = "HEALTHY"
                elif b_rate > mean_rate and (b_rate - mean_rate) > 0.1:
                    b_health = "PROBLEM"
                elif b_rate > mean_rate:
                    b_health = "WATCH"
                else:
                    b_health = "HEALTHY"
                series.append({
                    "bucket": b_name,
                    "health": b_health,
                    "volume": b_vol,
                    "anomalies": b_anom,
                    "delays": b_delays,
                })
            n["time_series"] = series

    # Intelligent Node Capping
    original_node_count = len(entity_data)
    capped = False
    clustered_count = 0

    if original_node_count > max_nodes:
        capped = True
        def priority_key(item: dict[str, Any]) -> tuple[int, int]:
            h_score = {"PROBLEM": 3, "WATCH": 2, "UNKNOWN": 1, "HEALTHY": 0}.get(item["health"], 0)
            return (h_score, item["exposure"])

        sorted_nodes = sorted(entity_data.values(), key=priority_key, reverse=True)
        slots = max_nodes - 6
        retained = set(n["id"] for n in sorted_nodes[:slots])
        clustered_into: dict[str, str] = {}

        for n in sorted_nodes[slots:]:
            clustered_count += 1
            other_id = f"{n['type'].lower()}:other"
            clustered_into[n["id"]] = other_id

            if other_id not in entity_data:
                entity_data[other_id] = {
                    "id": other_id,
                    "type": n["type"],
                    "label": f"Other {n['type']}s (Grouped)",
                    "company_id": company_id,
                    "exposure": 0,
                    "anomaly_count": 0,
                    "late_count": 0,
                    "health": "UNKNOWN",
                    "health_status": "HEALTHY",
                    "contributing_sources": set(),
                    "evidence_refs": set(),
                    "linked_incident_count": 0,
                    "is_incident_affected": False,
                    "metrics_vs_peer_baseline": {"clustered_node_count": 0},
                    "time_series": [],
                }
            entity_data[other_id]["exposure"] += n["exposure"]
            entity_data[other_id]["anomaly_count"] += n["anomaly_count"]
            entity_data[other_id]["late_count"] += n.get("late_count", 0)
            entity_data[other_id]["contributing_sources"].update(n.get("contributing_sources", set()))
            entity_data[other_id]["metrics_vs_peer_baseline"]["clustered_node_count"] += 1
            retained.add(other_id)

        entity_data = {k: v for k, v in entity_data.items() if k in retained}

    # Format nodes for return
    nodes_result = []
    for n in entity_data.values():
        sources_list = sorted(list(n.get("contributing_sources", set())))
        source_label = ", ".join(sources_list) if sources_list else source
        nodes_result.append({
            "id": n["id"],
            "type": n["type"],
            "label": n["label"],
            "source": source_label,
            "company_id": n["company_id"],
            "exposure": n["exposure"],
            "anomaly_count": n["anomaly_count"],
            "late_count": n.get("late_count", 0),
            "health": n["health"],
            "health_status": n["health_status"],
            "metrics_vs_peer_baseline": n.get("metrics_vs_peer_baseline", {}),
            "evidence_refs": sorted(list(n["evidence_refs"]))[:10],
            "linked_incident_count": n["linked_incident_count"],
            "is_incident_affected": n["is_incident_affected"],
            "time_series": n.get("time_series", []),
        })

    # Compile edges
    allowed_nodes = {n["id"] for n in nodes_result}
    edges_result = []

    # User-entered edges from approved proposals
    for relation in approved_relationships:
        left = relation.get("left_node_id")
        right = relation.get("right_node_id")
        if left in allowed_nodes and right in allowed_nodes:
            edges_result.append({
                "from": left,
                "to": right,
                "type": str(relation.get("relationship") or "USER_LINK"),
                "weight": int(relation.get("weight") or 1),
                "flag": "USER_ENTERED",
                "status": "ESTABLISHED",
                "meaning": str(relation.get("meaning") or "Reviewer approved relationship"),
                "source_refs": [str(relation.get("id") or "approval")],
            })

    # Flow aggregates
    for (src_id, tgt_id, edge_type, flag), flow_data in flow_aggregates.items():
        s_actual = src_id if src_id in allowed_nodes else f"{src_id.split(':')[0]}:other"
        t_actual = tgt_id if tgt_id in allowed_nodes else f"{tgt_id.split(':')[0]}:other"

        if s_actual in allowed_nodes and t_actual in allowed_nodes and s_actual != t_actual:
            edges_result.append({
                "from": s_actual,
                "to": t_actual,
                "type": edge_type,
                "weight": flow_data["weight"],
                "flag": flag,
                "status": flag,
                "meaning": f"{edge_type.replace('_', ' ').title()} relationship between entity groups",
                "source_refs": flow_data["refs"],
            })

    # Candidate problem focus ranking
    candidate_sources = []
    problem_nodes = [n for n in nodes_result if n["health"] == "PROBLEM"]
    for pn in sorted(problem_nodes, key=lambda x: (x["is_incident_affected"], x["exposure"]), reverse=True):
        candidate_sources.append({
            "node_id": pn["id"],
            "type": pn["type"],
            "label": pn["label"],
            "health": pn["health"],
            "exposure": pn["exposure"],
            "late_count": pn.get("late_count", 0),
            "anomaly_count": pn["anomaly_count"],
            "metrics_vs_peer_baseline": pn["metrics_vs_peer_baseline"],
            "confidence_label": "candidate, not confirmed",
        })

    return {
        "nodes": nodes_result,
        "edges": edges_result,
        "time_buckets": sorted(list(all_time_buckets)),
        "omitted_node_types": omitted_node_types,
        "capping": {
            "capped": capped,
            "max_nodes": max_nodes,
            "original_node_count": original_node_count,
            "clustered_into_other": clustered_count,
            "visible_node_count": len(nodes_result),
        },
        "candidate_sources": candidate_sources,
        "limitations": [
            "Network represents aggregated entity groups, not individual orders.",
            "Health states are computed relative to observed peer baselines.",
            "Established reachability describes exposure, not confirmed physical causation.",
        ],
    }


def trace_aggregated_network(
    graph_data: dict[str, Any],
    node_id: str,
    direction: str = "downstream",
    max_nodes: int = 500,
) -> dict[str, Any]:
    """
    Traces paths along ESTABLISHED and INFERRED edges in the aggregated supply network.
    Returns reached nodes, connecting paths, and explicit exposure labeling.
    """
    g = nx.DiGraph()
    for n in graph_data.get("nodes", []):
        g.add_node(n["id"], **n)

    for e in graph_data.get("edges", []):
        if e.get("flag") in ("ESTABLISHED", "INFERRED", "USER_ENTERED"):
            g.add_edge(e["from"], e["to"], **e)

    target_node = node_id
    if target_node not in g:
        # Match by raw ID suffix if prefixed with source
        raw_target = target_node.split(":")[-1]
        for existing in g.nodes:
            if existing == target_node or existing.split(":")[-1] == raw_target:
                target_node = existing
                break

    if target_node not in g:
        return {
            "root_node_id": node_id,
            "direction": direction,
            "nodes": [],
            "edges": [],
            "count": 0,
            "label": "exposure/hypothesis, not confirmed cause",
            "message": "Node not found in established network.",
        }

    search_graph = g if direction == "downstream" else g.reverse(copy=True)
    descendants = list(nx.descendants(search_graph, target_node))[:max_nodes]
    selected = {target_node, *descendants}

    traced_nodes = [g.nodes[item] for item in selected]
    traced_edges = [
        {"from": u, "to": v, **d}
        for u, v, d in g.edges(data=True)
        if u in selected and v in selected
    ]

    return {
        "root_node_id": target_node,
        "direction": direction,
        "nodes": traced_nodes,
        "edges": traced_edges,
        "count": len(traced_nodes),
        "truncated": len(nx.descendants(search_graph, target_node)) > max_nodes,
        "label": "exposure/hypothesis, not confirmed cause",
        "limitations": [
            "Path traversal follows recorded canonical established and inferred links.",
            "Reachability indicates potential exposure, never confirmed causation.",
        ],
    }
