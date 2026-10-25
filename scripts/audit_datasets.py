"""Read-only structural audit of dataset archives; never extracts files to disk."""

from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd


DATASET_ALIASES = {
    "olist": ("olist",),
    "dataco": ("dataco", "data_co", "data co"),
    "online_retail_ii": ("online+retail+ii", "online_retail", "online retail"),
}
DATE_HINTS = ("date", "time", "created", "delivered", "purchase", "invoice", "shipping")
ID_HINTS = ("id", "key", "number", "code")
LABEL_HINTS = ("label", "target", "class", "delay", "late", "risk", "fraud", "cancel", "review_score")


def identify_dataset(path: Path) -> str:
    """Identify known dataset family using archive filename and member names."""
    with zipfile.ZipFile(path) as archive:
        searchable = (path.name + " " + " ".join(archive.namelist())).lower()
    for name, aliases in DATASET_ALIASES.items():
        if any(alias in searchable for alias in aliases):
            return name
    return re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or "dataset"


def _read_member(archive: zipfile.ZipFile, member: str) -> list[tuple[str, pd.DataFrame]]:
    """Read a CSV or Excel workbook directly from the ZIP into memory."""
    suffix = Path(member).suffix.lower()
    if suffix == ".csv":
        with archive.open(member) as stream:
            # DataCo CSVs may use a non-UTF8 encoding; pandas reports decoding errors clearly.
            try:
                frame = pd.read_csv(stream, encoding="utf-8", low_memory=False)
            except UnicodeDecodeError:
                stream.seek(0)
                frame = pd.read_csv(stream, encoding="latin-1", low_memory=False)
        return [(member, frame)]
    if suffix in {".xlsx", ".xls"}:
        raw = archive.read(member)
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        return [(f"{member} [{sheet}]", frame) for sheet, frame in sheets.items()]
    return []


def _date_coverage(frame: pd.DataFrame) -> list[str]:
    results: list[str] = []
    for column in frame.columns:
        if not any(hint in str(column).lower() for hint in DATE_HINTS):
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce", format="mixed")
        valid = parsed.dropna()
        if len(valid):
            results.append(f"{column}: {valid.min()} to {valid.max()} ({len(valid):,} parseable values)")
    return results


def _id_uniqueness(frame: pd.DataFrame) -> list[str]:
    results: list[str] = []
    for column in frame.columns:
        name = str(column).lower()
        if any(hint in name for hint in ID_HINTS):
            non_null = frame[column].dropna()
            if len(non_null):
                results.append(f"{column}: {non_null.nunique(dropna=True):,}/{len(non_null):,} non-null values unique")
    return results


def inspect_frame(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    """Summarize observable structure and quality for one table/sheet."""
    columns = []
    for column in frame.columns:
        series = frame[column]
        columns.append({
            "name": str(column), "dtype": str(series.dtype),
            "missing_percent": round(float(series.isna().mean() * 100), 4),
        })
    candidate_labels = [str(c) for c in frame.columns if any(h in str(c).lower() for h in LABEL_HINTS)]
    return {
        "name": name, "rows": int(len(frame)), "columns": columns,
        "duplicate_rows": int(frame.duplicated().sum()),
        "date_coverage": _date_coverage(frame), "id_uniqueness": _id_uniqueness(frame),
        "candidate_labels": candidate_labels,
    }


def audit_archive(path: Path) -> tuple[str, list[dict[str, Any]], list[str]]:
    dataset = identify_dataset(path)
    reports: list[dict[str, Any]] = []
    members: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            members.append(f"{info.filename} ({info.file_size:,} bytes uncompressed)")
            for name, frame in _read_member(archive, info.filename):
                reports.append(inspect_frame(name, frame))
    issues: list[str] = []
    if dataset == "dataco":
        issues.append("The archive contains a field named as a late/delay outcome (verify its definition and prediction-time availability before using it as a target or feature).")
        issues.append("Potential target leakage cannot be determined from column names alone; inspect event timing and label construction before modeling.")
    if dataset == "olist":
        issues.append("Delivery timestamps and review fields may occur after purchase; exclude them from any prediction made before those events.")
    if dataset == "online_retail_ii":
        issues.append("This is transaction/demand data; it does not establish inventory levels or stockout labels.")
    if not issues:
        issues.append("No dataset-specific leakage claim inferred; verify feature availability at the intended prediction time and label definitions.")
    return dataset, reports, members + ["LIMITATIONS: " + x for x in issues]


def markdown_report(path: Path, dataset: str, reports: list[dict[str, Any]], members: list[str]) -> str:
    lines = [f"# Dataset audit: {dataset}", "", f"Archive: `{path.name}`", "", "## Archive files", ""]
    for entry in members:
        lines.append(f"- {entry}")
    lines += ["", "## Tables and sheets", ""]
    for report in reports:
        lines += [f"### {report['name']}", "", f"- Rows: {report['rows']:,}", f"- Duplicate rows: {report['duplicate_rows']:,}", "- Columns:"]
        lines.append("  | Column | Dtype | Missing % |")
        lines.append("  |---|---|---:|")
        for column in report["columns"]:
            lines.append(f"  | `{column['name']}` | `{column['dtype']}` | {column['missing_percent']:.4f}% |")
        lines.append("- Date coverage:")
        lines.extend([f"  - {x}" for x in report["date_coverage"]] or ["  - No date-like columns with parseable values detected."])
        lines.append("- ID uniqueness:")
        lines.extend([f"  - {x}" for x in report["id_uniqueness"]] or ["  - No ID-like columns detected by name."])
        lines.append("- Candidate label columns (name-based; not validated targets): " + (", ".join(f"`{x}`" for x in report["candidate_labels"]) or "none detected"))
        lines.append("")
    limitations = [x.removeprefix("LIMITATIONS: ") for x in members if x.startswith("LIMITATIONS: ")]
    lines += ["## Suspected leakage / limitations", ""]
    lines.extend(f"- {x}" for x in limitations)
    lines += ["", "This report describes observed archive contents only. Candidate labels and limitations require domain and prediction-time review.", ""]
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archives", nargs="*", type=Path, help="Optional archive paths; defaults to ZIP files under root")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    archives = [p.resolve() for p in args.archives] if args.archives else sorted(root.rglob("*.zip"))
    output_dir = root / "docs" / "audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in archives:
        if not path.is_file():
            raise FileNotFoundError(path)
        dataset, reports, members = audit_archive(path)
        destination = output_dir / f"{dataset}.md"
        destination.write_text(markdown_report(path, dataset, reports, members), encoding="utf-8")
        print(json.dumps({"dataset": dataset, "archive": str(path), "report": str(destination), "tables": len(reports), "rows": sum(item["rows"] for item in reports)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
