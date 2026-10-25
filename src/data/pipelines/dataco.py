"""Independent DataCo pipeline; access logs are excluded by its loader."""
from pathlib import Path
from src.data.loaders import load_dataco
from src.data.pipelines.common import run_pipeline

def run(archive: Path | str, output_root: Path | str = "data/processed") -> list[Path]:
    return run_pipeline("dataco", archive, output_root, load_dataco, required_columns=["Order Id", "order date (DateOrders)"],
                        date_columns=["order date (DateOrders)", "shipping date (DateOrders)"])
