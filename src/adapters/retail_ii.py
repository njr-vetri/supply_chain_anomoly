"""Online Retail II adapter; workbook sheets remain source-separated."""
from io import BytesIO
from pathlib import Path
from typing import Iterator
import zipfile

import pandas as pd

from src.adapters.base import SourceAdapter


class Adapter(SourceAdapter):
    def detect(self, path: Path | str) -> bool:
        try:
            with zipfile.ZipFile(path) as archive:
                return any(Path(name).name.lower() == "online_retail_ii.xlsx" for name in archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return False

    def read_chunks(self, path: Path | str, chunksize: int = 50_000) -> Iterator[tuple[str, pd.DataFrame]]:
        del chunksize  # Excel sheets are returned as individual frames by pandas.
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if Path(name).name.lower() == "online_retail_ii.xlsx":
                    sheets = pd.read_excel(BytesIO(archive.read(name)), sheet_name=None)
                    for sheet_name, frame in sheets.items():
                        member = f"{name} [{sheet_name}]"
                        frame.attrs["source_member"] = member
                        frame.attrs["source_row_offset"] = 0
                        yield member, frame
                    return
        raise FileNotFoundError("Retail II workbook not found in archive")
