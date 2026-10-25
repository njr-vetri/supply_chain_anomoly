"""Tests for capability detection and DatasetProfile schema validation."""

import pytest
from src.data.profile import DatasetProfile, detect_capabilities


def test_profile_requires_order_id_and_timestamp():
    # Missing order_id
    with pytest.raises(ValueError, match="order_id"):
        DatasetProfile(
            name="synthetic_invalid_1",
            mappings={"when": "order_ts"},
        )

    # Missing timestamp
    with pytest.raises(ValueError, match="timestamp"):
        DatasetProfile(
            name="synthetic_invalid_2",
            mappings={"id": "order_id", "amt": "price"},
        )

    # Valid profile with order_id and one timestamp
    valid_profile = DatasetProfile(
        name="synthetic_valid",
        mappings={"id": "order_id", "ts": "order_ts"},
    )
    assert valid_profile.mappings["id"] == "order_id"


def test_profile_rejects_unknown_canonical_roles():
    with pytest.raises(ValueError, match="Invalid canonical roles"):
        DatasetProfile(
            name="synthetic_bad_role",
            mappings={"id": "order_id", "ts": "order_ts", "extra": "some_unknown_role"},
        )


def test_capabilities_full_profile():
    mappings = {
        "id": "order_id",
        "o_date": "order_ts",
        "p_date": "promised_ts",
        "d_date": "delivered_ts",
        "seller": "supplier_id",
        "item": "product_id",
        "qty": "quantity",
        "cost": "price",
        "stat": "status",
    }
    caps = detect_capabilities(mappings)
    assert caps.anomaly_detection.possible is True
    assert caps.delay_prediction.possible is True
    assert caps.demand_forecasting.possible is True
    assert caps.graph.possible is True


def test_capabilities_missing_roles_reported_when_blocked():
    # Only order_id and order_ts
    mappings = {
        "id": "order_id",
        "o_date": "order_ts",
    }
    caps = detect_capabilities(mappings)

    # Delay prediction blocked because promised_ts and delivered_ts are missing
    assert caps.delay_prediction.possible is False
    assert "promised_ts" in caps.delay_prediction.missing_roles

    # Demand forecasting blocked because product_id and quantity are missing
    assert caps.demand_forecasting.possible is False
    assert "product_id" in caps.demand_forecasting.missing_roles
    assert "quantity" in caps.demand_forecasting.missing_roles

    # Graph blocked because no network entity is present
    assert caps.graph.possible is False
    assert len(caps.graph.missing_roles) > 0
