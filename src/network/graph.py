"""Dataset-local relationship graphs with explicit provenance and inference flags."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd


ESTABLISHED = "ESTABLISHED"
INFERRED = "INFERRED"
EDGE_MEANINGS = {
    "SUPPLIES": "Seller offers/supplies the product shown on an order item.",
    "SHIPS": "Seller is associated with shipping the order item/order.",
    "AFFECTS": "Order contains or affects the product on an order item.",
    "SUPPORTS": "Evidence record supports a hypothesis or incident interpretation.",
    "CONTRADICTS": "Evidence record contradicts a hypothesis or incident interpretation.",
    "PROPOSED_CAUSE_OF": "Unconfirmed hypothesis proposes a cause relationship.",
    "MITIGATED_BY": "Recommendation is intended to mitigate the linked incident/hypothesis.",
}


def _node(dataset: str, entity: str, identifier: Any) -> str:
    """Prefix every node by dataset to prevent accidental cross-source joins."""
    return f"{dataset}:{entity}:{identifier}"


def _add_edge(graph: nx.MultiDiGraph, source: str, target: str, edge_type: str,
              source_reference: str, flag: str, meaning: str | None = None) -> None:
    if edge_type not in EDGE_MEANINGS:
        raise ValueError(f"Unsupported edge type: {edge_type}")
    if flag not in {ESTABLISHED, INFERRED}:
        raise ValueError("Edge flag must be ESTABLISHED or INFERRED")
    graph.add_edge(source, target, key=f"{edge_type}:{source_reference}", edge_type=edge_type,
                   meaning=meaning or EDGE_MEANINGS[edge_type], source_reference=source_reference, flag=flag)


def build_olist_graph(items: pd.DataFrame) -> nx.MultiDiGraph:
    """Create Olist seller-order-product edges from observed order item rows only."""
    required = {"order_id", "seller_id", "product_id"}
    if missing := required - set(items.columns):
        raise ValueError(f"Missing Olist relationship columns: {sorted(missing)}")
    graph = nx.MultiDiGraph(dataset="olist")
    for row in items.itertuples(index=False):
        order = getattr(row, "order_id")
        seller = getattr(row, "seller_id")
        product = getattr(row, "product_id")
        item_id = getattr(row, "order_item_id", None)
        reference = f"olist_order_items_dataset.csv:order_id={order}:order_item_id={item_id}"
        order_node = _node("olist", "order", order)
        seller_node = _node("olist", "seller", seller)
        product_node = _node("olist", "product", product)
        graph.add_node(order_node, dataset="olist", entity="order")
        graph.add_node(seller_node, dataset="olist", entity="seller")
        graph.add_node(product_node, dataset="olist", entity="product")
        _add_edge(graph, seller_node, product_node, "SUPPLIES", reference, ESTABLISHED)
        _add_edge(graph, seller_node, order_node, "SHIPS", reference, ESTABLISHED)
        _add_edge(graph, order_node, product_node, "AFFECTS", reference, ESTABLISHED)
    return graph


def add_evidence_edge(graph: nx.MultiDiGraph, *, dataset: str, evidence_ref: str,
                      target_ref: str, classification: str) -> None:
    if graph.graph.get("dataset") != dataset:
        raise ValueError("Evidence edge dataset must match graph dataset")
    edge_type = {"supporting": "SUPPORTS", "contradicting": "CONTRADICTS"}.get(classification)
    if edge_type is None:
        raise ValueError("classification must be supporting or contradicting")
    _add_edge(graph, _node(dataset, "evidence", evidence_ref), _node(dataset, "hypothesis", target_ref),
              edge_type, evidence_ref, ESTABLISHED, EDGE_MEANINGS[edge_type])


def add_proposed_cause_edge(graph: nx.MultiDiGraph, *, dataset: str, hypothesis_ref: str,
                            incident_ref: str, source_reference: str) -> None:
    if graph.graph.get("dataset") != dataset:
        raise ValueError("Proposed-cause edge dataset must match graph dataset")
    _add_edge(graph, _node(dataset, "hypothesis", hypothesis_ref), _node(dataset, "incident", incident_ref),
              "PROPOSED_CAUSE_OF", source_reference, INFERRED)


def add_mitigation_edge(graph: nx.MultiDiGraph, *, dataset: str, recommendation_ref: str,
                        incident_ref: str, source_reference: str) -> None:
    if graph.graph.get("dataset") != dataset:
        raise ValueError("Mitigation edge dataset must match graph dataset")
    _add_edge(graph, _node(dataset, "recommendation", recommendation_ref), _node(dataset, "incident", incident_ref),
              "MITIGATED_BY", source_reference, INFERRED)


def calculate_seller_exposure(graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    """Count unique linked orders per seller; counts are exposure, not causation."""
    results = []
    for seller, attributes in graph.nodes(data=True):
        if attributes.get("entity") != "seller" or attributes.get("dataset") != "olist":
            continue
        orders = {target for _, target, edge in graph.out_edges(seller, data=True)
                  if edge.get("edge_type") == "SHIPS" and graph.nodes[target].get("entity") == "order"}
        results.append({"dataset": "olist", "seller_node": seller, "affected_order_count": len(orders),
                        "label": "exposure, not confirmed causation"})
    return sorted(results, key=lambda item: item["seller_node"])


def graph_from_olist_archive(archive_path: Path | str, chunksize: int = 50000) -> nx.MultiDiGraph:
    """Build an Olist-only graph directly from its raw ZIP member."""
    from src.data.loaders import load_olist

    chunks = [frame for name, frame in load_olist(archive_path, chunksize)
              if Path(name).stem == "olist_order_items_dataset"]
    return build_olist_graph(pd.concat(chunks, ignore_index=True))
