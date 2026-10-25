"""Generic read-only ZIP adapters; dataset mappings are loaded from YAML profiles."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator
import zipfile

import pandas as pd

from src.data.profile import DatasetProfile


class SourceAdapter(ABC):
    """Common source contract. Raw ZIP members are streamed/read in memory only."""

    def __init__(self, profile: DatasetProfile):
        self.profile = profile

    @abstractmethod
    def detect(self, path: Path | str) -> bool:
        """Return whether this adapter recognizes the archive contents."""

    @abstractmethod
    def read_chunks(self, path: Path | str, chunksize: int = 50_000) -> Iterator[tuple[str, pd.DataFrame]]:
        """Yield original member names and source-shaped data frames."""

    def to_canonical(self, frame: pd.DataFrame, mapping: dict[str, str] | None = None) -> pd.DataFrame:
        """Map known columns and retain every unmapped source value in custom_fields."""
        column_map = mapping or self.profile.mappings
        aliases = {"order_ts": "event_timestamp", "promised_ts": "promised_timestamp",
                   "delivered_ts": "delivered_timestamp"}
        result = pd.DataFrame(index=frame.index)
        for source_column, canonical_column in column_map.items():
            if source_column in frame.columns:
                canonical_name = aliases.get(canonical_column, canonical_column)
                result[canonical_name] = frame[source_column]
        # event_id is an explicit source identifier when available, otherwise a source-row locator.
        result["event_id"] = result.get("order_id", pd.Series(frame.index.map(str), index=frame.index)).astype(str)
        if "event_timestamp" not in result:
            fallback = next((name for name in ("delivered_timestamp", "promised_timestamp") if name in result), None)
            result["event_timestamp"] = result[fallback] if fallback else pd.NaT
        mapped = set(column_map)
        result["custom_fields"] = frame.apply(
            lambda row: {str(k): _json_value(v) for k, v in row.items() if k not in mapped}, axis=1
        )
        member = str(frame.attrs.get("source_member", "source-frame"))
        offset = int(frame.attrs.get("source_row_offset", 0))
        result["source"] = self.profile.name
        result["source_record_ref"] = [f"{member}:{offset + i}" for i in range(len(frame))]
        result["event_id"] = result["order_id"].fillna(result["source_record_ref"]).astype(str)
        return result.reset_index(drop=True)


def _json_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


class ZipCsvAdapter(SourceAdapter):
    member_markers: tuple[str, ...] = ()

    def detect(self, path: Path | str) -> bool:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [name.lower() for name in archive.namelist()]
            return any(any(marker in name for marker in self.member_markers) for name in names)
        except (OSError, zipfile.BadZipFile):
            return False

    def read_chunks(self, path: Path | str, chunksize: int = 50_000) -> Iterator[tuple[str, pd.DataFrame]]:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if self.accept_member(name):
                    with archive.open(name) as stream:
                        try:
                            reader = pd.read_csv(stream, chunksize=chunksize, low_memory=False)
                            offset = 0
                            for frame in reader:
                                frame.attrs["source_member"] = name
                                frame.attrs["source_row_offset"] = offset
                                offset += len(frame)
                                yield name, frame
                        except UnicodeDecodeError:
                            stream.seek(0)
                            reader = pd.read_csv(stream, chunksize=chunksize, encoding="latin-1", low_memory=False)
                            offset = 0
                            for frame in reader:
                                frame.attrs["source_member"] = name
                                frame.attrs["source_row_offset"] = offset
                                offset += len(frame)
                                yield name, frame

    @abstractmethod
    def accept_member(self, name: str) -> bool:
        raise NotImplementedError


def get_adapter(dataset: str, profile_dir: Path | str = "config/profiles") -> SourceAdapter:
    """Return an adapter using its reviewed, saved source-to-canonical profile."""
    adapter_modules = {"olist": "olist", "dataco": "dataco", "online_retail_ii": "retail_ii"}
    if dataset not in adapter_modules:
        raise ValueError(f"No adapter registered for profile '{dataset}'")
    from importlib import import_module
    module = import_module(f"src.adapters.{adapter_modules[dataset]}")
    adapter_type = module.Adapter
    profiles = Path(profile_dir)
    if not (profiles / f"{dataset}.yaml").is_file() and (Path("config/profiles") / f"{dataset}.yaml").is_file():
        profiles = Path("config/profiles")
    return adapter_type(DatasetProfile.load(dataset, profile_dir=profiles))
