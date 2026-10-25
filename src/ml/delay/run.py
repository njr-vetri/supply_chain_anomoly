"""Run delay classifiers and separate UCI transaction-demand forecasting baselines."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.config import load_settings
from src.data.features.olist import build_olist_delivery_features
from src.data.features.dataco import build_dataco_shipping_features
from src.data.features.online_retail_ii import build_product_week_demand
from src.data.loaders import find_archive, load_dataco, load_olist, load_online_retail_ii
from src.ml.delay.evaluation import evaluate_classification
from src.ml.delay.forecasting import dense_product_weeks, rolling_origin_cv

DATACO_FORBIDDEN_PREDICTORS = {
    "Late_delivery_risk", "Delivery Status", "Days for shipping (real)",
    "shipping date (DateOrders)", "observed_actual_shipping_days", "observed_late_delivery_risk",
}


def derive_olist_delay_label(orders: pd.DataFrame) -> pd.Series:
    """Derive observed delivery lateness from the audited estimate and delivery timestamps."""
    delivered = pd.to_datetime(orders["order_delivered_customer_date"], errors="coerce", format="mixed", utc=True)
    estimated = pd.to_datetime(orders["order_estimated_delivery_date"], errors="coerce", format="mixed", utc=True)
    result = (delivered > estimated).astype("Int64")
    return result.mask(delivered.isna() | estimated.isna())


def derive_dataco_delay_label(frame: pd.DataFrame) -> pd.Series:
    """Use the dataset's audited Late_delivery_risk field as its recorded label."""
    if "Late_delivery_risk" not in frame:
        raise ValueError("DataCo Late_delivery_risk label column is missing")
    return pd.to_numeric(frame["Late_delivery_risk"], errors="coerce").astype("Int64")


DATACO_MODEL_FEATURES = ["scheduled_shipping_days", "shipping_mode", "order_weekday", "order_region"]

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_olist_frame(archive: Path, chunksize: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    tables: dict[str, list[pd.DataFrame]] = {}
    for name, chunk in load_olist(archive, chunksize=chunksize):
        table = Path(name).stem
        if table in {"olist_orders_dataset", "olist_order_items_dataset"}:
            tables.setdefault(table, []).append(chunk)
    return (pd.concat(tables["olist_orders_dataset"], ignore_index=True),
            pd.concat(tables["olist_order_items_dataset"], ignore_index=True))


def prepare_olist(archive: Path, config: dict[str, Any], models_dir: Path, registry: Path,
                  audit_log_path: Path | None = None) -> dict[str, Any]:
    orders, items = _load_olist_frame(archive, config["csv_chunk_rows"])
    frame = build_olist_delivery_features(orders, items)
    delivered = orders["order_status"].eq("delivered")
    frame["delay_label"] = derive_olist_delay_label(orders)
    eligible = delivered & frame["actual_delivery_days"].notna() & frame["estimated_transit_days"].notna()
    frame = frame.loc[eligible].copy()
    frame["delivery_buffer_days"] = frame["estimated_transit_days"] - frame["prior_seller_delivery_days_mean"]
    frame["purchase_year"] = frame["order_purchase_timestamp"].dt.year
    features = ["estimated_transit_days", "prior_seller_delivery_days_mean", "prior_seller_order_count", "delivery_buffer_days"]
    frame["order_purchase_timestamp"] = pd.to_datetime(frame["order_purchase_timestamp"], utc=True)
    return evaluate_classification("olist_delay", frame, label="delay_label", timestamp="order_purchase_timestamp",
        features=features, subgroup="purchase_year", archive_hash=sha256_file(archive),
        config={**config, "simple_rule_feature": "delivery_buffer_days", "simple_rule_threshold": 0},
        models_dir=models_dir, registry_path=registry, audit_log_path=audit_log_path)


def prepare_dataco(archive: Path, config: dict[str, Any], models_dir: Path, registry: Path,
                   audit_log_path: Path | None = None) -> dict[str, Any]:
    chunks = [frame for _, frame in load_dataco(archive, chunksize=config["csv_chunk_rows"])]
    raw = pd.concat(chunks, ignore_index=True)
    frame = build_dataco_shipping_features(raw)
    frame["delay_label"] = derive_dataco_delay_label(raw)
    frame["record_id"] = raw["Order Item Id"].astype(str)
    frame["order_region_group"] = frame.get("order_region", "UNKNOWN")
    frame["order_timestamp"] = pd.to_datetime(frame["order_timestamp"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["order_timestamp", "delay_label"])
    features = DATACO_MODEL_FEATURES.copy()
    return evaluate_classification("dataco_delay", frame, label="delay_label", timestamp="order_timestamp",
        features=features, subgroup="order_region_group", archive_hash=sha256_file(archive),
        config={**config, "simple_rule_feature": "scheduled_shipping_days",
                "simple_rule_threshold": config["rule_thresholds"]["dataco_scheduled_days_median"]},
        models_dir=models_dir, registry_path=registry, audit_log_path=audit_log_path)


def prepare_demand(archive: Path, config: dict[str, Any]) -> dict[str, Any]:
    sheets = list(load_online_retail_ii(archive))
    # Workbook years stay separately reported; they are not merged as if one continuous source.
    reports = {}
    for sheet, frame in sheets:
        weekly = build_product_week_demand(frame, lags=())
        panel = dense_product_weeks(weekly)
        reports[sheet] = rolling_origin_cv(panel, folds=config["forecasting"]["cv_folds"],
            horizon=config["forecasting"]["horizon_weeks"],
            moving_average_weeks=config["forecasting"]["moving_average_weeks"],
            seasonal_period_weeks=config["forecasting"]["seasonal_period_weeks"])
    return {"task": "demand forecasting", "not_stockout_prediction": True, "sheets": reports}


def run(root: Path, report_path: Path) -> dict[str, Any]:
    settings = load_settings()
    base = settings.model_dump()
    eval_config = {**base["evaluation"], "csv_chunk_rows": base["data"]["csv_chunk_rows"]}
    models_dir = root / "models"
    registry = root / "src" / "ml" / "model_registry.json"
    results = {"random_seed": eval_config["random_seed"], "classification": {}, "demand_forecasting": {},
               "limitations": []}
    for dataset, prepare in (("olist", prepare_olist), ("dataco", prepare_dataco)):
        try:
            archive = find_archive(dataset, root)
            results["classification"][dataset] = prepare(archive, eval_config, models_dir, registry,
                                                         root / settings.audit.log_path)
        except (ImportError, ModuleNotFoundError) as exc:
            results["classification"][dataset] = {"status": f"NOT COMPUTED: dependency unavailable: {exc}"}
        except Exception as exc:
            results["classification"][dataset] = {"status": f"NOT COMPUTED: {type(exc).__name__}: {exc}"}
    try:
        archive = find_archive("online_retail_ii", root)
        results["demand_forecasting"] = prepare_demand(archive, eval_config)
    except Exception as exc:
        results["demand_forecasting"] = {"status": f"NOT COMPUTED: {type(exc).__name__}: {exc}",
                                          "task": "demand forecasting, not stockout prediction"}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    markdown_path = root / "docs" / "EVALUATION_REPORT.md"
    markdown_path.write_text(render_markdown(results), encoding="utf-8")
    return results


def render_markdown(results: dict[str, Any]) -> str:
    """Render only computed metrics and explicit not-computed reasons."""
    lines = ["# Evaluation report", "", "Only executed results are shown. No accuracy claim is made.", "",
             f"Fixed random seed: `{results.get('random_seed')}`", "", "## Delay classification", ""]
    for dataset, result in results.get("classification", {}).items():
        lines += [f"### {dataset}", ""]
        if "models" not in result:
            lines += [f"Not computed: {result.get('status', 'unknown reason')}", ""]
            continue
        split = result["split"]
        lines += [f"Chronological split: train {split['train_rows']:,}, validation {split['validation_rows']:,}, test {split['test_rows']:,}.", "",
                  "| Model | Test precision | Recall | F1 | PR-AUC | ROC-AUC | Brier |", "|---|---:|---:|---:|---:|---:|---:|"]
        for name, values in result["models"].items():
            metric = values["test"]
            lines.append(f"| {name} | {metric['precision']:.4f} | {metric['recall']:.4f} | {metric['f1']:.4f} | {metric['pr_auc']:.4f} | {metric['roc_auc']} | {metric['brier_score']:.4f} |")
        lines.append("")
    lines += ["## Demand forecasting", ""]
    demand = results.get("demand_forecasting", {})
    if "sheets" not in demand:
        lines.append(f"Not computed: {demand.get('status', 'unknown reason')}")
    else:
        lines.append("Online Retail II transaction demand forecast; not stockout prediction. Metric: MAE.")
        for sheet, report in demand["sheets"].items():
            lines += ["", f"### {sheet}", "", "| Baseline | Mean rolling-origin MAE | Status |", "|---|---:|---|"]
            for model in ("naive", "moving_average", "seasonal_naive"):
                if model in report and isinstance(report[model], dict):
                    mae_val = report[model].get("mean_mae")
                    mae_str = f"{mae_val:.4f}" if mae_val is not None else "N/A"
                    status = "RUN" if mae_val is not None else "SKIPPED"
                    lines.append(f"| {model} | {mae_str} | {status} |")
            if report.get("baselines_skipped"):
                lines += ["", "Skipped baselines:"]
                for skipped in report["baselines_skipped"]:
                    lines.append(f"- **{skipped['name']}**: {skipped['reason']}")
            if report.get("cv_adapted"):
                lines.append(f"- *CV adapted*: folds={report.get('adapted_folds')} (configured {report.get('configured_folds')}), horizon={report.get('adapted_horizon')} (configured {report.get('configured_horizon')})")
    lines += ["", "## Limitations", "",
              "DataCo target construction is not independently verified; leakage-prone outcome fields are excluded by documented feature allowlist.",
              "Olist labels require observed delivery and estimated dates, so undelivered/canceled records are excluded.",
              "Retail II contains transactions only; no inventory or stockout labels are available.",
              "Metrics are omitted for any dataset/model run that could not execute in the active environment.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = run(args.root, args.report or args.root / "docs" / "EVALUATION_REPORT.json")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
