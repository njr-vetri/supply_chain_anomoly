"""
Stage 10: Real dataset pipeline and validation execution.
Runs the three real datasets (Olist, DataCo, UCI Online Retail II) through the
canonical adapter & validation path in memory, measuring exact runtimes and reporting
real row counts. Never deletes, moves, or extracts dataset archives.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.adapters.base import get_adapter
from src.data.validation import validate_frame


DATASETS = {
    "olist": {
        "archive_pattern": "archive (1).zip",
        "required_columns": {
            "olist_orders_dataset": ["order_id", "order_purchase_timestamp"],
            "olist_order_items_dataset": ["order_id", "order_item_id"],
        },
    },
    "dataco": {
        "archive_pattern": "archive (2).zip",
        "required_columns": {
            "datacosupplychaindataset": ["Order Item Id", "Late_delivery_risk", "order date (DateOrders)"],
        },
    },
    "online_retail_ii": {
        "archive_pattern": "online+retail+ii.zip",
        "required_columns": {
            "online_retail_ii": ["StockCode", "InvoiceDate", "Quantity"],
        },
    },
}


def run_real_dataset(name: str, root: Path, chunksize: int = 50_000) -> dict:
    config = DATASETS[name]
    adapter = get_adapter(name, root / "config" / "profiles")
    candidates = sorted(set(root.glob("*.zip")) | set((root / "data" / "raw").rglob("*.zip")))
    matches = [c for c in candidates if adapter.detect(c)]
    if not matches:
        raise FileNotFoundError(f"Could not locate archive for dataset '{name}'")
    archive_path = matches[0]

    start_time = time.perf_counter()
    totals = {"input_rows": 0, "valid_rows": 0, "quarantined_rows": 0, "members_processed": 0}

    for member, frame in adapter.read_chunks(archive_path, chunksize):
        date_cols = [c for c in frame.columns if "date" in str(c).lower() or "timestamp" in str(c).lower()]
        stem = Path(member.split(" [")[0]).stem.lower()
        req_cols = config["required_columns"].get(stem, [])

        valid, quarantined, _ = validate_frame(
            frame,
            source=f"{name}:{member}",
            required_columns=req_cols,
            date_columns=date_cols,
        )
        totals["input_rows"] += len(frame)
        totals["valid_rows"] += len(valid)
        totals["quarantined_rows"] += len(quarantined)
        totals["members_processed"] += 1

    elapsed = time.perf_counter() - start_time
    totals["archive_filename"] = archive_path.name
    totals["elapsed_seconds"] = round(elapsed, 2)
    totals["status"] = "COMPLETED"
    return totals


def main() -> None:
    print("=" * 80)
    print("STAGE 10: REAL DATASETS IN-MEMORY VALIDATION & TIMING REPORT")
    print("=" * 80)
    root = Path.cwd()
    summary = {}

    for name in DATASETS:
        print(f"\nProcessing real dataset '{name}' in memory from archive...", flush=True)
        res = run_real_dataset(name, root)
        summary[name] = res
        print(f"  - Archive: {res['archive_filename']}")
        print(f"  - Input rows: {res['input_rows']:,}")
        print(f"  - Valid rows: {res['valid_rows']:,}")
        print(f"  - Quarantined rows: {res['quarantined_rows']:,}")
        print(f"  - Members processed: {res['members_processed']}")
        print(f"  - Wall-clock runtime: {res['elapsed_seconds']}s")

    print("\n" + "=" * 80)
    print("SUMMARY JSON:")
    print(json.dumps(summary, indent=2))
    print("=" * 80)


if __name__ == "__main__":
    main()
