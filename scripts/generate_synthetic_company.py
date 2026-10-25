"""
Generates an unfamiliar multi-file synthetic company dataset for testing.
All records are SYNTHETIC. Never used to claim production accuracy or real data findings.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate_synthetic_company_data(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    # 1. Vendor directory (50 vendors)
    vendors_path = output_dir / "acme_vendor_directory.csv"
    vendor_ids = [f"VND-{i:03d}" for i in range(1, 51)]
    vendor_names = [f"Synthetic Vendor {i} Corp" for i in range(1, 51)]
    countries = ["US", "DE", "BR", "CN", "MX", "IN", "JP", "GB"]
    tiers = ["TIER_1", "TIER_2", "TIER_3"]

    with open(vendors_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["vendor_code", "vendor_legal_entity", "country_code", "tier_classification", "synthetic_label"])
        for vid, vname in zip(vendor_ids, vendor_names):
            writer.writerow([vid, vname, random.choice(countries), random.choice(tiers), "SYNTHETIC"])

    # 2. Purchase Orders (1000 orders)
    orders_path = output_dir / "acme_purchase_orders.csv"
    base_date = datetime(2025, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    skus = [f"SKU-{i:04d}" for i in range(1, 101)]
    regions = ["NorthAmerica-East", "NorthAmerica-West", "EMEA-Central", "LATAM-South", "APAC-East"]

    po_records = []
    with open(orders_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "po_num", "po_creation_time", "target_fulfillment_date",
            "supplier_code", "sku_id", "ordered_units", "extended_price_usd",
            "destination_hub", "synthetic_label"
        ])
        for i in range(1, 1001):
            po_num = f"PO-{i:05d}"
            created_dt = base_date + timedelta(hours=i * 2 + random.randint(0, 5))
            target_dt = created_dt + timedelta(days=random.randint(3, 10))
            vendor = random.choice(vendor_ids)
            sku = random.choice(skus)
            units = random.randint(1, 50)
            price = round(units * random.uniform(10.0, 250.0), 2)
            region = random.choice(regions)

            writer.writerow([
                po_num, created_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                target_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                vendor, sku, units, price, region, "SYNTHETIC"
            ])
            po_records.append((po_num, created_dt, target_dt))

    # 3. Freight Shipments (1000 shipments, 950 matching POs, 50 deliberate orphans)
    shipments_path = output_dir / "acme_freight_shipments.csv"
    carriers = ["AlphaExpress", "OmegaFreight", "GlobalTransit", "ApexLogistics"]
    statuses = ["DELIVERED", "DELIVERED", "DELIVERED", "IN_TRANSIT", "DELAYED"]

    with open(shipments_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "tracking_ref", "po_num", "departure_time", "delivered_time",
            "freight_carrier_name", "shipment_condition", "synthetic_label"
        ])
        for i in range(1, 1001):
            tracking_ref = f"TRK-{i:06d}"
            carrier = random.choice(carriers)

            if i <= 950:
                po_num, created_dt, target_dt = po_records[i - 1]
                depart_dt = created_dt + timedelta(days=random.randint(1, 2))
                # 85% on time, 15% delayed
                if random.random() < 0.85:
                    delivered_dt = target_dt - timedelta(hours=random.randint(2, 24))
                    status = "DELIVERED"
                else:
                    delivered_dt = target_dt + timedelta(days=random.randint(1, 5))
                    status = "DELAYED"
                delivered_str = delivered_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                # Deliberate orphan shipments (unknown PO)
                po_num = f"PO-ORPHAN-{i:05d}"
                depart_dt = base_date + timedelta(days=random.randint(10, 60))
                delivered_str = (depart_dt + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
                status = random.choice(statuses)

            writer.writerow([
                tracking_ref, po_num, depart_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                delivered_str, carrier, status, "SYNTHETIC"
            ])

    return {
        "vendors": vendors_path,
        "orders": orders_path,
        "shipments": shipments_path,
    }


if __name__ == "__main__":
    out = Path("data/synthetic_company")
    files = generate_synthetic_company_data(out)
    for k, v in files.items():
        print(f"Generated {k}: {v} ({v.stat().st_size} bytes)")
