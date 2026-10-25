"""Run source-separated detectors and write anomaly evidence records."""

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.config import load_settings
from src.data.features.dataco import build_dataco_shipping_features
from src.data.features.olist import build_olist_delivery_features
from src.data.features.online_retail_ii import build_product_week_demand
from src.data.loaders import find_archive, load_dataco, load_olist, load_online_retail_ii
from src.ml.anomaly.isolation_forest import detect as isolation_detect
from src.ml.anomaly.rule_based import detect as rule_detect
from src.ml.anomaly.statistical import iqr, robust_zscore


def _detectors(values: pd.Series, threshold: float, settings: Any) -> dict[str, pd.DataFrame]:
    return {
        "rule": rule_detect(values, threshold),
        "robust_zscore": robust_zscore(values, settings.robust_z_threshold),
        "iqr": iqr(values, settings.iqr_multiplier),
    }


def _add_isolation(results: dict[str, pd.DataFrame], values: pd.Series, settings: Any) -> str | None:
    try:
        results["isolation_forest"] = isolation_detect(values, settings.isolation_forest_contamination,
                                                       settings.isolation_forest_estimators, settings.random_seed)
        return None
    except RuntimeError as exc:
        return str(exc)


def _evidence(dataset: str, record_ids: pd.Series, feature: str, result: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for index, row in result.loc[result["anomaly"]].iterrows():
        rows.append({"dataset": dataset, "detector": row["detector"], "feature": feature,
                     "evidence_ref": str(record_ids.loc[index]), "observed_value": row["observed_value"],
                     "baseline": row["baseline"], "anomaly_score": row["anomaly_score"]})
    return rows


def run_dataset(dataset: str, archive: Path, settings: Any) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    evidence: list[dict[str, Any]] = []
    statuses: list[str] = []
    detector_counts: dict[str, int] = {}
    if dataset == "olist":
        tables: dict[str, pd.DataFrame] = {}
        for name, chunk in load_olist(archive, chunksize=settings_data_chunk_size(settings)):
            table = Path(name).stem
            tables.setdefault(table, pd.DataFrame())
            tables[table] = pd.concat([tables[table], chunk], ignore_index=True)
        orders = tables.get("olist_orders_dataset", pd.DataFrame())
        items = tables.get("olist_order_items_dataset", pd.DataFrame())
        if orders.empty:
            raise ValueError("Olist orders table missing")
        features = build_olist_delivery_features(orders, items)
        record_ids = features["order_id"].astype(str)
        fields = {"actual_delivery_days": settings.anomaly.rule_thresholds["olist_delivery_days"],
                  "delivery_deviation_days": settings.anomaly.rule_thresholds["olist_delivery_days"]}
    elif dataset == "dataco":
        chunks = [frame for _, frame in load_dataco(archive, chunksize=settings_data_chunk_size(settings))]
        raw = pd.concat(chunks, ignore_index=True)
        features = build_dataco_shipping_features(raw)
        record_column = "Order Item Id" if "Order Item Id" in raw else "Order Id"
        record_ids = raw[record_column].astype(str)
        features.index = raw.index
        fields = {"scheduled_shipping_days": settings.anomaly.rule_thresholds["dataco_scheduled_days"],
                  "observed_actual_shipping_days": settings.anomaly.rule_thresholds["dataco_scheduled_days"]}
    else:
        sheets = list(load_online_retail_ii(archive))
        all_results = []
        # Each workbook sheet remains independently labelled and source-separated.
        for sheet_name, frame in sheets:
            weekly = build_product_week_demand(frame)
            record_ids = weekly["StockCode"].astype(str) + "@" + weekly["week"].astype(str)
            fields = {"weekly_quantity": settings.anomaly.rule_thresholds["online_retail_weekly_quantity"]}
            for feature, threshold in fields.items():
                methods = _detectors(weekly[feature], threshold, settings.anomaly)
                status = _add_isolation(methods, weekly[feature], settings.anomaly)
                if status:
                    statuses.append(status)
                for name, result in methods.items():
                    detector_counts[name] = detector_counts.get(name, 0) + int(result["anomaly"].sum())
                    rows = _evidence(dataset, record_ids, feature, result)
                    for row in rows:
                        row["source_sheet"] = sheet_name
                    all_results.extend(rows)
        return all_results, detector_counts, statuses
    for feature, threshold in fields.items():
        if feature not in features:
            continue
        methods = _detectors(features[feature], threshold, settings.anomaly)
        status = _add_isolation(methods, features[feature], settings.anomaly)
        if status:
            statuses.append(status)
        for name, result in methods.items():
            detector_counts[name] = detector_counts.get(name, 0) + int(result["anomaly"].sum())
            evidence.extend(_evidence(dataset, record_ids, feature, result))
    return evidence, detector_counts, statuses


def settings_data_chunk_size(settings: Any) -> int:
    return settings.data.csv_chunk_rows


def run(root: Path | str, output_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(root)
    settings = load_settings()
    output = Path(output_root) if output_root else root / "data" / "processed" / "anomalies"
    output.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, Any] = {}
    for dataset in ("olist", "dataco", "online_retail_ii"):
        archive = find_archive(dataset, root)
        try:
            rows, counts, statuses = run_dataset(dataset, archive, settings)
            target = output / f"{dataset}_anomalies.jsonl"
            with target.open("w", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, default=str) + "\n")
            summaries[dataset] = {"flagged_counts_by_detector": counts, "evidence_rows": len(rows),
                                  "status": statuses, "output": str(target)}
            print(json.dumps({"dataset": dataset, **summaries[dataset]}))
        except (ImportError, ModuleNotFoundError) as exc:
            summaries[dataset] = {"status": [str(exc)], "flagged_counts_by_detector": {}}
            print(json.dumps({"dataset": dataset, **summaries[dataset]}))
    settings_path = output / "settings_used.json"
    settings_path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run(args.root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
