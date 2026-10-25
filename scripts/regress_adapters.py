"""Compare real adapter validation row counts to the Phase 8 recorded baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.adapters.base import get_adapter
from src.data.validation import validate_frame


BASELINES = {
    "olist": {"input": 1_550_922, "quarantined": 258_816, "valid": 1_292_106},
    "dataco": {"input": 180_519, "quarantined": 0, "valid": 180_519},
    "online_retail_ii": {"input": 1_067_371, "quarantined": 12_133, "valid": 1_055_238},
}


def _required(dataset: str, member: str) -> list[str]:
    stem = Path(member.split(" [")[0]).stem.lower()
    return {
        "olist": {"olist_orders_dataset": ["order_id", "order_purchase_timestamp"],
                  "olist_order_items_dataset": ["order_id", "order_item_id"]},
        "dataco": {"datacosupplychaindataset": ["Order Item Id", "Late_delivery_risk",
                                                    "order date (DateOrders)"]},
        "online_retail_ii": {"online_retail_ii": ["StockCode", "InvoiceDate", "Quantity"]},
    }[dataset].get(stem, [])


def audit_dataset(root: Path, dataset: str, chunksize: int = 50_000) -> dict:
    adapter = get_adapter(dataset, root / "config" / "profiles")
    candidates = sorted(set(root.glob("*.zip")) | set((root / "data" / "raw").rglob("*.zip")))
    matches = [candidate for candidate in candidates if adapter.detect(candidate)]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one {dataset} archive, found {len(matches)}")
    totals = {"input": 0, "quarantined": 0, "valid": 0, "members": 0}
    for member, frame in adapter.read_chunks(matches[0], chunksize):
        date_columns = [column for column in frame.columns
                        if "date" in str(column).lower() or "timestamp" in str(column).lower()]
        valid, quarantined, _ = validate_frame(frame, source=f"{dataset}:{member}",
            required_columns=_required(dataset, member), date_columns=date_columns)
        totals["input"] += len(frame)
        totals["valid"] += len(valid)
        totals["quarantined"] += len(quarantined)
        totals["members"] += 1
    totals["archive"] = matches[0].name
    totals["baseline"] = BASELINES[dataset]
    totals["matches_baseline"] = all(totals[key] == BASELINES[dataset][key]
                                      for key in ("input", "quarantined", "valid"))
    return totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--chunksize", type=int, default=50_000)
    args = parser.parse_args()
    results = {}
    for name in BASELINES:
        print(f"Auditing {name} through its saved source adapter...", flush=True)
        results[name] = audit_dataset(args.root.resolve(), name, args.chunksize)
        print(json.dumps({name: results[name]}), flush=True)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
