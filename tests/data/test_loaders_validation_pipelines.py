"""Small clearly synthetic fixtures for read-only loaders and data pipelines."""
import json
from io import BytesIO
import zipfile

import pandas as pd
import pytest

from src.data.loaders import load_dataco, load_olist, load_online_retail_ii
from src.data.pipelines.olist import run as run_olist
from src.data.validation import validate_frame


def test_dataset_loaders_keep_sources_separate(tmp_path):
    olist = tmp_path / "synthetic_olist.zip"
    with zipfile.ZipFile(olist, "w") as archive:
        archive.writestr("olist_orders_dataset.csv", "order_id\nsynthetic-1\n")
    assert next(load_olist(olist))[1].iloc[0, 0] == "synthetic-1"

    dataco = tmp_path / "synthetic_dataco.zip"
    with zipfile.ZipFile(dataco, "w") as archive:
        archive.writestr("DataCoSupplyChainDataset.csv", "Order Id\n1\n")
        archive.writestr("tokenized_access_logs.csv", "ip\nprivate-ish\n")
    assert len(list(load_dataco(dataco))) == 1


def test_online_retail_loader_reads_synthetic_workbook(tmp_path):
    pytest.importorskip("openpyxl")
    retail = tmp_path / "synthetic_retail.zip"
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame({"Invoice": ["synthetic-1"], "InvoiceDate": ["2020-01-01"], "Quantity": [1]}).to_excel(
            writer, sheet_name="Synthetic Sheet", index=False
        )
    with zipfile.ZipFile(retail, "w") as archive:
        archive.writestr("online_retail_II.xlsx", workbook.getvalue())
    loaded_sheet = next(load_online_retail_ii(retail))
    assert loaded_sheet[0].endswith("[Synthetic Sheet]")
    assert loaded_sheet[1].iloc[0]["Invoice"] == "synthetic-1"


def test_validation_quarantines_invalid_duplicates_and_dates():
    fixture = pd.DataFrame({"id": [1, 2, 1], "when": ["2020-01-01", "bad-date", "2020-01-01"]})
    valid, quarantine, report = validate_frame(fixture, source="synthetic", required_columns=["id"],
                                                expected_types={"id": "numeric"}, date_columns=["when"])
    assert len(valid) == 1
    assert len(quarantine) == 2
    assert report.invalid_dates["when"] == 1
    assert "_quarantine_reasons" in quarantine.columns


def test_pipeline_writes_lineage_and_quarantine(tmp_path):
    archive = tmp_path / "synthetic_olist.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("olist_synthetic.csv", "id,when\n1,2020-01-01\n2,bad-date\n")
    outputs = run_olist(archive, tmp_path / "processed")
    lineage = json.loads((tmp_path / "processed" / "olist" / "lineage.json").read_text())
    assert lineage["source_sha256"]
    assert any("quarantine" in path.name for path in outputs)
