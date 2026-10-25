# Kaveri Foods sample dataset (SYNTHETIC)

SYNTHETIC test data generated for software testing. Not real company data.
It must never be used to claim real-world model accuracy.
Column names are deliberately different from Olist, DataCo and Online Retail II.
Date range: 2024-01-01 to 2025-12-31. Company: fictional "Kaveri Foods".

## Main files (upload these as one project)
purchase_orders.csv  one row per purchase order
  po_number, vendor_code, sku, qty_ordered, unit_cost, po_date, promised_arrival, warehouse_code
shipments.csv        one row per shipment (links to purchase_orders by po_number)
  shipment_ref, po_number, carrier_name, route, ship_date, arrival_date,
  days_late (arrival_date minus promised_arrival, in days), delivery_status
vendors.csv          one row per vendor
  vendor_code, vendor_name, country, tier
sales.csv            daily units sold per SKU (there is NO inventory data)
  sale_date, sku, units_sold

## Extra format and behaviour tests (extra_tests/)
purchase_orders_2026_batch2.csv  a later batch of orders with a changed column layout (schema change test)
vendors.xlsx                     same vendors as an Excel file, with a second non-data sheet called "notes"
multi_table.zip                  a ZIP holding three tables (purchase_orders, shipments, vendors)
company_b_orders.json            a second, unrelated company in JSON with different field names (isolation test)
