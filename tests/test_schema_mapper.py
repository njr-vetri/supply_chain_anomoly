"""Tests for schema mapper suggesting canonical roles with confidence scores."""

from src.data.profiler import profile_data
from src.data.schema_mapper import suggest_mappings


def test_schema_mapper_suggests_canonical_roles():
    csv_content = (
        "order_id,order_purchase_timestamp,estimated_delivery,actual_delivery_date,seller_id,price,status\n"
        "ORD-001,2026-01-01,2026-01-10,2026-01-09,SELL-1,99.99,delivered\n"
        "ORD-002,2026-01-02,2026-01-12,2026-01-11,SELL-2,149.50,delivered\n"
    ).encode("utf-8")

    report = profile_data(csv_content, filename="synthetic_orders.csv")
    mapping_report = suggest_mappings(report)

    # CRITICAL: It never auto-confirms
    assert mapping_report.auto_confirmed is False
    assert mapping_report.status == "PENDING_REVIEW"

    suggestions = {s.column_name: s for s in mapping_report.suggestions}

    assert suggestions["order_id"].suggested_role == "order_id"
    assert suggestions["order_id"].confidence >= 0.80

    assert suggestions["order_purchase_timestamp"].suggested_role == "order_ts"
    assert suggestions["order_purchase_timestamp"].confidence >= 0.80

    assert suggestions["estimated_delivery"].suggested_role == "promised_ts"
    assert suggestions["actual_delivery_date"].suggested_role == "delivered_ts"
    assert suggestions["seller_id"].suggested_role == "supplier_id"
    assert suggestions["price"].suggested_role == "price"
    assert suggestions["status"].suggested_role == "status"


def test_schema_mapper_penalizes_value_contradictions():
    """Ensure non-date column with date-like name receives a confidence penalty."""
    csv_content = (
        "order_date,amount\n"
        "NOT_A_DATE_TEXT_1,100\n"
        "NOT_A_DATE_TEXT_2,200\n"
    ).encode("utf-8")

    report = profile_data(csv_content, filename="synthetic_bad_dates.csv")
    mapping_report = suggest_mappings(report)

    suggestions = {s.column_name: s for s in mapping_report.suggestions}
    # order_date has 0% date parse rate -> confidence must be severely penalized
    assert suggestions["order_date"].confidence < 0.60
    assert "Contradicted" in suggestions["order_date"].reason


def test_schema_mapper_handles_unmatched_columns():
    csv_content = (
        "order_id,order_date,random_unrelated_column_xyz\n"
        "ORD-1,2026-01-01,foobar\n"
    ).encode("utf-8")

    report = profile_data(csv_content, filename="synthetic_random.csv")
    mapping_report = suggest_mappings(report)

    suggestions = {s.column_name: s for s in mapping_report.suggestions}
    assert suggestions["random_unrelated_column_xyz"].suggested_role is None
    assert suggestions["random_unrelated_column_xyz"].confidence == 0.0
