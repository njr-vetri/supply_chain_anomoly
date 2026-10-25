"""DataCo source adapter. Field mapping is loaded from config/profiles/dataco.yaml."""
from pathlib import Path

from src.adapters.base import ZipCsvAdapter


class Adapter(ZipCsvAdapter):
    member_markers = ("datacosupplychaindataset.csv",)

    def accept_member(self, name: str) -> bool:
        return Path(name).name.lower() == "datacosupplychaindataset.csv"
