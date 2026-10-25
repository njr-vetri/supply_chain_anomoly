"""Shared pipeline mechanics, keeping each dataset's outputs in its own directory."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterator

import pandas as pd

from src.data.validation import validate_frame
from src.core.config import load_settings


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_pipeline(dataset: str, archive: Path | str, output_root: Path | str,
                 loader: Callable[..., Iterator[tuple[str, pd.DataFrame]]], *,
                 required_columns: list[str] | None = None, date_columns: list[str] | None = None,
                 chunksize: int | None = None) -> list[Path]:
    """Write valid rows, quarantined rows and lineage; raw archive is never written."""
    archive_path = Path(archive)
    settings = load_settings()
    actual_chunksize = chunksize or settings.data.csv_chunk_rows
    out = Path(output_root) / dataset
    out.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    lineage_items: list[dict[str, object]] = []
    for index, (member, frame) in enumerate(loader(archive_path, chunksize=actual_chunksize)):
        valid, quarantined, report = validate_frame(frame, source=f"{dataset}:{member}",
                                                     required_columns=required_columns, date_columns=date_columns,
                                                     freshness_max_age_hours=settings.data.freshness_max_age_hours,
                                                     max_null_fraction=settings.data.max_null_fraction)
        stem = Path(member.split(" [")[0]).stem
        valid_path = out / f"{stem}_{index}_valid.csv"
        quarantine_path = out / f"{stem}_{index}_quarantine.csv"
        quality_path = out / f"{stem}_{index}_quality.json"
        valid.to_csv(valid_path, index=False)
        quarantined.to_csv(quarantine_path, index=False)
        quality_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        outputs.extend([valid_path, quarantine_path, quality_path])
        lineage_items.append({"member": member, "rows_read": len(frame), "valid_rows": len(valid),
                              "quarantined_rows": len(quarantined), "outputs": [p.name for p in outputs[-3:]]})
    lineage = {"dataset": dataset, "source_archive": archive_path.name, "source_sha256": sha256_file(archive_path),
               "transform_steps": ["read member directly from ZIP", "validate required fields/dates/duplicates",
                                   "write valid and quarantined rows separately"],
               "created_at": datetime.now(timezone.utc).isoformat(), "members": lineage_items}
    lineage_path = out / "lineage.json"
    lineage_path.write_text(json.dumps(lineage, indent=2), encoding="utf-8")
    outputs.append(lineage_path)
    return outputs
