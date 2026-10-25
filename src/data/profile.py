"""Dataset profile schema and capability detection for generic dataset onboarding."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


CANONICAL_ROLES: set[str] = {
    "order_id",
    "order_ts",
    "promised_ts",
    "delivered_ts",
    "supplier_id",
    "product_id",
    "carrier",
    "quantity",
    "price",
        "status",
    "post_outcome",
    "region",
    "route",
    "event_id",
    "event_timestamp",
    "order_line_id",
    "shipment_id",
    "supplier_name",
    "product_name",
    "warehouse_id",
    "warehouse_name",
    "snapshot_id",
    "observation_id",
    "carrier_id",
    "customer_id",
    "destination",
}

TIMESTAMP_ROLES: set[str] = {"order_ts", "promised_ts", "delivered_ts", "event_timestamp"}


class TaskCapability(BaseModel):
    """Feasibility of an analytics or modeling task based on mapped roles."""
    model_config = ConfigDict(extra="forbid")
    task: str
    possible: bool
    missing_roles: list[str] = Field(default_factory=list)
    reason: str = ""


class DatasetCapabilities(BaseModel):
    """Collection of task capabilities for a confirmed profile."""
    model_config = ConfigDict(extra="forbid")
    anomaly_detection: TaskCapability
    delay_prediction: TaskCapability
    demand_forecasting: TaskCapability
    graph: TaskCapability


class DatasetProfile(BaseModel):
    """YAML-serializable dataset profile mapping source columns to canonical roles."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(default="1.0", max_length=32)
    description: str = Field(default="", max_length=1000)
    source_file: str = Field(default="", max_length=256)
    source_archive_sha256: str = Field(default="", max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mappings: dict[str, str] = Field(description="Map source_column -> canonical_role")
    custom_fields: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    time_zone: str | None = Field(default=None, max_length=100)
    date_format: str | None = Field(default=None, max_length=100)
    capabilities: DatasetCapabilities | None = None

    @field_validator("mappings")
    @classmethod
    def validate_mappings(cls, mappings: dict[str, str]) -> dict[str, str]:
        if not mappings:
            raise ValueError("Mappings dictionary cannot be empty")
        
        # Check all target roles are canonical
        invalid_roles = set(mappings.values()) - CANONICAL_ROLES
        if invalid_roles:
            raise ValueError(
                f"Invalid canonical roles: {sorted(invalid_roles)}. "
                f"Allowed roles: {sorted(CANONICAL_ROLES)}"
            )

        # An order or event identifier is required for source record provenance.
        primary_entity_roles = {"order_id", "event_id", "shipment_id", "supplier_id", "product_id", "warehouse_id"}
        if not set(mappings.values()).intersection(primary_entity_roles):
            raise ValueError("Mappings must include an 'order_id' or entity role")

        # Check at least one timestamp role for transaction / event tables
        if any(r in mappings.values() for r in ("order_id", "event_id", "shipment_id", "quantity", "price")):
            if not any(ts in mappings.values() for ts in TIMESTAMP_ROLES):
                raise ValueError(
                    f"Mappings must include at least one timestamp role ({sorted(TIMESTAMP_ROLES)})"
                )

        return mappings

    def save(self, profile_dir: Path | str = "config/profiles") -> Path:
        """Save this profile as a YAML document under profile_dir."""
        target_dir = Path(profile_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{self.name}.yaml"
        data = self.model_dump(mode="json")
        with target_path.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)
        return target_path

    @classmethod
    def load(cls, name_or_path: Path | str, profile_dir: Path | str = "config/profiles") -> DatasetProfile:
        """Load a profile from a name or explicit path."""
        path = Path(name_or_path)
        if not path.is_file():
            path = Path(profile_dir) / f"{path.stem}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Profile not found at {path}")
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        return cls.model_validate(data)


def detect_capabilities(mappings: dict[str, str]) -> DatasetCapabilities:
    """Analyze confirmed mappings to detect possible and blocked analytical tasks."""
    roles = set(mappings.values())

    # 1. Anomaly Detection:
    # Requires order_id and at least one metric/timeline (quantity, price, or timestamp)
    anomaly_missing: list[str] = []
    if "order_id" not in roles:
        anomaly_missing.append("order_id")
    has_metric_or_time = bool(roles & {"quantity", "price", "order_ts", "delivered_ts", "promised_ts"})
    if not has_metric_or_time:
        anomaly_missing.append("quantity or price or timestamp")
    anomaly_possible = len(anomaly_missing) == 0
    anomaly_cap = TaskCapability(
        task="anomaly_detection",
        possible=anomaly_possible,
        missing_roles=anomaly_missing,
        reason="Order ID and metric/timeline values present" if anomaly_possible else f"Missing required role(s): {anomaly_missing}",
    )

    # 2. Delay Prediction:
    # Requires order_id, promised_ts, and either delivered_ts or status
    delay_missing: list[str] = []
    if "order_id" not in roles:
        delay_missing.append("order_id")
    if "promised_ts" not in roles:
        delay_missing.append("promised_ts")
    if "delivered_ts" not in roles and "status" not in roles:
        delay_missing.append("delivered_ts (or status)")
    delay_possible = len(delay_missing) == 0
    delay_cap = TaskCapability(
        task="delay_prediction",
        possible=delay_possible,
        missing_roles=delay_missing,
        reason="Promised timestamp and delivery outcome present" if delay_possible else f"Missing required role(s): {delay_missing}",
    )

    # 3. Demand Forecasting:
    # Requires product_id, quantity, and a timestamp (order_ts or delivered_ts)
    demand_missing: list[str] = []
    if "product_id" not in roles:
        demand_missing.append("product_id")
    if "quantity" not in roles:
        demand_missing.append("quantity")
    if not any(ts in roles for ts in TIMESTAMP_ROLES):
        demand_missing.append("order_ts or delivered_ts")
    demand_possible = len(demand_missing) == 0
    demand_cap = TaskCapability(
        task="demand_forecasting",
        possible=demand_possible,
        missing_roles=demand_missing,
        reason="Product ID, order quantity, and timestamps present" if demand_possible else f"Missing required role(s): {demand_missing}",
    )

    # 4. Graph Construction:
    # Requires order_id and at least one relational entity (supplier_id, product_id, or carrier)
    graph_missing: list[str] = []
    if "order_id" not in roles:
        graph_missing.append("order_id")
    has_relational = bool(roles & {"supplier_id", "product_id", "carrier"})
    if not has_relational:
        graph_missing.append("supplier_id, product_id, or carrier")
    graph_possible = len(graph_missing) == 0
    graph_cap = TaskCapability(
        task="graph",
        possible=graph_possible,
        missing_roles=graph_missing,
        reason="Order ID and network entity present" if graph_possible else f"Missing required role(s): {graph_missing}",
    )

    return DatasetCapabilities(
        anomaly_detection=anomaly_cap,
        delay_prediction=delay_cap,
        demand_forecasting=demand_cap,
        graph=graph_cap,
    )
