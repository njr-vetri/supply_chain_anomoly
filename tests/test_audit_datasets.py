"""Small, clearly synthetic checks for the read-only archive auditor."""

from pathlib import Path

import pandas as pd

from scripts.audit_datasets import identify_dataset, inspect_frame


def test_identifies_synthetic_olist_archive(tmp_path: Path) -> None:
    """Synthetic archive filename/member names exercise naming only, not data claims."""
    import zipfile

    path = tmp_path / "sample.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("olist_orders_dataset.csv", "order_id\nsynthetic-1\n")
    assert identify_dataset(path) == "olist"


def test_inspect_frame_reports_observed_synthetic_values() -> None:
    """Synthetic frame validates missingness, duplicates, and ID uniqueness reporting."""
    frame = pd.DataFrame({"order_id": ["a", "a", None], "order_delivered_at": ["2020-01-01", None, None]})
    result = inspect_frame("synthetic.csv", frame)
    assert result["rows"] == 3
    assert result["duplicate_rows"] == 0
    assert result["columns"][0]["missing_percent"] == 33.3333
    assert result["id_uniqueness"] == ["order_id: 1/2 non-null values unique"]
