# Acceptance Test Results: Synthetic Kaveri Foods & Multi-Tenant Verification

**Execution Date**: 2026-10-24  
**Dataset**: Synthetic Kaveri Foods (`tests/fixtures/synthetic/kaveri_foods/`) & Competitor Corp  
**Test Suite**: `tests/test_e2e_acceptance_unseen.py`  
**Execution Status**: PASSED (Exit Code: 0, 0 Failures)  
**Machine Context**: CPU-only, 16 GB RAM  
**Provenance**: Derived strictly from live execution output persisted in [`docs/acceptance_findings.json`](file:///c:/Projects/supply-chain-risk-system/docs/acceptance_findings.json).

---

## 1. Capability Assessment Statuses

All capabilities are assessed dynamically based on mapped canonical roles and confirmed graph relationships:

| Capability / Feature | Status | Mapped Roles / Gating | Limitations / Required Extra Data |
| :--- | :--- | :--- | :--- |
| **`delay_prediction`** | `AVAILABLE_WITH_LIMITATIONS` | `order_id`, `event_timestamp`, `promised_timestamp`, `delivered_timestamp` | Mapped roles indicate potential capability; post-outcome columns are screened to prevent leakage; not proof of delay cause. |
| **`dependency_graph`** | `AVAILABLE` | Approved relationships between POs, Shipments, and Vendors | Capped at configured clustering thresholds; individual transaction nodes are aggregated into supply network entities. |
| **`anomaly_detection`** | `AVAILABLE_WITH_LIMITATIONS` | Dated event records, numeric measures (`quantity`, `price`) | An anomaly is an unusual statistical value, not direct proof of operational severity or root cause. |
| **`demand_analysis`** | `AVAILABLE` | `product_id`, `quantity`, `event_timestamp` | Demand pressure only; inventory snapshots and stockout labels are not inferred. |
| **`model_evaluation`** | `AVAILABLE_WITH_LIMITATIONS` | Mapped delay prediction roles | Evaluated against chronological train/test split with dummy/rule baselines. |
| **`inventory_risk`** | `UNSUPPORTED` | Missing: `inventory_snapshot`, `on_hand_quantity`, `warehouse_id` | Requires snapshot tables with timestamped on-hand balances per SKU and warehouse. |

---

## 2. Data-Quality Report & Planted Fault Counts

All data quality counts were computed generically by canonical role across the project sources without hardcoded column names:

| Issue Type / Category | Count | Source Dataset(s) | Description / Quarantine Behavior |
| :--- | :---: | :--- | :--- |
| **Exact Duplicate Rows** | **30** | `purchase_orders` (30) | Full row deduplication across mapped canonical fields. |
| **Negative Values** | **18** | `purchase_orders` (18 in quantity/price) | Flagged for non-negative business measure roles. |
| **Invalid Dates** | **15** | `purchase_orders` (15) | Malformed ISO timestamps; safely quarantined to `.quarantine.jsonl`. |
| **Blank Required Values** | **40** | `purchase_orders` (40 blank promised dates) | Nulls in required timestamp/key roles. |
| **Unknown Foreign Keys** | **10** | `purchase_orders` -> `vendors` (10 POs) | PO records referencing vendor codes not present in the vendor directory. |
| **Orphan Rows** | **25** | `shipments` without matching PO (25) | Shipment records with order IDs missing from purchase orders. |
| **Open Records** | **150** | `shipments` (150) | In-flight shipments with no `delivered_timestamp` recorded. |
| **Extreme Outliers** | **50** | `purchase_orders` (43), `sales` (7) | Values exceeding 5 standard deviations from median / robust IQR envelope. |
| **Quarantined Rows** | **15** | `purchase_orders` (15) | Tracked separately from clean pipeline records; retained with audit provenance. |

---

## 3. Top Anomalies (Top 10 Detected)

Anomalies detected across canonical measures (quantity, price, volume) using IQR, Robust Z-score, and Isolation Forest baselines:

1. **PO #6014 (`V014`)**: Quantity = `250` (Baseline: `98.5`, Expected Range: `[-45.1, 249.9]`, Method: `iqr`, Severity: `LOW`)
2. **PO #4904 (`V014`)**: Quantity = `250` (Baseline: `98.5`, Expected Range: `[-39.1, 239.9]`, Method: `iqr`, Severity: `LOW`)
3. **PO #4876 (`V014`)**: Quantity = `-67` (Baseline: `99.0`, Expected Range: `[-37.9, 239.1]`, Method: `isolation_forest`, Severity: `LOW`)
4. **PO #4876 (`V014`)**: Quantity = `-67` (Baseline: `99.0`, Expected Range: `[-37.9, 239.1]`, Method: `iqr`, Severity: `LOW`)
5. **PO #4614 (`V014`)**: Quantity = `250` (Baseline: `100.0`, Expected Range: `[-37.5, 238.5]`, Method: `iqr`, Severity: `LOW`)
6. **PO #4461 (`V014`)**: Quantity = `250` (Baseline: `100.0`, Expected Range: `[-37.5, 238.5]`, Method: `iqr`, Severity: `LOW`)
7. **PO #4371 (`V014`)**: Quantity = `250` (Baseline: `100.0`, Expected Range: `[-37.5, 238.5]`, Method: `iqr`, Severity: `LOW`)
8. **PO #4321 (`V014`)**: Quantity = `250` (Baseline: `100.0`, Expected Range: `[-37.5, 238.5]`, Method: `iqr`, Severity: `LOW`)
9. **PO #4088 (`V014`)**: Quantity = `250` (Baseline: `100.0`, Expected Range: `[-37.5, 238.5]`, Method: `iqr`, Severity: `LOW`)
10. **PO #3981 (`V014`)**: Quantity = `-65` (Baseline: `100.0`, Expected Range: `[-37.5, 238.5]`, Method: `isolation_forest`, Severity: `LOW`)

*Total Canonical Anomalies Persisted*: 2,000 (capped for bounded operational ingestion).

---

## 4. Delay Prediction & Top 5 Ranked Delay Drivers

* **Baseline Delay Rate**: `14.39%` (overall system delay rate)
* **Model Split**: Strict chronological split (`train_end`: 2024-04-12, `test_start`: 2024-04-13)
* **Model Trained**: Balanced Logistic Regression with one-hot encoded categorical drivers and standard-scaled numeric features.

### Top 5 Ranked Drivers of Delay:
1. **`supplier_id: V017`**:
   * Delay Rate: **`31.00%`** (vs Baseline `14.39%`, Difference: **`+16.62%`**)
   * Sample Size: `687` orders
   * Estimated Start Date: **`2024-01-19T00:00:00+00:00`**
   * Status: `UNVERIFIED` (Requires reviewer confirmation)
2. **`product_id: SKU-1004`**:
   * Delay Rate: **`30.85%`** (vs Baseline `14.39%`, Difference: **`+16.46%`**)
   * Sample Size: `94` orders
   * Estimated Start Date: **`2024-02-19T00:00:00+00:00`**
   * Status: `UNVERIFIED`
3. **`product_id: SKU-1003`**:
   * Delay Rate: **`30.39%`** (vs Baseline `14.39%`, Difference: **`+16.01%`**)
   * Sample Size: `102` orders
   * Estimated Start Date: **`2024-01-12T00:00:00+00:00`**
   * Status: `UNVERIFIED`
4. **`product_id: SKU-1010`**:
   * Delay Rate: **`25.96%`** (vs Baseline `14.39%`, Difference: **`+11.57%`**)
   * Sample Size: `104` orders
   * Estimated Start Date: **`2024-03-18T00:00:00+00:00`**
   * Status: `UNVERIFIED`
5. **`product_id: SKU-1008`**:
   * Delay Rate: **`25.24%`** (vs Baseline `14.39%`, Difference: **`+10.86%`**)
   * Sample Size: `103` orders
   * Estimated Start Date: **`2024-05-16T00:00:00+00:00`**
   * Status: `UNVERIFIED`

---

## 5. Delay Model Leakage Handling

To eliminate target and temporal leakage, post-outcome fields were dynamically identified and blocked from feature matrices:

* **Blocked Columns**:
  * `delivered_timestamp`: Mapped to delivered time (temporal outcome leakage).
  * `status`: Outcome-style name indicating post-event outcome state.
  * `days_late`: Outcome-style name indicating delay magnitude.
  * `delivery_status`: Outcome-style name indicating delivery completion state.
* **Allowed Predictive Features**: `quantity`, `price`, `supplier_id`, `product_id`, `carrier`, `order_id`, `promised_timestamp`, `warehouse_id`.
* **Analyst Overrides**: Supported via `POST /api/v1/projects/{project_id}/leakage-overrides` with mandatory rationale and audit logging.

---

## 6. Supply-Chain Dependency Graph

* **Total Aggregated Nodes**: `103` (No hardcoded `ProcessStage` nodes)
* **Total Weighted Edges**: `489`
* **Node Counts by Type**:
  * `Supplier`: **`25`** (24 known vendors from `vendors.csv` + 1 unknown vendor code from `purchase_orders.csv`)
  * `Product`: **`60`**
  * `Carrier`: **`4`** (`FastLogistics`, `ExpressFreight`, `BlueLine`, `SwiftCargo`)
  * `Warehouse`: **`4`** (`WH-North`, `WH-South`, `WH-East`, `WH-Central`)
  * `Route/Lane`: **`5`** (Derived from canonical mapped `route` role)
  * `CustomerRegion`: **`5`** (`South`, `West`, `East`, `North`, `Central`)
* **Edge Counts by Relationship Type**:
  * `SUPPLIES`: **`129`** (Supplier supplies Product)
  * `USES`: **`100`** (Supplier uses Carrier via order-shipment join)
  * `SERVES`: **`20`** (Carrier serves Route/Lane)
  * `STORED_AT`: **`240`** (Product stored at Warehouse)
* **Top 10 Unhealthy Nodes by Z-Score (Peer Late Rate Baseline)**:
  1. `supplier:V017`: Late rate `14.98%` vs peer avg `6.12%` (+8.86%, z-score: **`3.76`**, `PROBLEM`) — Planted faulty supplier connected to products and carriers
  2. `product:SKU-1023`: Late rate `11.76%` vs peer avg `5.41%` (+6.36%, z-score: **`2.95`**, `PROBLEM`)
  3. `product:SKU-1059`: Late rate `11.62%` vs peer avg `5.41%` (+6.21%, z-score: **`2.88`**, `PROBLEM`)
  4. `route:West-3`: Late rate `8.97%` vs peer avg `7.01%` (+1.96%, z-score: **`1.80`**, `PROBLEM`)
  5. `carrier:BlueLine`: Late rate `9.37%` vs peer avg `6.79%` (+2.57%, z-score: **`1.73`**, `WATCH`)
  6. `product:SKU-1028`: Late rate `8.89%` vs peer avg `5.41%` (+3.48%, z-score: **`1.61`**, `WATCH`)
  7. `warehouse:WH-DEL`: Late rate `7.59%` vs peer avg `6.38%` (+1.21%, z-score: **`1.58`**, `WATCH`)
  8. `product:SKU-1042`: Late rate `8.47%` vs peer avg `5.41%` (+3.06%, z-score: **`1.42`**, `WATCH`)
  9. `product:SKU-1014`: Late rate `8.06%` vs peer avg `5.41%` (+2.66%, z-score: **`1.23`**, `WATCH`)
  10. `product:SKU-1038`: Late rate `8.00%` vs peer avg `5.41%` (+2.59%, z-score: **`1.20`**, `WATCH`)
* *All nodes at or below peer average evaluated to `HEALTHY`. Zero nodes labeled `UNHEALTHY` with negative z-score.*

---

## 7. Role-Based Access Control (RBAC) Verification

Exact status codes returned during negative and authorized role tests:

| Role | Operation / Endpoint | Allowed? | HTTP Status Code | Governance Rule Enforced |
| :--- | :--- | :---: | :---: | :--- |
| **Viewer** | `POST /api/v1/datasets/upload` | **No** | **403** | Read-only accounts cannot upload data. |
| **Viewer** | `PUT /api/v1/datasets/{name}/confirm-mapping` | **No** | **403** | Viewers cannot confirm column mappings. |
| **Viewer** | `POST /api/v1/projects/{id}/pipeline/run` | **No** | **403** | Viewers cannot execute machine learning pipelines. |
| **Viewer** | `POST /api/v1/hypotheses/{id}/confirm` | **No** | **403** | Only human reviewers can confirm root-cause hypotheses. |
| **Viewer** | `POST /api/v1/actions/{id}/approve` | **No** | **403** | Viewers cannot approve mitigation actions (returns strict 403, never 404). |
| **Viewer** | `POST /api/v1/auth/users` | **No** | **403** | Viewers cannot manage accounts. |
| **Analyst** | `POST /api/v1/hypotheses/{id}/confirm` | **No** | **403** | Analysts cannot confirm hypotheses (human reviewer gate). |
| **Analyst** | `POST /api/v1/actions/{id}/approve` | **No** | **403** | Analysts cannot approve actions (returns strict 403, never 404). |
| **Analyst** | `POST /api/v1/auth/users` | **No** | **403** | Analysts cannot manage user accounts. |
| **Analyst** | `POST /api/v1/system/kill-switch` | **No** | **403** | Analysts cannot toggle emergency kill switch. |
| **Reviewer**| `POST /api/v1/hypotheses/{id}/confirm` (unverified) | **No** | **409** | Enforces `UNVERIFIED -> SUPPORTED -> CONFIRMED` lifecycle ("Insufficient evidence"). |
| **Reviewer**| `POST /api/v1/hypotheses/{id}/confirm` (supported) | **Yes** | **200** | Human reviewer confirmed supported hypothesis. |
| **Reviewer**| `POST /api/v1/auth/users` | **No** | **403** | Reviewers cannot manage user accounts (admin gate). |
| **Reviewer**| `POST /api/v1/system/kill-switch` | **No** | **403** | Reviewers cannot toggle kill switch (admin gate). |
| **Admin**   | `GET /api/v1/auth/users` | **Yes** | **200** | Admin can list and manage users. |
| **Admin**   | `POST /api/v1/system/kill-switch` | **Yes** | **200** | Admin can activate/deactivate emergency kill switch. |

---

## 8. Multi-Tenant Isolation & Schema Drift

* **Multi-Tenant Isolation**:
  * Company A (`kaveri_foods`): `9` isolated dataset sources.
  * Company B (`competitor_corp`): `1` isolated dataset source (`company_b_orders`).
  * Cross-Company Access Attempt (Company A user token with `X-Company-Id: competitor_corp`): Returned **`403 Forbidden`**. No cross-company records leaked.
* **Schema Drift Reporting**:
  * Monitored Source: `purchase_orders`
  * Status: `DRIFT_ALERT` (Warning only; automatic model retraining is strictly disallowed).
  * Explicit Unit Annotations:
    * `row_count_change`: `fraction`
    * `null_rate_change`: `fraction (0.0 to 1.0)`
    * `numeric_mean_shift`: `baseline_standard_deviations (z-units)`
    * `category_concentration_change`: `fraction (0.0 to 1.0)`

---

## 9. Failed or Unsupported Steps

* **Failed Pipeline Steps**: None (`"failures": []`).
* **Unsupported Capabilities**: `inventory_risk` (`UNSUPPORTED` due to lack of inventory snapshot tables).
* **Quarantined Rows**: 15 purchase order rows quarantined due to unparseable timestamp formats.
* **Unverified Elements**: All top 5 delay drivers remain marked `UNVERIFIED` until explicitly reviewed and transitioned to `CONFIRMED` by a human reviewer.
