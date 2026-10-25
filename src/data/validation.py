"""Generic record quality checks; invalid rows are returned separately for quarantine."""

from datetime import datetime, timezone

import pandas as pd
from pydantic import BaseModel, Field


class QualityReport(BaseModel):
    source: str
    total_rows: int
    valid_rows: int
    quarantined_rows: int
    null_counts: dict[str, int] = Field(default_factory=dict)
    duplicate_rows: int = 0
    invalid_dates: dict[str, int] = Field(default_factory=dict)
    type_errors: dict[str, int] = Field(default_factory=dict)
    schema_errors: list[str] = Field(default_factory=list)
    freshness_age_seconds: float | None = None
    freshness_ok: bool | None = None


def validate_frame(frame: pd.DataFrame, *, source: str, required_columns: list[str] | None = None,
                   expected_types: dict[str, str] | None = None, date_columns: list[str] | None = None,
                   freshness_column: str | None = None, freshness_max_age_hours: int = 168,
                   max_null_fraction: float = 1.0) -> tuple[pd.DataFrame, pd.DataFrame, QualityReport]:
    """Return valid, quarantined and summary report; never silently drops bad rows."""
    required_columns = required_columns or []
    expected_types = expected_types or {}
    date_columns = date_columns or []
    errors = pd.DataFrame(index=frame.index)
    schema_errors = [f"Missing required column: {c}" for c in required_columns if c not in frame.columns]
    schema_errors.extend(f"Missing date column: {c}" for c in date_columns if c not in frame.columns)
    if schema_errors:
        errors["schema"] = True
    null_counts = {str(c): int(frame[c].isna().sum()) for c in frame.columns}
    for column in required_columns:
        if column in frame.columns:
            errors[f"null:{column}"] = frame[column].isna()
    type_errors: dict[str, int] = {}
    for column, kind in expected_types.items():
        if column not in frame.columns:
            continue
        if kind in {"numeric", "integer", "float"}:
            converted = pd.to_numeric(frame[column], errors="coerce")
            bad = frame[column].notna() & converted.isna()
            if kind == "integer":
                bad |= converted.notna() & (converted % 1 != 0)
        elif kind == "datetime":
            converted = pd.to_datetime(frame[column], errors="coerce", format="mixed", utc=True)
            bad = frame[column].notna() & converted.isna()
        elif kind == "string":
            bad = frame[column].notna() & frame[column].astype("string").str.strip().eq("")
        else:
            raise ValueError(f"Unsupported expected type '{kind}' for {column}")
        type_errors[column] = int(bad.sum())
        errors[f"type:{column}"] = bad
    invalid_dates: dict[str, int] = {}
    for column in date_columns:
        if column not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce", format="mixed", utc=True)
        bad = frame[column].notna() & parsed.isna()
        invalid_dates[column] = int(bad.sum())
        errors[f"date:{column}"] = bad
    duplicates = frame.duplicated(keep="first")
    errors["duplicate"] = duplicates
    invalid = errors.any(axis=1) if len(errors.columns) else pd.Series(False, index=frame.index)
    freshness_age: float | None = None
    freshness_ok: bool | None = None
    if freshness_column and freshness_column in frame.columns and frame[freshness_column].notna().any():
        parsed = pd.to_datetime(frame[freshness_column], errors="coerce", format="mixed", utc=True).dropna()
        if not parsed.empty:
            freshness_age = (datetime.now(timezone.utc) - parsed.max().to_pydatetime()).total_seconds()
            freshness_ok = freshness_age <= freshness_max_age_hours * 3600
    # Null threshold applies to required columns; optional nulls are reported, not rejected.
    for column in required_columns:
        if column in frame.columns and len(frame) and frame[column].isna().mean() > max_null_fraction:
            schema_errors.append(f"Null fraction exceeds configured limit: {column}")
            errors[f"null_fraction:{column}"] = True
    quarantine = frame.loc[invalid].copy()
    if len(quarantine):
        quarantine["_quarantine_reasons"] = errors.loc[invalid].apply(
            lambda row: ";".join(str(name) for name, failed in row.items() if bool(failed)), axis=1
        )
    valid = frame.loc[~invalid].copy()
    report = QualityReport(source=source, total_rows=len(frame), valid_rows=len(valid), quarantined_rows=len(quarantine),
                           null_counts=null_counts, duplicate_rows=int(duplicates.sum()), invalid_dates=invalid_dates,
                           type_errors=type_errors, schema_errors=schema_errors, freshness_age_seconds=freshness_age,
                           freshness_ok=freshness_ok)
    return valid, quarantine, report
