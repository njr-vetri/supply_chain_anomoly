import pandas as pd

from src.data.profile import DatasetProfile
from src.data.validation import validate_frame


def test_saved_profiles_exist_and_are_valid():
    """Verify that Olist, DataCo, and Retail II have valid saved YAML profiles."""
    for name in ["olist", "dataco", "online_retail_ii"]:
        profile = DatasetProfile.load(name, profile_dir="config/profiles")
        assert profile.name == name
        assert "order_id" in profile.mappings.values()
        assert any(role in profile.mappings.values() for role in ["order_ts", "promised_ts", "delivered_ts"])
        assert profile.capabilities is not None


def test_validation_row_count_regression_synthetic():
    """Compare profile-derived required columns against previous pipeline required columns."""
    # 1. Olist comparison
    olist_profile = DatasetProfile.load("olist", profile_dir="config/profiles")
    # In previous pipeline: ["order_id", "order_purchase_timestamp"]
    legacy_olist_required = ["order_id", "order_purchase_timestamp"]
    profile_olist_required = [
        col for col, role in olist_profile.mappings.items()
        if role in {"order_id", "order_ts"}
    ]
    assert set(legacy_olist_required) == set(profile_olist_required)

    olist_synthetic_data = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", None, "ORD-4", "ORD-1"],  # 1 null, 1 duplicate
        "order_purchase_timestamp": ["2026-01-01", "2026-01-02", "2026-01-03", None, "2026-01-01"],
        "price": [10.0, 20.0, 30.0, 40.0, 10.0],
    })

    v_legacy, q_legacy, r_legacy = validate_frame(
        olist_synthetic_data, source="olist:test", required_columns=legacy_olist_required
    )
    v_profile, q_profile, r_profile = validate_frame(
        olist_synthetic_data, source="olist:test", required_columns=profile_olist_required
    )

    assert len(v_legacy) == len(v_profile)
    assert len(q_legacy) == len(q_profile)
    assert r_legacy.valid_rows == r_profile.valid_rows
    assert r_legacy.quarantined_rows == r_profile.quarantined_rows

    # 2. DataCo comparison
    dataco_profile = DatasetProfile.load("dataco", profile_dir="config/profiles")
    profile_dataco_required = [
        col for col, role in dataco_profile.mappings.items()
        if role in {"order_id", "order_ts"}
    ]
    # Check that required columns contain Order Item Id and order date (DateOrders)
    assert "Order Item Id" in profile_dataco_required
    assert "order date (DateOrders)" in profile_dataco_required

    dataco_synthetic_data = pd.DataFrame({
        "Order Item Id": ["1", "2", None, "4"],
        "order date (DateOrders)": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "Late_delivery_risk": [0, 1, 0, 1],
    })
    v_dataco_legacy, q_dataco_legacy, _ = validate_frame(
        dataco_synthetic_data, source="dataco:test",
        required_columns=["Order Item Id", "order date (DateOrders)"]
    )
    v_dataco_profile, q_dataco_profile, _ = validate_frame(
        dataco_synthetic_data, source="dataco:test",
        required_columns=profile_dataco_required
    )
    assert len(v_dataco_legacy) == len(v_dataco_profile)
    assert len(q_dataco_legacy) == len(q_dataco_profile)

    # 3. Retail II comparison
    retail_profile = DatasetProfile.load("online_retail_ii", profile_dir="config/profiles")
    profile_retail_required = [
        col for col, role in retail_profile.mappings.items()
        if role in {"product_id", "quantity", "order_ts"}
    ]
    legacy_retail_required = ["StockCode", "InvoiceDate", "Quantity"]
    assert set(profile_retail_required) == set(legacy_retail_required)
    retail_synthetic_data = pd.DataFrame({
        "Invoice": ["INV-1", "INV-2", None, "INV-4"],
        "StockCode": ["SKU-1", "SKU-2", "SKU-3", None],
        "Quantity": [10, 20, 30, 40],
        "InvoiceDate": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
    })
    v_ret_legacy, q_ret_legacy, _ = validate_frame(
        retail_synthetic_data, source="retail:test",
        required_columns=["StockCode", "InvoiceDate", "Quantity"]
    )
    v_ret_profile, q_ret_profile, _ = validate_frame(
        retail_synthetic_data, source="retail:test",
        required_columns=profile_retail_required
    )
    assert len(v_ret_legacy) == len(v_ret_profile)
    assert len(q_ret_legacy) == len(q_ret_profile)
