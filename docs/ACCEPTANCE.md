# Acceptance Testing Specification (Scenarios 1 to 10)

This document specifies the acceptance criteria, automated test coverage, and manual/browser verification procedures for Scenarios 1 through 10 of the Autonomous, Transparent Supply-Chain Risk Monitoring & Response System.

---

## Summary Matrix

| Scenario | Title | Automated Test (`tests/test_stage10_scenarios.py`) | Manual / UI Verification Procedure | Status |
|---|---|---|---|---|
| **Scenario 1** | New Company Onboarding & Upload | `test_scenario_1_onboarding_and_upload` | Data Sources screen > Upload tab: file picker, SHA-256 display, background progress | Verified |
| **Scenario 2** | Schema Mapping Wizard & Suggestions | `test_scenario_2_schema_mapping_wizard` | Data Sources screen > Mapping wizard: review suggestions, set units, accept with reason | Verified |
| **Scenario 3** | Cross-Source Relationships & Orphan Detection | `test_scenario_3_cross_source_relationships` | Data Sources screen > Relationships tab: preview matched/orphan keys, approve proposal | Verified |
| **Scenario 4** | Capability Checklist & Gating | `test_scenario_4_capability_checklist_and_gating` | Data Sources screen > Capabilities tab: inspect available vs blocked features | Verified |
| **Scenario 5** | Quality Validation & Drift Monitoring | `test_scenario_5_quality_validation_and_drift_monitoring` | Monitoring screen: drift advisory banner, schema changes summary | Verified |
| **Scenario 6** | Anomaly Detection & ML Delay Prediction | `test_scenario_6_anomaly_detection_and_ml_prediction` | Predictions screen: prediction values, SHAP attribution, feature contributions | Verified |
| **Scenario 7** | Incident Assembly & Hypothesis Lifecycle | `test_scenario_7_incident_assembly_and_hypothesis_lifecycle` | Incidents screen > Investigation: view evidence, review hypothesis, reviewer confirm | Verified |
| **Scenario 8** | Supply Graph & Upstream/Downstream Tracing | `test_scenario_8_supply_chain_graph_and_tracing` | Supply-Chain Graph screen: Cytoscape canvas, node health, trace exposure | Verified |
| **Scenario 9** | Recommendation Playbooks & What-If Simulations | `test_scenario_9_recommendations_and_whatif` | Recommendations screen: what-if calculator, hypothetical scenario labels | Verified |
| **Scenario 10** | Guarded Actions, Approval Queue, Kill Switch & Audit | `test_scenario_10_guarded_actions_approval_killswitch_and_audit` | Approvals & Settings screens: approve request, dry-run action, kill switch toggle, audit trail | Verified |

---

## Scenario 1: New Company Onboarding & Dataset Upload

### Objective
Verify that an unfamiliar company can upload structured data files (CSV, XLSX, JSON, JSONL, or single-table ZIP) into tenant-isolated storage without modifying original raw bytes or extracting archives to disk.

### Automated Test
- **Function**: `test_scenario_1_onboarding_and_upload`
- **Assertions**:
  - `POST /api/v1/datasets/upload` accepts file stream with tenant header `X-Company-Id`.
  - Verifies exact SHA-256 calculation and status (`QUEUED` / `COMPLETED`).
  - Verifies viewer role receives `403 Forbidden` on upload.

### Manual / Browser Verification Steps
1. Navigate to `http://localhost:5173`.
2. Connect using API Key with `reviewer` role and Company ID `acme_industrial`.
3. In sidebar, click **Data Sources**, then click the **Upload** tab.
4. Drag and drop `acme_purchase_orders.csv` into the upload dropzone.
5. **Expected UI Result**:
   - The UI displays an active progress indicator.
   - Upon completion, the upload card displays the computed SHA-256 hash and processed row count.
   - Raw bytes remain unchanged in tenant storage.

---

## Scenario 2: Schema Mapping Wizard & Suggestions

### Objective
Ensure mapping suggestions provide confidence scores and explicit reasoning, strictly never auto-confirming, and requiring authenticated reviewer sign-off.

### Automated Test
- **Function**: `test_scenario_2_schema_mapping_wizard`
- **Assertions**:
  - `GET /api/v1/datasets/{name}/suggestions` returns suggestions with `auto_confirmed: False`.
  - Reviewer accepts version with mandatory `reason`; prior versions remain immutable.
  - Viewer role receives `403 Forbidden` on mapping modification.

### Manual / Browser Verification Steps
1. In **Data Sources**, click the **Mapping wizard** tab.
2. Select `acme_orders`.
3. Verify suggestion confidence badges and reasoning tooltips next to candidate canonical roles.
4. Notice the permanent disclaimer: *"Suggestions are never auto-confirmed."*
5. Fill in reviewer rationale and click **Accept mapping**.
6. **Expected UI Result**: Mapping status changes to `ACCEPTED` with audit provenance timestamp.

---

## Scenario 3: Cross-Source Relationships & Orphan Detection

### Objective
Verify multi-file join analysis accurately computes matched, orphan, and null-reference counts across independent files before establishing relationships.

### Automated Test
- **Function**: `test_scenario_3_cross_source_relationships`
- **Assertions**:
  - `POST /api/v1/datasets/relationships/preview` computes matched and orphan counts.
  - Generates proposal ID in pending state.
  - `POST /api/v1/datasets/relationships/{proposal_id}/approve` persists relationship record only after reviewer sign-off.

### Manual / Browser Verification Steps
1. In **Data Sources**, click the **Relationships** tab.
2. Select Left Source (`acme_orders`, key `po_num`) and Right Source (`acme_shipments`, key `po_num`).
3. Click **Preview join relationship**.
4. **Expected UI Result**:
   - Matched rows count and orphan rows count (e.g. 50 deliberate orphan shipments) are clearly itemized.
   - PENDING_APPROVAL chip is shown until approved.

---

## Scenario 4: Capability Checklist & Gating

### Objective
Assess available vs blocked analytical tasks based solely on accepted canonical mapping roles.

### Automated Test
- **Function**: `test_scenario_4_capability_checklist_and_gating`
- **Assertions**:
  - Sales data enables `demand_forecasting` and `delay_prediction`.
  - `inventory_risk` is explicitly marked `UNSUPPORTED` / `BLOCKED` with missing roles listed (`on_hand`, `warehouse_id`).

### Manual / Browser Verification Steps
1. In **Data Sources**, click the **Capabilities** tab.
2. **Expected UI Result**:
   - Green checkmarks appear next to `demand_forecasting`, `delay_prediction`, `anomaly_detection`.
   - Red warning badge appears next to `inventory_risk` stating *"Blocked: Missing roles [on_hand, warehouse]"*.
   - The system never pretends unmapped capabilities are operational.

---

## Scenario 5: Quality Validation & Drift Monitoring

### Objective
Validate incoming data quality and detect statistical drift between batches, ensuring drift serves as an advisory warning and never triggers automatic retraining.

### Automated Test
- **Function**: `test_scenario_5_quality_validation_and_drift_monitoring`
- **Assertions**:
  - Retyped columns and shifted distributions trigger `DRIFT_ALERT`.
  - Returns `drift_is_warning_only: True` and `triggers_automatic_retrain: False`.

### Manual / Browser Verification Steps
1. In the sidebar, click **Monitoring & Drift**.
2. Select source `acme_orders`.
3. **Expected UI Result**:
   - Amber warning banner renders: *"Drift is advisory, never an automatic retrain trigger."*
   - Table displays per-column null % shifts, mean shifts, and added columns.

---

## Scenario 6: Multi-Method Anomaly Detection & ML Delay Prediction

### Objective
Ensure anomalies are flagged using multiple statistical and unsupervised methods (IQR, Robust Z, Isolation Forest) and predictive models supply SHAP attribution labelled as feature contribution, not proven cause.

### Automated Test
- **Function**: `test_scenario_6_anomaly_detection_and_ml_prediction`
- **Assertions**:
  - IQR, Robust Z-score, and Isolation Forest flag injected outliers.
  - Outputs include detector metadata, baseline value, and observed score.

### Manual / Browser Verification Steps
1. In the sidebar, click **Predictions & Forecasts**.
2. Inspect prediction cards.
3. Click an order prediction to expand the explanation drawer.
4. **Expected UI Result**:
   - Delay probability is displayed with confidence interval.
   - SHAP waterfall chart displays feature contributions.
   - Prominent disclaimer: *"Feature contribution, not proven cause."*

---

## Scenario 7: Generic Incident Assembly & Hypothesis Lifecycle

### Objective
Group anomalies and predictions into traceable incidents, enforcing the strict lifecycle: `UNVERIFIED` -> `SUPPORTED` -> `CONFIRMED` (reviewer-only).

### Automated Test
- **Function**: `test_scenario_7_incident_assembly_and_hypothesis_lifecycle`
- **Assertions**:
  - `POST /api/v1/incidents/assemble` links anomalies and predictions.
  - Hypotheses start as `UNVERIFIED`.
  - Analyst cannot promote to `CONFIRMED` (rejected with 400/403).
  - Reviewer confirmation succeeds with written rationale.

### Manual / Browser Verification Steps
1. In the sidebar, click **Incidents & Investigations**.
2. Select the assembled incident.
3. Review the Evidence Ledger and Hypotheses list.
4. Attempt confirmation as `analyst` -> button is disabled.
5. Switch session role to `reviewer` -> Enter rationale and click **Confirm hypothesis**.
6. **Expected UI Result**: Status badge changes to `CONFIRMED` with reviewer username and timestamp.

---

## Scenario 8: Supply-Chain Dependency Graph & Tracing

### Objective
Visualize the multi-echelon network of suppliers, products, carriers, and orders, distinguishing `ESTABLISHED` edges from `INFERRED` edges, and tracing exposure paths.

### Automated Test
- **Function**: `test_scenario_8_supply_chain_graph_and_tracing`
- **Assertions**:
  - Graph query returns nodes and typed edges.
  - Downstream trace traverses only `ESTABLISHED` edges and returns order exposure counts.

### Manual / Browser Verification Steps
1. In the sidebar, click **Supply-Chain Graph**.
2. Enter Project ID `acme-proj-01`.
3. Inspect Cytoscape canvas:
   - Green nodes (Healthy), Amber nodes (At Risk), Red nodes (Incident).
   - Solid lines (`ESTABLISHED`), Dashed lines (`INFERRED`).
4. Click a Supplier node -> click **Trace downstream exposure**.
5. **Expected UI Result**: Downstream customer orders are highlighted in purple; exposure summary displays order count labelled *"downstream exposure, not proven cause"*.

---

## Scenario 9: Recommendation Playbooks & What-If Simulations

### Objective
Provide mitigation recommendations with explicit assumptions and constraints, allowing interactive what-if simulations labelled `HYPOTHETICAL`.

### Automated Test
- **Function**: `test_scenario_9_recommendations_and_whatif`
- **Assertions**:
  - What-if simulation requires explicit scenario assumptions.
  - Emitted results are flagged `HYPOTHETICAL`.
  - Uncomputed capacity and savings are explicitly withheld.

### Manual / Browser Verification Steps
1. In the sidebar, click **Recommendations**.
2. Select an active recommendation (e.g. *Vendor Capacity Reallocation*).
3. In the What-If Simulation panel, adjust the volume reallocation slider (e.g. 25%).
4. Click **Run simulation**.
5. **Expected UI Result**:
   - `HYPOTHETICAL` badge renders on all projected metrics.
   - Cost savings and vendor capacity are flagged as *"Not estimated"*.

---

## Scenario 10: Guarded Actions, Approval Queue, Kill Switch & Audit Chaining

### Objective
Enforce safety boundaries: dry-run default, approval requirement for high-impact actions, emergency kill switch halt, and cryptographic audit log chaining.

### Automated Test
- **Function**: `test_scenario_10_guarded_actions_approval_killswitch_and_audit`
- **Assertions**:
  - High-impact action without approval is rejected.
  - Reviewer approval allows action recording.
  - Action strictly executes as `DRY_RUN`.
  - Kill switch halts action execution.
  - Audit log maintains SHA-256 previous-hash linkage.

### Manual / Browser Verification Steps
1. In the sidebar, click **Settings**.
2. Under Emergency Controls, toggle **Global Kill Switch** to `ON`, providing reason *"Testing emergency halt"*.
3. Navigate to **Recommendations** and attempt to trigger an action -> Action is blocked with alert *"Kill switch is active"*.
4. Return to **Settings** and toggle Kill Switch to `OFF`.
5. Navigate to **Audit Trail** (admin role).
6. **Expected UI Result**: Table shows cryptographic chain of events (`KILL_SWITCH_TOGGLED`, `APPROVAL_CREATED`, `ACTION_RECORDED`), each with SHA-256 hash and previous hash.
