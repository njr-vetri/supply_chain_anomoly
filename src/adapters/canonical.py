"""Canonical Pydantic records and corresponding Arrow/Parquet schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CanonicalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    event_timestamp: datetime
    source: str | None = None
    source_record_ref: str | None = None
    order_id: str | None = None
    product_id: str | None = None
    supplier_id: str | None = None
    warehouse_id: str | None = None
    customer_id: str | None = None
    destination: str | None = None
    region: str | None = None
    mode: str | None = None
    carrier: str | None = None
    quantity: float | None = None
    price: float | None = None
    status: str | None = None
    post_outcome: int | None = None
    promised_timestamp: datetime | None = None
    delivered_timestamp: datetime | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CanonicalOrder(CanonicalRecord):
    pass


class CanonicalOrderLine(CanonicalRecord):
    order_line_id: str | None = None


class CanonicalShipment(CanonicalRecord):
    shipment_id: str | None = None


class CanonicalSupplier(CanonicalRecord):
    supplier_name: str | None = None


class CanonicalProduct(CanonicalRecord):
    product_name: str | None = None


class CanonicalWarehouse(CanonicalRecord):
    warehouse_name: str | None = None


class CanonicalInventorySnapshot(CanonicalRecord):
    snapshot_id: str | None = None


class CanonicalDemandObservation(CanonicalRecord):
    observation_id: str | None = None


class CanonicalCarrier(CanonicalRecord):
    carrier_id: str | None = None


class CanonicalCustomerDestination(CanonicalRecord):
    pass


CANONICAL_TYPES = {
    "orders": CanonicalOrder, "order_lines": CanonicalOrderLine, "shipments": CanonicalShipment,
    "suppliers": CanonicalSupplier, "products": CanonicalProduct, "warehouses": CanonicalWarehouse,
    "inventory_snapshots": CanonicalInventorySnapshot, "demand_observations": CanonicalDemandObservation,
    "carriers": CanonicalCarrier, "customers_destinations": CanonicalCustomerDestination,
}


def parquet_schemas():
    """Build matching Arrow schemas. Import pyarrow lazily so non-Parquet paths remain usable."""
    import pyarrow as pa

    shared = [pa.field("event_id", pa.string(), nullable=False),
              pa.field("event_timestamp", pa.timestamp("us", tz="UTC"), nullable=False)]
    optional = [pa.field(name, pa.string()) for name in (
        "source", "source_record_ref", "order_id", "product_id", "supplier_id", "warehouse_id",
        "customer_id", "destination", "region", "mode", "carrier", "status")]
    optional += [pa.field("quantity", pa.float64()), pa.field("price", pa.float64()),
                 pa.field("post_outcome", pa.int8()),
                 pa.field("promised_timestamp", pa.timestamp("us", tz="UTC")),
                 pa.field("delivered_timestamp", pa.timestamp("us", tz="UTC")),
                 pa.field("custom_fields", pa.map_(pa.string(), pa.string()))]
    optional += [pa.field(name, pa.string()) for name in (
        "order_line_id", "shipment_id", "supplier_name", "product_name", "warehouse_name",
        "snapshot_id", "observation_id", "carrier_id")]
    common_schema = pa.schema(shared + optional)
    return {name: common_schema for name in CANONICAL_TYPES}
