"""Independent transaction demand pipeline; no inventory/stockout inference."""
from pathlib import Path
from src.data.loaders import load_online_retail_ii
from src.data.pipelines.common import run_pipeline

def run(archive: Path | str, output_root: Path | str = "data/processed") -> list[Path]:
    # The workbook loader takes no chunksize; adapter keeps common pipeline interface.
    def loader(path: Path, chunksize: int = 50000):
        del chunksize
        return load_online_retail_ii(path)
    return run_pipeline("online_retail_ii", archive, output_root, loader,
                        required_columns=["Invoice", "InvoiceDate", "Quantity"], date_columns=["InvoiceDate"])
