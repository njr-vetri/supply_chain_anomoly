"""Compatibility facade. Archive parsing is implemented by ``src.adapters``."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator
import pandas as pd

from src.adapters.base import get_adapter


SUPPORTED_PROFILES = ("olist", "dataco", "online_retail_ii")


def find_archive(dataset: str, root: Path | str) -> Path:
    root_path = Path(root)
    candidates = sorted(set(root_path.glob("*.zip")) | set((root_path / "data" / "raw").rglob("*.zip")))
    adapter = get_adapter(dataset)
    found = [path for path in candidates if adapter.detect(path)]
    if len(found) != 1:
        raise FileNotFoundError(f"Expected one {dataset} archive under {root_path}; found {len(found)}")
    return found[0]


def load_dataset(dataset: str, path: Path | str, chunksize: int = 50_000) -> Iterator[tuple[str, pd.DataFrame]]:
    yield from get_adapter(dataset).read_chunks(path, chunksize)


# Backward-compatible function names; no source parsing logic remains here.
def load_olist(path: Path | str, chunksize: int = 50_000):
    yield from load_dataset("olist", path, chunksize)


def load_dataco(path: Path | str, chunksize: int = 50_000):
    yield from load_dataset("dataco", path, chunksize)


def load_online_retail_ii(path: Path | str, chunksize: int = 50_000):
    yield from load_dataset("online_retail_ii", path, chunksize)
