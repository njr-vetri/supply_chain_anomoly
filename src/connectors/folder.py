"""Read-only scheduled folder connector; files are hashed and never rewritten."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
import zipfile

import pandas as pd

from src.connectors.base import ConnectorHealth, RecordBatch


class FolderImportConnector:
    def __init__(self, folder: Path | str, *, chunksize: int = 5000,
                 max_zip_entries: int = 1000, max_zip_bytes: int = 2_000_000_000,
                 max_compression_ratio: float = 100.0):
        if chunksize <= 0 or max_zip_entries <= 0 or max_zip_bytes <= 0 or max_compression_ratio <= 0:
            raise ValueError("Folder connector limits must be positive")
        self.folder = Path(folder)
        self.chunksize = chunksize
        self.max_zip_entries = max_zip_entries
        self.max_zip_bytes = max_zip_bytes
        self.max_compression_ratio = max_compression_ratio

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def health_check(self) -> ConnectorHealth:
        status = "HEALTHY" if self.folder.is_dir() and self.folder.exists() else "UNAVAILABLE"
        detail = "input folder is readable" if status == "HEALTHY" else "input folder is not available"
        return ConnectorHealth("scheduled_folder", status, datetime.now(timezone.utc).isoformat(), detail)

    def _records(self, path: Path) -> Iterator[tuple[str, list[dict[str, Any]]]]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            for frame in pd.read_csv(path, chunksize=self.chunksize, low_memory=False):
                yield str(path), frame.where(pd.notna(frame), None).to_dict(orient="records")
        elif suffix in {".jsonl", ".ndjson"}:
            for frame in pd.read_json(path, lines=True, chunksize=self.chunksize):
                yield str(path), frame.where(pd.notna(frame), None).to_dict(orient="records")
        elif suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else [data]
            for offset in range(0, len(rows), self.chunksize):
                yield str(path), [dict(row) for row in rows[offset:offset + self.chunksize]
                                  if isinstance(row, dict)]
        elif suffix == ".xlsx":
            frame = pd.read_excel(path)
            yield str(path), frame.where(pd.notna(frame), None).to_dict(orient="records")
        elif suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                infos = [info for info in archive.infolist() if not info.is_dir()]
                if len(infos) > self.max_zip_entries or sum(i.file_size for i in infos) > self.max_zip_bytes:
                    raise ValueError("ZIP member limits exceeded")
                for info in infos:
                    normalized = info.filename.replace("\\", "/")
                    if normalized.startswith("/") or Path(normalized).is_absolute() or ".." in Path(normalized).parts:
                        raise ValueError("Unsafe ZIP member path")
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > self.max_compression_ratio:
                        raise ValueError("ZIP compression ratio limit exceeded")
                    if Path(normalized).suffix.lower() != ".csv":
                        continue
                    with archive.open(info) as stream:
                        for frame in pd.read_csv(stream, chunksize=self.chunksize, low_memory=False):
                            yield f"{path}!{info.filename}", frame.where(pd.notna(frame), None).to_dict(orient="records")

    def read_batches(self):
        if not self.folder.is_dir():
            return
        for path in sorted(self.folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".jsonl", ".ndjson", ".xlsx", ".zip"}:
                continue
            digest = self._hash(path)
            for source_ref, records in self._records(path):
                yield RecordBatch("scheduled_folder", source_ref, digest, records)
