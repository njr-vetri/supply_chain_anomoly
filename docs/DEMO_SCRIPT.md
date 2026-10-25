# End-to-End Demonstration Script

This walkthrough script demonstrates the complete 10-step risk monitoring and response lifecycle of the Autonomous, Transparent Supply-Chain Risk Monitoring & Response System using both the **React Frontend Dashboard** (`http://localhost:5173`) and **PowerShell / FastAPI REST API** (`http://127.0.0.1:8000`).

---

## Preparation

1. **Launch Services**:
   - Terminal 1 (API): `.\scripts\dev.ps1 run-api`
   - Terminal 2 (UI): `.\scripts\dev.ps1 run-ui`
2. **Access Dashboard**: Open `http://localhost:5173` in a web browser.
3. **Configure Authentication**: Enter API key `stage10-reviewer` and Company ID `acme_industrial`.

---

## 10-Step Lifecycle Walkthrough

### Step 1: Unfamiliar Company Data Ingestion
- **Concept**: Ingest unfamiliar CSV files with custom column names without altering raw storage.
- **UI Action**:
  1. Navigate to **Data Sources** > **Upload** tab.
  2. Upload `acme_purchase_orders.csv`, `acme_freight_shipments.csv`, and `acme_vendor_directory.csv` from `data/synthetic_company/`.
  3. Observe computed SHA-256 digests and row ingestion progress.
- **API Equivalent**:
  ```powershell
  $headers = @{ "X-API-Key" = "stage10-reviewer"; "X-Company-Id" = "acme_industrial" }
  Invoke-RestMethod -Method Post -Headers $headers -Uri "http://127.0.0.1:8000/api/v1/datasets/upload" `
    -InFile "data/synthetic_company/acme_purchase_orders.csv" -ContentType "text/csv"
  ```

### Step 2: Schema Mapping Wizard & Suggestions
- **Concept**: Heuristic mapping suggestions provide reasons and confidence scores; suggestions are never auto-confirmed.
- **UI Action**:
  1. In **Data Sources**, click the **Mapping wizard** tab and select `acme_purchase_orders`.
  2. Inspect candidate mappings (e.g. `po_num` -> `order_id`, `supplier_code` -> `supplier_id`).
  3. Note confidence scores and reason explanations.
  4. Enter reviewer rationale: *"Accepted canonical purchase order mapping"* and click **Accept mapping**.

### Step 3: Cross-Source Entity Relationships
- **Concept**: Discover and review joins across separate source tables while detecting orphaned keys.
- **UI Action**:
  1. Click the **Relationships** tab in **Data Sources**.
  2. Review the join between `acme_orders.po_num` and `acme_shipments.po_num`.
  3. Inspect matched record counts and orphaned order counts.
  4. Click **Approve Relationship**.

### Step 4: Capability Checklist & Gating
- **Concept**: Capabilities unlock dynamically based only on approved canonical mappings.
- **UI Action**:
  1. Click the **Capabilities** tab.
  2. Verify:
     - `anomaly_detection`: **AVAILABLE_WITH_LIMITATIONS** (price & quantity mapped).
     - `demand_analysis`: **AVAILABLE** (product, quantity, order_ts mapped).
     - `inventory_risk`: **UNSUPPORTED** (no inventory snapshot table present).
     - `dependency_graph`: **AVAILABLE_WITH_LIMITATIONS**.

### Step 5: Quality Validation & Drift Monitoring
- **Concept**: Track null rates and schema shifts; drift generates advisory warnings, never automatic retraining.
- **UI Action**:
  1. Navigate to the **Monitoring** screen.
  2. Inspect the Quality Snapshot card: 0% null rates across critical keys.
  3. Inspect Schema & Data Drift: Status reports `WITHIN_CONFIGURED_LIMITS` or `DRIFT_ALERT` with warning badge.

### Step 6: Anomaly Detection & Incident Assembly
- **Concept**: Detect statistical outliers (IQR / Robust Z) and cluster correlated anomalies into an incident.
- **UI Action**:
  1. Navigate to **Incidents** screen.
  2. Select incident: *"Acme Supplier Price Spike & Delay Incident"*.
  3. Inspect linked anomalies (e.g. PO-00042 price spike detected via IQR).
  4. Review the **Missing Evidence Checklist** highlighting corroborated carrier logs.

### Step 7: Hypothesis Ledger & Reviewer Confirmation
- **Concept**: Strict status progression: `UNVERIFIED` -> `SUPPORTED` -> `CONFIRMED`. Only reviewers can confirm.
- **UI Action**:
  1. Inside the Incident details, view the active hypothesis: *"Supplier component shortage"*.
  2. Notice that confirming without supporting evidence is blocked (409 Conflict).
  3. Attach corroborated evidence (freight congestion manifest, strength 0.92).
  4. Status transitions to `SUPPORTED`.
  5. With `reviewer` role active, enter review notes and click **Confirm Hypothesis**.
  6. Status updates to `CONFIRMED` with full review history provenance.

### Step 8: Supply-Chain Dependency Graph & Exposure Tracing
- **Concept**: Bounded graph navigation for upstream and downstream blast-radius analysis.
- **UI Action**:
  1. Navigate to **Supply Graph** screen.
  2. Inspect interactive Cytoscape node-edge diagram (Suppliers -> Products -> Purchase Orders).
  3. Click node `supplier:V-100` and trigger **Trace Downstream Exposure**.
  4. Highlight dependent purchase orders and delivery hubs.

### Step 9: Recommendation Playbooks & What-If Simulations
- **Concept**: Evaluate operational mitigations under explicitly labelled hypothetical assumptions.
- **UI Action**:
  1. Navigate to **Recommendations** screen.
  2. Select recommendation: *"Perform Vendor SLA Capacity Audit"*.
  3. Launch **What-If Simulation**: Adjust relative delay reduction slider (e.g. 25% reduction).
  4. Verify the permanent yellow banner: **HYPOTHETICAL SIMULATION — Assumptions require physical confirmation**.

### Step 10: Guarded Actions, Emergency Kill Switch & Cryptographic Audit
- **Concept**: Dry-run by default, reviewer approval requirement, instant emergency kill switch, and tamper-evident audit.
- **UI Action**:
  1. Click **Request Approval** for high-impact action.
  2. Reviewer signs off on the mitigation.
  3. Execute action: Confirm execution is flagged `dry_run: true`.
  4. Navigate to **Settings** / **Admin**: Toggle **Emergency Kill Switch** ON.
  5. Attempt a subsequent mitigation: Action is immediately blocked with status `BLOCKED_KILL_SWITCH`.
  6. Navigate to **Audit Trail** screen: Inspect cryptographic SHA-256 hash chaining verifying sequential log integrity.
