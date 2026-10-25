"""Versioned feature definitions and source-linked feature lineage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict


class FeatureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    description: str
    source_roles: list[str]
    transformation: str
    availability_rule: str


class FeatureLineage(BaseModel):
    feature_name: str
    feature_version: str
    value: Any
    source_records: list[str]
    transformation: str
    available_at: datetime
    source_available_at: datetime | None = None


DEFAULT_FEATURES = {
    "event_age_seconds": FeatureDefinition(name="event_age_seconds", version="1.0.0",
        description="Elapsed seconds between the event and feature computation.", source_roles=["event_timestamp"],
        transformation="feature_computed_at - event_timestamp", availability_rule="Available at computation time."),
    "gross_line_value": FeatureDefinition(name="gross_line_value", version="1.0.0",
        description="Quantity multiplied by unit price when both exist.", source_roles=["quantity", "price"],
        transformation="quantity * price", availability_rule="Available when source quantity and price are recorded."),
}


def derive_with_lineage(record: dict[str, Any], *, computed_at: datetime | None = None) -> list[FeatureLineage]:
    now = computed_at or datetime.now(timezone.utc)
    refs = [str(record.get("source_record_ref") or record.get("event_id"))]
    derived: list[FeatureLineage] = []
    event_time = record.get("event_timestamp")
    if event_time:
        parsed = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        derived.append(FeatureLineage(feature_name="event_age_seconds", feature_version="1.0.0",
            value=(now - parsed).total_seconds(), source_records=refs,
            transformation=DEFAULT_FEATURES["event_age_seconds"].transformation,
            available_at=now, source_available_at=parsed))
    quantity, price = record.get("quantity"), record.get("price")
    if quantity is not None and price is not None:
        source_available = parsed if event_time else now
        derived.append(FeatureLineage(feature_name="gross_line_value", feature_version="1.0.0",
            value=float(quantity) * float(price), source_records=refs,
            transformation=DEFAULT_FEATURES["gross_line_value"].transformation,
            available_at=now, source_available_at=source_available))
    return derived
