"""Generic, role-driven data quality reporting per dataset and per project."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.repository import (
    DataSourceRow, ImportJobRow, MappingVersionRow, ProjectRow,
    RelationshipProposalRow, Repository,
)
from src.data.onboarding import json_record_chunks

NUMERIC_ROLES = {"quantity", "price", "unit_cost", "units_sold", "on_hand_quantity"}
DATE_ROLES = {"order_ts", "event_timestamp", "promised_ts", "promised_timestamp",
              "delivered_ts", "delivered_timestamp", "ship_date", "arrival_date", "date"}
REQUIRED_ROLES = {"order_id", "promised_ts", "promised_timestamp", "event_timestamp",
                  "order_ts", "product_id", "supplier_id"}
DELIVERY_ROLES = {"delivered_ts", "delivered_timestamp"}


def _load_raw_df(file_path: Path, max_rows: int = 100000) -> pd.DataFrame:
    """Read tabular file into pandas DataFrame safely."""
    if not file_path.exists():
        return pd.DataFrame()
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".csv":
            try:
                return pd.read_csv(file_path, nrows=max_rows, low_memory=False)
            except UnicodeDecodeError:
                return pd.read_csv(file_path, nrows=max_rows, encoding="latin-1", low_memory=False)
        elif suffix in {".xlsx", ".xlsm"}:
            from openpyxl import load_workbook
            with file_path.open("rb") as stream:
                wb = load_workbook(stream, read_only=True, data_only=True)
                for s_name in wb.sheetnames:
                    sheet = wb[s_name]
                    iterator = sheet.iter_rows(values_only=True)
                    first_row = next(iterator, None)
                    if not first_row:
                        continue
                    non_empty = [c for c in first_row if c is not None and str(c).strip()]
                    if len(non_empty) < 2 or s_name.strip().lower() in {"notes", "note", "readme"}:
                        continue
                    headers = [str(v) if v is not None else f"column_{i+1}" for i, v in enumerate(first_row)]
                    rows = []
                    for row in iterator:
                        rows.append(row)
                        if len(rows) >= max_rows:
                            break
                    wb.close()
                    return pd.DataFrame(rows, columns=headers)
                wb.close()
                return pd.DataFrame()
        elif suffix in {".jsonl", ".ndjson"}:
            return pd.read_json(file_path, lines=True, nrows=max_rows)
        elif suffix == ".json":
            with file_path.open("rb") as stream:
                chunks = list(json_record_chunks(stream, max_rows))
                return chunks[0] if chunks else pd.DataFrame()
    except Exception:
        pass
    return pd.DataFrame()


def compute_dataset_quality_report(repo: Repository, dataset_name: str) -> dict[str, Any]:
    """Compute generic data quality counts driven by mapped roles, never raw column names."""
    sources = [s for s in repo.list_rows(DataSourceRow) if s.name == dataset_name]
    if not sources:
        return {"dataset_name": dataset_name, "error": "Dataset not found", "total_rows": 0}
    source = max(sources, key=lambda s: s.created_at)
    
    # Get mapping
    mappings = [m for m in repo.list_rows(MappingVersionRow)
                if m.data_source_id == source.id and m.status == "ACCEPTED"]
    mapping_row = max(mappings, key=lambda m: m.version) if mappings else None
    col_to_role: dict[str, str] = mapping_row.mapping.get("mappings", {}) if mapping_row else {}

    # Get latest import job
    jobs = [j for j in repo.list_rows(ImportJobRow) if j.data_source_id == source.id]
    latest_job = max(jobs, key=lambda j: j.created_at) if jobs else None
    quarantined_count = 0
    if latest_job and latest_job.payload:
        quarantined_count = int(latest_job.payload.get("quarantined_rows") or 0)

    # Read dataframe
    df = _load_raw_df(Path(source.location_ref))
    total_rows = len(df)
    if df.empty:
        return {
            "dataset_name": dataset_name,
            "total_rows": 0,
            "exact_duplicate_rows": 0,
            "negative_values": 0,
            "invalid_dates": 0,
            "blank_required_values": 0,
            "open_records": 0,
            "extreme_outliers": 0,
            "quarantined_rows": quarantined_count,
        }

    # 1. Exact duplicate rows
    exact_duplicates = int(df.duplicated().sum())

    # 2. Negative values in quantity/price roles
    negative_values = 0
    for col, role in col_to_role.items():
        if role in NUMERIC_ROLES and col in df.columns:
            nums = pd.to_numeric(df[col], errors="coerce")
            negative_values += int((nums < 0).sum())

    # 3. Invalid dates in date/timestamp roles
    invalid_dates = 0
    for col, role in col_to_role.items():
        if role in DATE_ROLES and col in df.columns:
            non_null = df[col].dropna()
            for val in non_null:
                val_str = str(val).strip()
                if not val_str or val_str.lower() in {"null", "none", "nan", "nat"}:
                    continue
                try:
                    pd.to_datetime(val_str)
                except Exception:
                    invalid_dates += 1

    # 4. Blank values in mapped required roles
    blank_required = 0
    for col, role in col_to_role.items():
        if role in REQUIRED_ROLES and col in df.columns:
            blanks = df[col].isna() | (df[col].astype(str).str.strip().isin(["", "nan", "null", "none"]))
            blank_required += int(blanks.sum())

    # 5. Open records (missing delivered timestamp)
    open_records = 0
    for col, role in col_to_role.items():
        if role in DELIVERY_ROLES and col in df.columns:
            open_records = int(df[col].isna().sum() + (df[col].astype(str).str.strip().isin(["", "nan", "null", "none"])).sum())

    # 6. Extreme outliers (3 * IQR)
    extreme_outliers = 0
    for col, role in col_to_role.items():
        if (role in NUMERIC_ROLES or "late" in col.lower() or "delay" in col.lower()) and col in df.columns:
            clean = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(clean) >= 10:
                q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    outliers = ((clean < q1 - 3 * iqr) | (clean > q3 + 3 * iqr)).sum()
                    extreme_outliers += int(outliers)

    return {
        "dataset_name": dataset_name,
        "total_rows": total_rows,
        "exact_duplicate_rows": exact_duplicates,
        "negative_values": negative_values,
        "invalid_dates": invalid_dates,
        "blank_required_values": blank_required,
        "open_records": open_records,
        "extreme_outliers": extreme_outliers,
        "quarantined_rows": quarantined_count,
    }


def compute_project_quality_report(repo: Repository, project_id: str) -> dict[str, Any]:
    """Compute aggregate and per-dataset data quality report including cross-table foreign keys and orphans."""
    sources = [s for s in repo.list_rows(DataSourceRow) if s.project_id == project_id]
    dataset_reports = {}
    dataframes: dict[str, pd.DataFrame] = {}
    col_mappings: dict[str, dict[str, str]] = {}

    for source in sources:
        rep = compute_dataset_quality_report(repo, source.name)
        dataset_reports[source.name] = rep
        df = _load_raw_df(Path(source.location_ref))
        if not df.empty:
            dataframes[source.name] = df
            mappings = [m for m in repo.list_rows(MappingVersionRow)
                        if m.data_source_id == source.id and m.status == "ACCEPTED"]
            mapping_row = max(mappings, key=lambda m: m.version) if mappings else None
            if mapping_row:
                col_mappings[source.name] = mapping_row.mapping.get("mappings", {})

    # Cross-table relational checks: unknown foreign keys and orphan rows
    unknown_foreign_keys = 0
    orphan_rows = 0

    # Read approved relationship proposals
    proposals = [p for p in repo.list_rows(RelationshipProposalRow) if p.status == "APPROVED"]
    approved_links = []
    for prop in proposals:
        approved_links.extend(prop.payload.get("links", []))

    source_by_id = {s.id: s.name for s in sources}

    # Evaluate approved links
    checked_pairs = set()
    for link in approved_links:
        left_src = source_by_id.get(link.get("left_source_id"))
        right_src = source_by_id.get(link.get("right_source_id"))
        left_key = link.get("left_key")
        right_key = link.get("right_key")
        rel_type = link.get("relationship", "")
        if left_src and right_src and left_key and right_key and left_src in dataframes and right_src in dataframes:
            pair_key = (left_src, left_key, right_src, right_key)
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            df_left = dataframes[left_src]
            df_right = dataframes[right_src]
            if left_key in df_left.columns and right_key in df_right.columns:
                left_vals = df_left[left_key].dropna()
                right_vals = set(df_right[right_key].dropna())
                missing_in_right = int((~left_vals.isin(right_vals)).sum())
                
                # If left is PO and right is Vendor (Supplier relationship) -> Unknown vendor codes
                if "supplier" in rel_type or "vendor" in left_key.lower():
                    unknown_foreign_keys += missing_in_right
                # If right is shipments referencing PO (or child-parent relationship) -> Orphan shipments
                elif "shipment" in rel_type or "order_shipment" in rel_type:
                    # check right keys not in left
                    right_non_null = df_right[right_key].dropna()
                    left_set = set(df_left[left_key].dropna())
                    missing_in_left = int((~right_non_null.isin(left_set)).sum())
                    orphan_rows += missing_in_left
                else:
                    unknown_foreign_keys += missing_in_right

    # If no approved proposals were found, fall back to checking mapped roles between orders, shipments, vendors
    if not approved_links:
        # Check POs vs Vendors
        po_name = next((s for s in dataframes if "order" in s), None)
        ven_name = next((s for s in dataframes if "vendor" in s or "supplier" in s), None)
        shp_name = next((s for s in dataframes if "shipment" in s), None)

        if po_name and ven_name:
            po_df = dataframes[po_name]
            ven_df = dataframes[ven_name]
            # find vendor key
            po_v_col = next((c for c, r in col_mappings.get(po_name, {}).items() if r == "supplier_id"), "vendor_code")
            ven_v_col = next((c for c, r in col_mappings.get(ven_name, {}).items() if r == "supplier_id"), "vendor_code")
            if po_v_col in po_df.columns and ven_v_col in ven_df.columns:
                unknown_foreign_keys += int((~po_df[po_v_col].dropna().isin(set(ven_df[ven_v_col].dropna()))).sum())

        if po_name and shp_name:
            po_df = dataframes[po_name]
            shp_df = dataframes[shp_name]
            po_o_col = next((c for c, r in col_mappings.get(po_name, {}).items() if r == "order_id"), "po_number")
            shp_o_col = next((c for c, r in col_mappings.get(shp_name, {}).items() if r == "order_id"), "po_number")
            if po_o_col in po_df.columns and shp_o_col in shp_df.columns:
                orphan_rows += int((~shp_df[shp_o_col].dropna().isin(set(po_df[po_o_col].dropna()))).sum())

    total_exact_duplicates = sum(r.get("exact_duplicate_rows", 0) for r in dataset_reports.values())
    total_negative_values = sum(r.get("negative_values", 0) for r in dataset_reports.values())
    total_invalid_dates = sum(r.get("invalid_dates", 0) for r in dataset_reports.values())
    total_blank_required = sum(r.get("blank_required_values", 0) for r in dataset_reports.values())
    total_open_records = sum(r.get("open_records", 0) for r in dataset_reports.values())
    total_extreme_outliers = sum(r.get("extreme_outliers", 0) for r in dataset_reports.values())
    total_quarantined = sum(r.get("quarantined_rows", 0) for r in dataset_reports.values())

    return {
        "project_id": project_id,
        "summary": {
            "exact_duplicate_rows": total_exact_duplicates,
            "negative_values": total_negative_values,
            "invalid_dates": total_invalid_dates,
            "blank_required_values": total_blank_required,
            "unknown_foreign_keys": unknown_foreign_keys,
            "orphan_rows": orphan_rows,
            "open_records": total_open_records,
            "extreme_outliers": total_extreme_outliers,
            "quarantined_rows": total_quarantined,
        },
        "datasets": dataset_reports,
        "quarantined_rows": {name: r.get("quarantined_rows", 0) for name, r in dataset_reports.items()},
    }
