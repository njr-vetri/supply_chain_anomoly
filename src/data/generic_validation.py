"""Configurable, non-destructive validation for canonical records."""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from src.adapters.canonical import CanonicalRecord


class RuleConfig(BaseModel):
    missing_required: bool = True
    duplicates: bool = True
    invalid_dates: bool = True
    negative_quantity: bool = True
    broken_relationships: bool = True
    unit_currency_consistency: bool = True
    schema_change: bool = True
    outliers: bool = True
    outlier_iqr_multiplier: float = Field(default=1.5, gt=0)


class ValidationReport(BaseModel):
    total_records: int
    flagged_records: int
    rule_counts: dict[str, int]
    record_flags: list[dict[str, Any]]
    schema_added: list[str] = Field(default_factory=list)
    schema_missing: list[str] = Field(default_factory=list)
    unusual_values_rejected: bool = False


def validate_canonical_records(records: list[dict[str, Any]], *, rules: RuleConfig | None = None,
                               expected_schema: set[str] | None = None,
                               approved_relationships: set[tuple[str, str]] | None = None,
                               units: dict[str, str] | None = None) -> ValidationReport:
    rules = rules or RuleConfig()
    approved_relationships = approved_relationships or set()
    units = units or {}
    flags: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()

    def flag(index: int, rule: str) -> None:
        flags.setdefault(str(index), []).append(rule)
        counts[rule] += 1

    for index, record in enumerate(records):
        try:
            CanonicalRecord.model_validate(record)
        except Exception:
            if rules.missing_required:
                flag(index, "missing_or_invalid_required_fields")
        timestamp = record.get("event_timestamp")
        if rules.invalid_dates and timestamp is not None:
            try:
                pd.to_datetime(timestamp, errors="raise", utc=True)
            except (ValueError, TypeError, OverflowError):
                flag(index, "invalid_date")
        if rules.negative_quantity and record.get("quantity") is not None:
            try:
                if float(record["quantity"]) < 0:
                    flag(index, "negative_quantity")
            except (ValueError, TypeError):
                flag(index, "invalid_quantity_type")
        if rules.broken_relationships:
            for role in ("order_id", "supplier_id", "product_id", "warehouse_id", "carrier_id"):
                value = record.get(role)
                if value and approved_relationships and (role, str(value)) not in approved_relationships:
                    flag(index, f"unresolved_{role}_reference")
    if rules.duplicates:
        seen: set[str] = set()
        for index, record in enumerate(records):
            key = str(record.get("event_id", ""))
            if key and key in seen:
                flag(index, "duplicate_event_id")
            seen.add(key)
    if rules.unit_currency_consistency:
        for role, values in (("unit", [units.get(k) for k in ("quantity", "price") if units.get(k)]),
                             ("currency", [units.get(k) for k in ("price", "currency") if units.get(k)])):
            if len(set(values)) > 1:
                for index in range(len(records)):
                    flag(index, f"inconsistent_{role}")
    columns = set().union(*(record.keys() for record in records)) if records else set()
    added = sorted(columns - expected_schema) if expected_schema is not None else []
    missing = sorted(expected_schema - columns) if expected_schema is not None else []
    if rules.schema_change and (added or missing):
        for index in range(len(records)):
            flag(index, "schema_change")
    if rules.outliers and len(records) >= 4:
        frame = pd.DataFrame(records)
        for column in ("quantity", "price"):
            if column not in frame:
                continue
            numeric = pd.to_numeric(frame[column], errors="coerce")
            clean = numeric.dropna()
            if len(clean) < 4:
                continue
            q1, q3 = clean.quantile([0.25, 0.75])
            spread = q3 - q1
            low, high = q1 - rules.outlier_iqr_multiplier * spread, q3 + rules.outlier_iqr_multiplier * spread
            for index in numeric.index[(numeric < low) | (numeric > high)]:
                flag(int(index), f"outlier_{column}")
    return ValidationReport(total_records=len(records), flagged_records=len(flags),
        rule_counts=dict(counts), record_flags=[{"record_ref": records[int(i)].get("source_record_ref") or
        records[int(i)].get("event_id"), "rules": values} for i, values in sorted(flags.items(), key=lambda pair: int(pair[0]))],
        schema_added=added, schema_missing=missing)
