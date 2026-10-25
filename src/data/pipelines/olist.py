"""Independent Olist data preparation pipeline."""
from pathlib import Path
from src.data.loaders import load_olist
from src.data.pipelines.common import run_pipeline

def run(archive: Path | str, output_root: Path | str = "data/processed") -> list[Path]:
    return run_pipeline("olist", archive, output_root, load_olist)
