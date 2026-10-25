"""Tests for in-memory dataset profiler and sample-free statistics calculation."""

import io
import zipfile
import pytest

from src.data.profiler import profile_data, MAX_ZIP_ENTRIES


def test_profiler_csv_synthetic():
    csv_content = (
        "order_id,purchase_date,amount,notes\n"
        "ORD-001,2026-01-01,100.50,clean note\n"
        "ORD-002,2026-01-02,200.00,another note\n"
        "ORD-003,2026-01-03,,third note\n"
        "ORD-004,bad-date,400.25,fourth note\n"
    ).encode("utf-8")

    report = profile_data(csv_content, filename="synthetic_orders.csv", dataset_name="synthetic_orders")
    assert report.dataset_name == "synthetic_orders"
    assert report.total_rows == 4
    assert report.total_columns == 4

    col_map = {col.name: col for col in report.columns}
    assert "order_id" in col_map
    assert col_map["order_id"].null_count == 0
    assert col_map["order_id"].unique_count == 4

    # Date parse rate: 3 out of 4 non-null dates parse successfully (75%)
    assert col_map["purchase_date"].date_parse_success_rate == 0.75

    # Amount: 1 null out of 4 (25%)
    assert col_map["amount"].null_count == 1
    assert col_map["amount"].null_percentage == 25.0
    assert col_map["amount"].numeric_stats is not None
    assert col_map["amount"].numeric_stats["min"] == 100.50
    assert col_map["amount"].numeric_stats["max"] == 400.25


def test_profiler_is_strictly_sample_free():
    """Ensure no raw row values or sample snippets are present in the serialized profile report."""
    raw_secret_order = "ORD-SECRET-9999"
    raw_secret_text = "Highly-confidential-supplier-remarks"
    csv_content = f"order_id,remarks\n{raw_secret_order},{raw_secret_text}\n".encode("utf-8")

    report = profile_data(csv_content, filename="synthetic_secret.csv")
    dumped = report.model_dump_json()

    assert raw_secret_order not in dumped
    assert raw_secret_text not in dumped
    # Verify report only has aggregate fields
    for col in report.columns:
        assert not hasattr(col, "sample_values")
        assert not hasattr(col, "head")
        assert not hasattr(col, "examples")


def test_profiler_formula_injection_flag():
    """Detect potential formula injection on cells starting with =, +, -, @."""
    csv_content = (
        "id,command\n"
        "1,normal\n"
        "2,=cmd|' /C calc'!A0\n"
    ).encode("utf-8")

    report = profile_data(csv_content, filename="synthetic_formula.csv")
    assert report.has_formula_injection_risk is True
    cmd_col = next(c for c in report.columns if c.name == "command")
    assert cmd_col.formula_injection_risk is True


def test_profiler_zip_in_memory():
    """Profile CSV compressed inside a ZIP archive in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("orders.csv", "order_id,quantity\nSYNTH-1,10\nSYNTH-2,20\n")

    report = profile_data(buf.getvalue(), filename="synthetic.zip")
    assert report.total_rows == 2
    assert report.total_columns == 2
    assert report.file_type.startswith("zip:")


def test_profiler_zip_bomb_protection():
    """Verify that excessive zip entry counts or uncompressed sizes are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Create too many entries
        for i in range(MAX_ZIP_ENTRIES + 1):
            zf.writestr(f"file_{i}.txt", "data")

    with pytest.raises(ValueError, match="too many entries"):
        profile_data(buf.getvalue(), filename="bomb.zip")


def test_profiler_path_traversal_in_zip():
    """Reject zip members with path traversal components."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../traversal.csv", "a,b\n1,2\n")

    with pytest.raises(ValueError, match="Path traversal detected"):
        profile_data(buf.getvalue(), filename="traversal.zip")
