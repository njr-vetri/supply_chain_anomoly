"""Olist source adapter. Field mapping is loaded from config/profiles/olist.yaml."""
from pathlib import Path

from src.adapters.base import ZipCsvAdapter


class Adapter(ZipCsvAdapter):
    member_markers = ("olist_", "product_category_name_translation.csv")

    def accept_member(self, name: str) -> bool:
        basename = Path(name).name.lower()
        return basename.endswith(".csv") and (basename.startswith("olist_") or
                                               basename == "product_category_name_translation.csv")
