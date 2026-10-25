"""Synthetic fixtures verify adapter contracts and tenant boundaries only."""
import zipfile
import hashlib
import json

import pandas as pd
import pytest
from sqlalchemy import create_engine

from src.adapters.base import get_adapter
from src.adapters.canonical import CanonicalOrder, parquet_schemas
from src.adapters.dataco import Adapter as DataCoAdapter
from src.adapters.olist import Adapter as OlistAdapter
from src.adapters.retail_ii import Adapter as RetailIIAdapter
from src.core.repository import AuditEventRow, Base, DatasetVersionRow, IncidentRow, Repository
from src.core.tenant_files import TenantFileStore
from src.data.profile import DatasetProfile


def profile(name="synthetic"):
    return DatasetProfile(name=name, mappings={"Order": "order_id", "Placed": "order_ts", "Other": "status"})


def test_canonical_conversion_keeps_unknown_columns_and_source_locator():
    adapter = OlistAdapter(profile("synthetic"))
    frame = pd.DataFrame({"Order": ["synthetic-order"], "Placed": ["2026-01-01"],
                          "Other": ["synthetic-status"], "Extra": ["synthetic-preserved"]})
    canonical = adapter.to_canonical(frame)
    assert canonical.loc[0, "event_id"] == "synthetic-order"
    assert canonical.loc[0, "custom_fields"] == {"Extra": "synthetic-preserved"}
    record = CanonicalOrder.model_validate(canonical.iloc[0].to_dict())
    assert record.order_id == "synthetic-order"
    assert record.event_timestamp.year == 2026


def test_canonical_record_requires_identifier_and_timestamp():
    with pytest.raises(Exception):
        CanonicalOrder.model_validate({"event_id": "synthetic-id"})


def test_adapter_contracts_read_synthetic_zip_in_memory(tmp_path):
    archive = tmp_path / "synthetic.csv.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("olist_orders_dataset.csv", "Order,Placed,Other\nsynthetic-1,2026-01-01,ok\n")
    adapter = OlistAdapter(profile("synthetic"))
    assert adapter.detect(archive)
    member, chunk = next(adapter.read_chunks(archive, chunksize=1))
    assert member == "olist_orders_dataset.csv"
    assert len(chunk) == 1
    assert DataCoAdapter(profile("synthetic")).detect(archive) is False
    assert RetailIIAdapter(profile("synthetic")).detect(archive) is False


def test_saved_profiles_drive_real_adapter_registry():
    for dataset in ("olist", "dataco", "online_retail_ii"):
        adapter = get_adapter(dataset, "config/profiles")
        assert adapter.profile.name == dataset


def test_company_repository_cannot_read_other_company_rows_or_files(tmp_path):
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    company_a = Repository("sqlite://", company_id="synthetic-company-a", engine=engine)
    company_b = Repository("sqlite://", company_id="synthetic-company-b", engine=engine)
    row_a = IncidentRow(id="synthetic-a-row", dataset_version_id="synthetic-dataset-a",
        source="synthetic", title="synthetic A", occurred_at=pd.Timestamp("2026-01-01").to_pydatetime())
    # Isolate this test from unrelated foreign keys by adding the parent first.
    company_a.add(DatasetVersionRow(id="synthetic-dataset-a", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash-a", observed_at=pd.Timestamp("2026-01-01").to_pydatetime(), payload={}))
    company_a.add(row_a)
    company_b.add(DatasetVersionRow(id="synthetic-dataset-b", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash-b", observed_at=pd.Timestamp("2026-01-01").to_pydatetime(), payload={}))
    company_b.add(IncidentRow(id="synthetic-b-row", dataset_version_id="synthetic-dataset-b",
        source="synthetic", title="synthetic B", occurred_at=pd.Timestamp("2026-01-01").to_pydatetime()))
    assert company_a.get(IncidentRow, "synthetic-b-row") is None
    assert company_b.get(IncidentRow, "synthetic-a-row") is None
    assert [row.id for row in company_a.list_rows(IncidentRow)] == ["synthetic-a-row"]

    files_a = TenantFileStore(tmp_path, company_id="synthetic-company-a")
    files_b = TenantFileStore(tmp_path, company_id="synthetic-company-b")
    files_a.write_bytes("synthetic/fixture.bin", b"synthetic A")
    files_b.write_bytes("synthetic/fixture.bin", b"synthetic B")
    assert files_a.read_bytes("synthetic/fixture.bin") == b"synthetic A"
    assert files_b.read_bytes("synthetic/fixture.bin") == b"synthetic B"
    with pytest.raises(FileNotFoundError):
        files_b.read_bytes("only-a.bin")
    with pytest.raises(ValueError):
        files_a.read_bytes("../synthetic-company-b/synthetic/fixture.bin")


def test_soft_delete_retains_row_and_appends_audit_event():
    repo = Repository("sqlite:///:memory:", company_id="synthetic-company")
    repo.add(DatasetVersionRow(id="synthetic-dataset", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=pd.Timestamp("2026-01-01").to_pydatetime(), payload={}))
    repo.add(IncidentRow(id="synthetic-incident", dataset_version_id="synthetic-dataset",
        source="synthetic", title="synthetic record", occurred_at=pd.Timestamp("2026-01-01").to_pydatetime()))
    assert repo.soft_delete(IncidentRow, "synthetic-incident", actor="synthetic-reviewer", reason="synthetic reason")
    assert repo.get(IncidentRow, "synthetic-incident") is None
    assert repo.get(IncidentRow, "synthetic-incident", include_deleted=True) is not None
    events = repo.list_rows(AuditEventRow)
    assert len(events) == 1
    event = events[0]
    from src.core.audit import GENESIS_HASH
    payload = {"event_type": event.event_type, "actor": event.actor, "source": event.source,
               "record_refs": event.payload["record_refs"], "details": event.payload["details"]}
    canonical = json.dumps({"previous_hash": GENESIS_HASH, **payload}, sort_keys=True,
                           separators=(",", ":"), default=str)
    assert event.previous_hash == GENESIS_HASH
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == event.event_hash


def test_parquet_schema_has_nonnullable_identity_and_timestamp():
    pytest.importorskip("pyarrow")
    schema = parquet_schemas()["orders"]
    assert schema.field("event_id").nullable is False
    assert schema.field("event_timestamp").nullable is False
