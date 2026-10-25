"""Investigate anomalies/predictions using only rows read from audited source archives."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib

import pandas as pd

from src.core.schemas import Evidence, HypothesisStatus, Incident
from src.data.loaders import find_archive, load_dataco, load_olist, load_online_retail_ii
from src.risk.hypotheses import HypothesisCase, LedgerEvidence


SAFE_FIELDS = {
    "olist": ["order_id", "order_status", "order_purchase_timestamp", "order_estimated_delivery_date",
              "order_delivered_customer_date", "order_delivered_carrier_date"],
    "dataco": ["Order Item Id", "Order Id", "Days for shipment (scheduled)", "Days for shipping (real)",
               "Late_delivery_risk", "Delivery Status", "order date (DateOrders)", "shipping date (DateOrders)", "Shipping Mode"],
    "online_retail_ii": ["Invoice", "StockCode", "InvoiceDate", "Quantity", "Price"],
}


def _find_record(dataset: str, archive: Path, record_ref: str) -> tuple[str, pd.Series] | None:
    if dataset == "olist":
        for name, chunk in load_olist(archive):
            if Path(name).stem != "olist_orders_dataset":
                continue
            found = chunk.loc[chunk["order_id"].astype(str) == record_ref]
            if not found.empty:
                return name, found.iloc[0]
    elif dataset == "dataco":
        for name, chunk in load_dataco(archive):
            column = "Order Item Id" if "Order Item Id" in chunk else "Order Id"
            found = chunk.loc[chunk[column].astype(str) == record_ref]
            if not found.empty:
                return name, found.iloc[0]
    elif dataset == "online_retail_ii":
        stock, _, week = record_ref.partition("@")
        for name, frame in load_online_retail_ii(archive):
            frame["InvoiceDate"] = pd.to_datetime(frame["InvoiceDate"], errors="coerce", format="mixed")
            target_week = pd.Timestamp(week)
            observed_week = frame["InvoiceDate"].dt.to_period("W").dt.start_time
            found = frame.loc[(frame["StockCode"].astype(str) == stock) & (observed_week == target_week)]
            if not found.empty:
                row = found.iloc[0].copy()
                row["weekly_quantity"] = pd.to_numeric(found["Quantity"], errors="coerce").sum()
                row["__record_refs"] = [f"{invoice}:{stock}" for invoice in found["Invoice"].astype(str).tolist()]
                return name, row
    return None


def _observed_feature(dataset: str, feature: str, row: pd.Series) -> Any:
    """Derive the named monitored value from source fields; unknown features fail closed."""
    if dataset == "olist":
        purchase = pd.to_datetime(row.get("order_purchase_timestamp"), errors="coerce", utc=True)
        delivered = pd.to_datetime(row.get("order_delivered_customer_date"), errors="coerce", utc=True)
        estimated = pd.to_datetime(row.get("order_estimated_delivery_date"), errors="coerce", utc=True)
        if feature == "actual_delivery_days" and pd.notna(purchase) and pd.notna(delivered):
            return (delivered - purchase).total_seconds() / 86400
        if feature == "delivery_deviation_days" and pd.notna(purchase) and pd.notna(delivered) and pd.notna(estimated):
            return (delivered - estimated).total_seconds() / 86400
    if dataset == "dataco":
        mappings = {"scheduled_shipping_days": "Days for shipment (scheduled)",
                    "observed_actual_shipping_days": "Days for shipping (real)",
                    "observed_late_delivery_risk": "Late_delivery_risk"}
        column = mappings.get(feature)
        if column:
            return row.get(column)
    if dataset == "online_retail_ii" and feature == "weekly_quantity":
        return row.get("Quantity")
    return None


def investigate(item: dict[str, Any], *, root: Path | str) -> dict[str, Any]:
    """Return source-verified facts, separate hypotheses, alternatives, and limitations."""
    dataset = str(item.get("dataset", ""))
    if dataset not in SAFE_FIELDS:
        return {"status": "Insufficient evidence", "reason": "Unknown dataset source"}
    prediction = item.get("prediction")
    prediction_data = prediction if isinstance(prediction, dict) else None
    prediction_refs = prediction_data.get("record_refs", []) if prediction_data else []
    record_ref = str(item.get("evidence_ref") or item.get("record_ref") or
                     (prediction_refs[0] if prediction_refs else ""))
    if not record_ref:
        return {"status": "Insufficient evidence", "reason": "No source record reference was provided"}
    try:
        archive = find_archive(dataset, root)
    except (FileNotFoundError, ValueError) as exc:
        return {"status": "Insufficient evidence", "reason": str(exc)}
    found = _find_record(dataset, archive, record_ref)
    if found is None:
        return {"status": "Insufficient evidence", "reason": "Referenced record was not found in the audited source archive"}
    member, row = found
    source_refs = row.get("__record_refs", [record_ref])
    if not isinstance(source_refs, list):
        source_refs = [record_ref]
    feature = str(item.get("feature", ""))
    if not feature and prediction_data:
        target = str(prediction_data.get("target", "")).lower()
        feature = {"delay": "actual_delivery_days" if dataset == "olist" else "observed_late_delivery_risk",
                   "late_delivery_risk": "observed_late_delivery_risk",
                   "quantity": "weekly_quantity"}.get(target, "")
    observed = _observed_feature(dataset, feature, row)
    if observed is None or pd.isna(observed):
        return {"status": "Insufficient evidence", "reason": "The requested feature could not be verified from audited source fields"}
    claimed = item.get("observed_value")
    try:
        matches = abs(float(observed) - float(claimed)) <= 1e-6
    except (TypeError, ValueError):
        matches = str(observed) == str(claimed)
    if claimed is not None and not matches:
        return {"status": "Insufficient evidence", "reason": "Provided observed value does not match the audited source record"}
    values = {field: row[field] for field in SAFE_FIELDS[dataset] if field in row.index and pd.notna(row[field])}
    facts = {key: (value.isoformat() if isinstance(value, (datetime, pd.Timestamp)) else value.item() if hasattr(value, "item") else value)
             for key, value in values.items()}
    facts[feature] = float(observed) if isinstance(observed, (int, float)) else str(observed)
    digest = hashlib.sha256(repr(sorted((key, str(value)) for key, value in facts.items())).encode()).hexdigest()
    evidence = Evidence(evidence_type="audited_source_record", source=dataset, record_refs=source_refs,
                        observed_at=datetime.now(timezone.utc), facts=facts, content_hash=digest)
    occurred_value = row.get("order_purchase_timestamp", row.get("order date (DateOrders)", row.get("InvoiceDate")))
    occurred = pd.to_datetime(occurred_value, errors="coerce", utc=True) if occurred_value is not None else pd.NaT
    occurred_at = occurred.to_pydatetime() if pd.notna(occurred) else datetime.now(timezone.utc)
    incident = Incident(title=f"Observed {feature} anomaly", description="Source record verified; interpretation remains unconfirmed.",
                        source=dataset, record_refs=source_refs, occurred_at=occurred_at, evidence_refs=[evidence.id])
    supporting = LedgerEvidence(classification="supporting", source=dataset, record_refs=source_refs,
                               observed_at=evidence.observed_at, strength=0.5,
                               description=f"Observed {feature} value {observed} in audited member {member}.")
    primary = HypothesisCase(statement=f"The observed {feature} deviation reflects an operational delay condition.", source=dataset)
    primary.ledger.add(supporting)
    primary.ledger.missing.append("Independent corroboration and mechanism evidence are not established by this record alone.")
    alternatives = [
        HypothesisCase(statement="The deviation may reflect data quality, date parsing, or a recording discrepancy.", source=dataset),
        HypothesisCase(statement="The deviation may be explained by normal variation or a context-specific schedule.", source=dataset),
    ]
    limitations = ["One source record is insufficient to establish root cause.",
                   "SHAP note: feature contribution, not proven cause. A model prediction is not proof of cause.",
                   "Dataset license and source semantics remain subject to the project register."]
    if pd.isna(occurred):
        limitations.append("No source event timestamp was available; incident time is investigation time.")
    if prediction is not None:
        limitations.append("The supplied prediction is retained as a prediction reference, not treated as observed fact.")
    return {"status": "evidence_found", "incident": incident.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"), "hypothesis": primary.model_dump(mode="json"),
            "alternatives": [alternative.model_dump(mode="json") for alternative in alternatives],
            "prediction": prediction_data, "limitations": limitations,
            "lifecycle_status": HypothesisStatus.UNVERIFIED.value}
