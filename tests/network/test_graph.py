"""Synthetic-only graph tests; no real-world causation claims."""
import pandas as pd
import pytest

from src.network.graph import (ESTABLISHED, INFERRED, add_evidence_edge, add_mitigation_edge,
                               add_proposed_cause_edge, build_olist_graph, calculate_seller_exposure)


def test_olist_relationship_edges_have_meaning_provenance_and_established_flag():
    graph = build_olist_graph(pd.DataFrame({"order_id": ["synthetic-order"], "seller_id": ["synthetic-seller"],
                                            "product_id": ["synthetic-product"], "order_item_id": [1]}))
    assert graph.graph["dataset"] == "olist"
    assert graph.number_of_edges() == 3
    for _, _, edge in graph.edges(data=True):
        assert edge["meaning"] and edge["source_reference"].startswith("olist_order_items_dataset.csv")
        assert edge["flag"] == ESTABLISHED
    exposure = calculate_seller_exposure(graph)
    assert exposure[0]["affected_order_count"] == 1
    assert "not confirmed causation" in exposure[0]["label"]


def test_inferred_graph_edges_are_distinguished_and_sources_cannot_cross():
    graph = build_olist_graph(pd.DataFrame({"order_id": ["o"], "seller_id": ["s"], "product_id": ["p"]}))
    add_evidence_edge(graph, dataset="olist", evidence_ref="e-1", target_ref="h-1", classification="supporting")
    add_proposed_cause_edge(graph, dataset="olist", hypothesis_ref="h-1", incident_ref="i-1", source_reference="h-1")
    add_mitigation_edge(graph, dataset="olist", recommendation_ref="r-1", incident_ref="i-1", source_reference="r-1")
    flags = {edge["edge_type"]: edge["flag"] for _, _, edge in graph.edges(data=True)}
    assert flags["SUPPORTS"] == ESTABLISHED
    assert flags["PROPOSED_CAUSE_OF"] == INFERRED
    assert flags["MITIGATED_BY"] == INFERRED
    with pytest.raises(ValueError, match="dataset"):
        add_evidence_edge(graph, dataset="dataco", evidence_ref="e", target_ref="h", classification="supporting")
