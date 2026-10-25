"""In-memory dataset profiler computing sample-free statistics without storing raw values."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import BinaryIO
import zipfile

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


MAX_ZIP_ENTRIES = 500
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_COMPRESSION_RATIO = 100


class ColumnProfile(BaseModel):
    """Sample-free column profile containing only aggregate structural statistics."""
    model_config = ConfigDict(extra="forbid")
    name: str
    dtype: str
    total_rows: int
    null_count: int
    null_percentage: float
    unique_count: int
    uniqueness_ratio: float
    date_parse_success_rate: float
    date_formats: list[str] = Field(default_factory=list)
    candidate_identifier: bool = False
    numeric_stats: dict[str, float] | None = None
    string_stats: dict[str, float | int | bool] | None = None
    formula_injection_risk: bool = False


class DatasetProfileReport(BaseModel):
    """Aggregate profile of a dataset containing column profiles without raw data samples."""
    model_config = ConfigDict(extra="forbid")
    dataset_name: str
    source_filename: str
    total_rows: int
    total_columns: int
    columns: list[ColumnProfile]
    file_type: str
    has_formula_injection_risk: bool = False
    processed_rows: int | None = None
    total_rows_known: bool = True
    sheets_detected: list[str] = Field(default_factory=list)
    sheets_imported: list[str] = Field(default_factory=list)
    sheets_skipped: list[dict[str, str]] = Field(default_factory=list)


def _check_zip_bomb(archive: zipfile.ZipFile, total_compressed_bytes: int) -> None:
    """Validate zip archive against zip-bomb and path-traversal attacks."""
    infolist = archive.infolist()
    if len(infolist) > MAX_ZIP_ENTRIES:
        raise ValueError(f"Zip archive contains too many entries ({len(infolist)} > {MAX_ZIP_ENTRIES})")

    total_uncompressed = sum(info.file_size for info in infolist)
    if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
        raise ValueError(
            f"Uncompressed size exceeds safety limit ({total_uncompressed} > {MAX_UNCOMPRESSED_BYTES} bytes)"
        )

    if total_compressed_bytes > 0:
        ratio = total_uncompressed / total_compressed_bytes
        if ratio > MAX_COMPRESSION_RATIO:
            raise ValueError(
                f"Suspicious compression ratio ({ratio:.1f} > {MAX_COMPRESSION_RATIO}), possible zip bomb"
            )

    for info in infolist:
        name = info.filename
        if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
            raise ValueError(f"Path traversal detected in zip entry: '{name}'")


def _read_data_stream(
    stream: BinaryIO, filename: str, member_name: str | None = None
) -> tuple[pd.DataFrame, str]:
    """Read CSV, XLSX, or ZIP content into a pandas DataFrame in memory."""
    stream.seek(0, io.SEEK_END)
    size = stream.tell()
    stream.seek(0)

    lower = filename.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(stream) as archive:
            _check_zip_bomb(archive, size)
            candidates = [
                name for name in archive.namelist()
                if not name.endswith("/") and not Path(name).name.startswith(".")
                and (name.lower().endswith((".csv", ".xlsx", ".xls", ".json", ".jsonl")))
            ]
            if not candidates:
                raise ValueError("No CSV, Excel, or JSON members found inside zip archive")
            selected = member_name if member_name and member_name in archive.namelist() else candidates[0]
            with archive.open(selected) as member_stream:
                member_bytes = member_stream.read()
                if selected.lower().endswith(".csv"):
                    try:
                        df = pd.read_csv(io.BytesIO(member_bytes), low_memory=False)
                    except UnicodeDecodeError:
                        df = pd.read_csv(io.BytesIO(member_bytes), encoding="latin-1", low_memory=False)
                    return df, f"zip:{selected}"
                elif selected.lower().endswith((".json", ".jsonl")):
                    df = pd.read_json(io.BytesIO(member_bytes), lines=selected.lower().endswith(".jsonl"))
                    return df, f"zip:{selected}"
                else:
                    df = pd.read_excel(io.BytesIO(member_bytes))
                    return df, f"zip:{selected}"

    elif lower.endswith(".xlsx") or lower.endswith(".xls"):
        df = pd.read_excel(stream)
        return df, "excel"

    elif lower.endswith((".json", ".jsonl")):
        df = pd.read_json(stream, lines=lower.endswith(".jsonl"))
        return df, "jsonl" if lower.endswith(".jsonl") else "json"
    elif lower.endswith(".csv"):
        try:
            df = pd.read_csv(stream, low_memory=False)
        except UnicodeDecodeError:
            stream.seek(0)
            df = pd.read_csv(stream, encoding="latin-1", low_memory=False)
        return df, "csv"


def profile_column(series: pd.Series, name: str) -> ColumnProfile:
    """Compute aggregate sample-free statistics for one column."""
    total_rows = len(series)
    null_count = int(series.isna().sum())
    null_pct = round((null_count / total_rows * 100.0) if total_rows > 0 else 0.0, 4)

    non_null = series.dropna()
    unique_count = int(non_null.nunique())
    uniqueness_ratio = round((unique_count / total_rows) if total_rows > 0 else 0.0, 4)

    # Date parse rate
    date_parse_rate = 0.0
    if len(non_null) > 0:
        if pd.api.types.is_datetime64_any_dtype(series):
            date_parse_rate = 1.0
        elif pd.api.types.is_numeric_dtype(series):
            # Pure numbers should not be coerced to epoch dates
            date_parse_rate = 0.0
        else:
            # Check up to 500 rows for parseability
            sample_size = min(len(non_null), 500)
            sample_series = non_null.iloc[:sample_size].astype(str)
            parsed = pd.to_datetime(sample_series, errors="coerce", format="mixed")
            date_parse_rate = round(float(parsed.notna().mean()), 4)

    # Formula injection risk on text columns (starts with =, +, -, @, \t, \r)
    formula_risk = False
    numeric_stats: dict[str, float] | None = None
    string_stats: dict[str, float | int | bool] | None = None

    if pd.api.types.is_numeric_dtype(series):
        if len(non_null) > 0:
            numeric_stats = {
                "min": float(non_null.min()) if not math.isnan(float(non_null.min())) else 0.0,
                "max": float(non_null.max()) if not math.isnan(float(non_null.max())) else 0.0,
                "mean": round(float(non_null.mean()), 4) if not math.isnan(float(non_null.mean())) else 0.0,
                "std": round(float(non_null.std()), 4) if len(non_null) > 1 and not math.isnan(float(non_null.std())) else 0.0,
                "median": round(float(non_null.median()), 4) if not math.isnan(float(non_null.median())) else 0.0,
            }
    else:
        # String length statistics and formula risk check
        str_series = non_null.astype(str)
        if len(str_series) > 0:
            lengths = str_series.str.len()
            starts_formula = str_series.str.startswith(("=", "+", "-", "@", "\t", "\r"))
            formula_risk = bool(starts_formula.any())
            string_stats = {
                "min_length": int(lengths.min()),
                "max_length": int(lengths.max()),
                "avg_length": round(float(lengths.mean()), 2),
                "is_alphanumeric": bool(str_series.str.isalnum().all()),
            }

    date_formats = _date_format_candidates(non_null) if len(non_null) else []
    return ColumnProfile(
        name=name,
        dtype=str(series.dtype),
        total_rows=total_rows,
        null_count=null_count,
        null_percentage=null_pct,
        unique_count=unique_count,
        uniqueness_ratio=uniqueness_ratio,
        date_parse_success_rate=date_parse_rate,
        date_formats=date_formats,
        candidate_identifier=bool(total_rows > 0 and uniqueness_ratio >= 0.95),
        numeric_stats=numeric_stats,
        string_stats=string_stats,
        formula_injection_risk=formula_risk,
    )


def _date_format_candidates(values: pd.Series) -> list[str]:
    """Return common observed date shape labels without retaining sample values."""
    if pd.api.types.is_datetime64_any_dtype(values):
        return ["datetime dtype"]
    if pd.api.types.is_numeric_dtype(values):
        return []
    formats: set[str] = set()
    for raw in values.dropna().astype(str).head(500):
        value = raw.strip()
        if not value:
            continue
        if "T" in value or " " in value:
            formats.add("timestamp-like")
        elif "/" in value:
            formats.add("slash-separated date")
        elif "-" in value:
            formats.add("hyphen-separated date")
        elif "." in value:
            formats.add("dot-separated date")
    return sorted(formats)


def profile_data(
    source: bytes | BinaryIO | Path | str,
    filename: str = "dataset.csv",
    dataset_name: str | None = None,
    member_name: str | None = None,
) -> DatasetProfileReport:
    """Profile a dataset in memory, returning aggregate metrics without storing raw samples."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        with path.open("rb") as stream:
            data = stream.read()
        stream_io = io.BytesIO(data)
        eff_filename = filename or path.name
    elif isinstance(source, bytes):
        stream_io = io.BytesIO(source)
        eff_filename = filename
    else:
        content = source.read()
        stream_io = io.BytesIO(content)
        eff_filename = filename

    df, file_type = _read_data_stream(stream_io, eff_filename, member_name=member_name)

    name = dataset_name or Path(eff_filename).stem
    columns: list[ColumnProfile] = []
    has_formula_risk = False

    for col in df.columns:
        col_profile = profile_column(df[col], str(col))
        if col_profile.formula_injection_risk:
            has_formula_risk = True
        columns.append(col_profile)

    return DatasetProfileReport(
        dataset_name=name,
        source_filename=eff_filename,
        total_rows=len(df),
        total_columns=len(df.columns),
        columns=columns,
        file_type=file_type,
        has_formula_injection_risk=has_formula_risk,
    )
