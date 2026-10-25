# What's New: Company-Independent Upgrade (Stages 1 to Current)

This document provides a comprehensive technical reference for the company-independent upgrade of the Autonomous Supply-Chain Risk System. It details every capability, where it lives in the codebase, how to use it via API or UI, known operational limitations, and verified test evidence.

---

## 1. Data Onboarding

### File Upload & Streamed Hashing

- **Description**: Streams incoming tabular data files directly to company-scoped immutable storage and verifies integrity via SHA-256. Files are never modified or normalized in place, and oversized payloads are rejected before job creation.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/importer.py`, `api/main.py` (`POST /api/v1/datasets/upload`), UI: **Data Sources** -> *Upload & Register File*.
- **How to use it**:
  1. Open **Data Sources** in the dashboard sidebar.
  2. In the upload card, select a supported tabular file (CSV, TSV, JSON, JSONL, XLSX, or single-table ZIP).
  3. Submit the file; receive an asynchronous `import_job_id` and verified SHA-256 checksum.
  4. Alternatively, send a multipart `POST` to `/api/v1/datasets/upload` with header `X-API-Key` (minimum role: `reviewer`).
- **Limitations & data needs**: Max size is 50 MB (`52,428,800` bytes). ZIP archives must contain exactly one supported tabular file without directory nesting.
- **Evidence**: `tests/test_onboarding_stage2.py::test_dataset_upload_stream_and_sha256`.

### In-Memory Streaming Profiler

- **Description**: Inspects tabular datasets in chunked streams to compute statistical profiles and column types without persisting raw sample rows. It derives row counts, null rates, cardinality, and numerical min/max while keeping raw records private.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/profiler.py`, `api/main.py` (`GET /api/v1/imports/{job_id}`), UI: **Data Sources** -> *File Profile & Summary*.
- **How to use it**:
  1. Upload a dataset file to trigger background profiling.
  2. Poll `GET /api/v1/imports/{job_id}` until status is `COMPLETED`.
  3. View the generated profile in the **Data Sources** table view.
- **Limitations & data needs**: Processes up to 10,000 rows per chunk. Profiles contain aggregate summary statistics only; individual data values are not retained in storage.
- **Evidence**: `tests/test_profiler.py`, `tests/test_profile_regression.py`.

### Schema Mapping Suggestions

- **Description**: Analyzes profiled column headers and statistical patterns to recommend mappings to canonical supply-chain roles. Confidence scores accompany each suggestion, and automatic confirmation is strictly prohibited.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/schema_mapper.py`, `api/main.py` (`GET /api/v1/datasets/{dataset_name}/suggestions`), UI: **Data Sources** -> *Mapping Wizard*.
- **How to use it**:
  1. Open **Data Sources** and select a registered dataset.
  2. Click **Mapping Wizard** to view detected column names beside suggested canonical roles.
  3. Review the confidence scores and heuristics for each recommendation.
  4. Alternatively, call `GET /api/v1/datasets/{dataset_name}/suggestions`.
- **Limitations & data needs**: Heuristic name and type matching only. Domain-specific jargon or obscure acronyms require manual reviewer alignment.
- **Evidence**: `tests/test_schema_mapper.py::test_suggest_mappings_heuristics`.

### Versioned Schema Mappings

- **Description**: Stores versioned, immutable mapping definitions across dataset iterations with explicit reviewer audit trails. Mapping lifecycle progresses through `PENDING_REVIEW`, `ACCEPTED`, or `REJECTED`, requiring human rationale for every status change.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/core/repository.py` (`MappingVersionRow`), `api/main.py` (`GET/POST/PUT /api/v1/datasets/{dataset_name}/mappings`, `.../accept`, `.../reject`), UI: **Data Sources** -> *Mapping History & Review*.
- **How to use it**:
  1. Submit mapping definitions via `POST /api/v1/datasets/{dataset_name}/mappings`.
  2. Inspect pending versions in the **Mapping History** panel.
  3. A human reviewer calls `POST /api/v1/datasets/{dataset_name}/mappings/{version}/accept` with a mandatory reason string.
- **Limitations & data needs**: Requires `reviewer` role for approval. Prior accepted versions remain read-only and immutable.
- **Evidence**: `tests/test_dataset_api.py::test_mapping_lifecycle_accept_reject`.

### Multi-File Relationships & Orphan Analysis

- **Description**: Previews key joins across separate company-owned files to report matched records, orphan keys, and null counts before persisting edges. Proposed entity relationships remain inactive until explicitly approved by a human reviewer.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/relationships.py`, `api/main.py` (`POST /api/v1/datasets/relationships/preview`, `.../{proposal_id}/approve`), UI: **Data Sources** -> *Relationships & Orphan Counts*.
- **How to use it**:
  1. Post join keys via `POST /api/v1/datasets/relationships/preview` with left/right source IDs and foreign keys.
  2. Review matched row percentages and orphan row counts returned by the preview.
  3. Call `POST /api/v1/datasets/relationships/{proposal_id}/approve` with a documented justification.
- **Limitations & data needs**: Relationships can only link files within the same company tenant. Joins do not create synthetic linkages across disparate historical datasets.
- **Evidence**: `tests/test_onboarding_stage2.py::test_relationships_preview_and_approval`.

### Controlled Import & Canonical Materialization

- **Description**: Transforms raw source records into normalized canonical JSONL derivatives in a background process using an accepted mapping version. The materialization pipeline tracks processed versus total row counts and aborts on structural failures.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/importer.py`, `api/main.py` (`POST /api/v1/imports/{job_id}/commit`), UI: **Data Sources** -> *Import Commit*.
- **How to use it**:
  1. Verify that an accepted mapping version exists for the dataset.
  2. Call `POST /api/v1/imports/{job_id}/commit` specifying the accepted mapping version.
  3. Poll job status until complete; the canonical derivative is saved under `data/processed/{company_id}/`.
- **Limitations & data needs**: Requires an `ACCEPTED` mapping version. Any row failing required type casts is quarantined without aborting valid rows.
- **Evidence**: `tests/test_onboarding_stage2.py::test_controlled_import_commit`.

### Import Job History & State Tracking

- **Description**: Records full operational job histories for every file upload, profiling run, and canonical materialization task. States include `QUEUED`, `RUNNING`, `COMPLETED`, `PARTIAL`, and `FAILED`, with full error payloads preserved.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/core/repository.py` (`ImportJobRow`), `api/main.py` (`GET /api/v1/imports`, `GET /api/v1/imports/{job_id}`), UI: **Data Sources** -> *Import History*.
- **How to use it**:
  1. Navigate to **Data Sources** in the UI.
  2. Scroll to the **Import History** log table to view timestamps, row counts, and status badges.
  3. Alternatively, query `GET /api/v1/imports` to inspect all tenant jobs.
- **Limitations & data needs**: Limited to the authenticated company tenant. Partial jobs disclose processed row counts and quarantine counts.
- **Evidence**: `tests/test_dataset_api.py::test_import_job_history`.

---

## 2. Canonical Data Model, Source Adapters & Multi-Tenancy

### Canonical Event Schema

- **Description**: Standardizes diverse supply-chain records into a single typed schema covering orders, shipments, products, and suppliers. Facts, predictions, hypotheses, and recommendations remain strictly separated in all models.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/core/schema.py` (`CanonicalOrderRecord`, `EventRecord`).
- **How to use it**:
  1. Materialized imports automatically map raw fields to canonical fields (`order_id`, `supplier_id`, `product_id`, `carrier`, `quantity`, `price`, `event_timestamp`).
  2. Downstream pipelines consume the canonical JSONL derivative directly.
- **Limitations & data needs**: Requires at minimum an event identifier and timestamp. Unmapped fields are collected under `custom_fields`.
- **Evidence**: `tests/core/test_schema.py`.

### Dataset Adapters (Olist, DataCo, UCI Online Retail II)

- **Description**: Serves as read-only in-memory transformers converting original static ZIP datasets into the canonical schema. Archives are never extracted to disk or mutated, ensuring complete raw data preservation.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/adapters.py` (`OlistAdapter`, `DataCoAdapter`, `RetailIIAdapter`), `scripts/run_real_datasets.py`.
- **How to use it**:
  1. Run `python scripts/run_real_datasets.py` to stream real dataset archives into memory.
  2. Each adapter maps archive members into canonical format and outputs quarantine logs.
- **Limitations & data needs**: Olist requires orders and items tables; DataCo requires main CSV; Online Retail II requires year sheets.
- **Evidence**: `tests/test_stage1_adapters_tenancy.py`, `scripts/run_real_datasets.py`.

### Multi-Tenant Company, Workspace & Project Separation

- **Description**: Isolates data storage, database tables, and API queries by company tenant using an enforced tenant identifier. Company A cannot view, query, or infer relationships from Company B's datasets, models, or audit trails.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/core/repository.py` (`TenantBase`, `WorkspaceRow`, `ProjectRow`), `api/main.py`.
- **How to use it**:
  1. Supply header `X-Company-Id: {company_id}` with every API request.
  2. The database session binds tenant filters to all SQL operations.
  3. In the UI, switch companies using the sidebar company switcher.
- **Limitations & data needs**: Requests missing `X-Company-Id` fall back to `local` or the key-associated tenant. Cross-tenant queries return 404 or empty sets.
- **Evidence**: `tests/test_stage7_cross_company.py`, `tests/test_stage1_adapters_tenancy.py`.

---

## 3. Capability Assessment & Generic Pipeline

### Capability Assessment Engine

- **Description**: Evaluates mapped canonical column roles against capability requirements to report available analytical features. Capabilities include demand analysis, delay risk, supplier risk, graph analytics, and incident assembly.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/data/capabilities.py`, `api/main.py` (`GET /api/v1/projects/{project_id}/capabilities`), UI: **Data Sources** -> *Capability Checklist*.
- **How to use it**:
  1. Open **Data Sources** and review the **Capability Checklist**.
  2. Each capability shows `AVAILABLE`, `AVAILABLE_WITH_LIMITATIONS`, `AWAITING_CONFIGURATION`, or `UNSUPPORTED`.
  3. Or call `GET /api/v1/projects/{project_id}/capabilities`.
- **Limitations & data needs**: Gated purely on accepted column mappings. If `event_timestamp` or `quantity` is missing, demand forecasting is marked `UNSUPPORTED`.
- **Evidence**: `tests/test_capabilities.py`, `tests/test_stage3_capabilities.py`, `tests/test_api_stage3.py`.

### Generic Analytical Pipeline Runner

- **Description**: Executes downstream profiling, anomaly detection, delay inference, and incident assembly for any mapped project. Execution defaults strictly to dry-run mode and supports configurable retries with backoff.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/pipeline/generic_runner.py`, `api/main.py` (`POST /api/v1/pipeline/previews`, `POST /api/v1/pipeline/run`), UI: **Data Sources** -> *Run Pipeline*.
- **How to use it**:
  1. Call `POST /api/v1/pipeline/previews` with `project_id` to test configuration.
  2. Execute `POST /api/v1/pipeline/run` to trigger background execution across available capabilities.
- **Limitations & data needs**: Only processes capabilities marked `AVAILABLE`. Does not execute when the global kill switch is active.
- **Evidence**: `tests/test_stage3_capabilities.py::test_generic_pipeline_execution`.

---

## 4. Anomaly Detection, Delay Prediction & Demand Forecasting

### Multi-Detector Anomaly Monitoring

- **Description**: Scans numerical features across entity groupings using four separate detectors: Robust Z-score, IQR, Rule-based, and Isolation Forest. Anomalies are recorded as facts linked to source record references with severity scores.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/monitoring/detectors.py`, `src/monitoring/service.py`, `api/main.py` (`GET /api/v1/anomalies`), UI: **Monitoring & Anomalies**.
- **How to use it**:
  1. Pipeline runs automatically execute active detectors on quantity, price, and transit time.
  2. Navigate to **Monitoring & Anomalies** to inspect detected anomalies and filter by detector type.
  3. Or call `GET /api/v1/anomalies` with `project_id`.
- **Limitations & data needs**: Requires at least 8 baseline records for statistical detectors. Extreme counts are flagged as detectors, not absolute proof of fraud or failure.
- **Evidence**: `tests/monitoring/test_detectors.py`, `tests/test_stage4_analytics.py`.

### Leakage-Controlled Delay Classification

- **Description**: Trains and evaluates delay classifiers using chronological train/validation/test splits (60/20/20) and strict feature allowlists. Post-outcome fields like delivered timestamps and delivery status are blocked to prevent data leakage.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/ml/delay/model.py`, `src/ml/delay/features.py`, `api/main.py` (`GET /api/v1/predictions`), UI: **Predictions & Forecasts**.
- **How to use it**:
  1. Train models via `python -m src.ml.delay.run`.
  2. View evaluated models in **System Health & Audit** -> *Model Governance*.
  3. Query predictions via `GET /api/v1/predictions`.
- **Limitations & data needs**: Requires binary delay target derived strictly from estimated vs delivered dates. Point predictions require explicit calibration to be used in risk scoring.
- **Evidence**: `tests/ml/test_leakage_controls.py`, `tests/test_stage4_analytics.py`.

### Chronological Demand Forecasting

- **Description**: Evaluates rolling-origin transaction demand baselines (Naive, Moving Average, Seasonal Naive) over historical weekly horizons. Strictly evaluated as order volume forecasting; inventory availability or stockout claims are explicitly omitted.
- **Status**: IMPLEMENTED BUT NOT ADEQUATELY TESTED (Online Retail II stopped with insufficient CV weeks)
- **Where it lives**: `src/ml/demand/model.py`, `api/main.py` (`GET /api/v1/predictions`), UI: **Predictions & Forecasts**.
- **How to use it**:
  1. Provide canonical records containing `event_timestamp` and `quantity`.
  2. Run demand forecasting module to evaluate rolling-origin CV.
  3. Inspect forecasts in **Predictions & Forecasts** screen.
- **Limitations & data needs**: Requires > 64 historical weeks for configured seasonal CV. Real Online Retail II run stopped with: `ValueError: Insufficient weekly history for configured CV: 54 weeks, need > 64` (documented in `docs/EVALUATION_REPORT.md`).
- **Evidence**: `tests/ml/test_demand_forecasting.py`, `docs/EVALUATION_REPORT.md`.

---

## 5. Incidents, Driver Analysis, Hypothesis Ledger & Risk Prioritization

### Generic Incident Assembly

- **Description**: Groups correlated anomalies and delay predictions into structured incident records carrying provenance references to raw source records. Incidents maintain separate lists of observed facts, model predictions, and emerging hypotheses.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/risk/incidents.py`, `api/main.py` (`GET /api/v1/incidents`, `.../{id}`), UI: **Incidents & Investigations**.
- **How to use it**:
  1. The generic pipeline clusters anomalies exceeding severity thresholds into incidents.
  2. Open **Incidents & Investigations** and select an incident.
  3. Review the linked evidence items, affected orders, and timeline.
- **Limitations & data needs**: Assembly is rule- and cluster-driven; incidents represent operational alerts, not legally verified causal events.
- **Evidence**: `tests/test_stage5_analysis_graph.py`, `tests/test_stage5_api.py`.

### Statistical Driver Analysis

- **Description**: Computes entity correlations across suppliers, carriers, and products using Fisher's exact test, Benjamini-Hochberg FDR correction, and changepoint analysis. Results carry the required disclaimer: `"correlation, not proof"`.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/risk/drivers.py`, UI: **Incidents & Investigations** -> *Driver Analysis*.
- **How to use it**:
  1. Open an incident investigation in the dashboard.
  2. Navigate to the **Driver Analysis** tab to inspect candidate entities.
  3. View effect sizes, adjusted p-values, and weekly change points.
- **Limitations & data needs**: Requires minimum affected support ($\ge 2$) and baseline support ($\ge 2$). Driver analysis does not establish causal agency.
- **Evidence**: `tests/test_stage5_analysis_graph.py::test_driver_analysis_planted_vs_clean`.

### Root-Cause Hypothesis Ledger

- **Description**: Manages root-cause propositions through a strict state machine: `UNVERIFIED` -> `SUPPORTED` -> `CONFIRMED` (or `REJECTED`/`CLOSED`). Confirmation requires reviewer role authentication and verified supporting evidence; automated confirmation is blocked.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/core/schema.py`, `api/main.py` (`POST /api/v1/hypotheses`, `.../review`, `.../confirm`), UI: **Incidents & Investigations** -> *Hypothesis Ledger*.
- **How to use it**:
  1. Analysts submit candidate hypotheses via `POST /api/v1/hypotheses` (status defaults to `UNVERIFIED`).
  2. Add supporting evidence refs to advance status to `SUPPORTED`.
  3. A human reviewer calls `POST /api/v1/hypotheses/{id}/confirm` with rationale; confirmation fails if evidence thresholds are unmet.
- **Limitations & data needs**: Only human reviewers can confirm. Hypotheses lacking adequate evidence return `"Insufficient evidence"`.
- **Evidence**: `tests/test_stage5_api.py::test_hypothesis_confirmation_lifecycle`.

### Multi-Factor Risk Prioritization

- **Description**: Scores operational risk across likelihood, impact, evidence strength, and uncertainty with configurable company weights. Aggregated numeric risk scores are withheld unless likelihood is explicitly calibrated.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/risk/prioritization.py`, `api/main.py` (`GET /api/v1/risk/scoring-config`, `POST /api/v1/risk/score`), UI: **Incidents & Investigations** -> *Risk Prioritization*.
- **How to use it**:
  1. View or configure weights via `GET/PUT /api/v1/risk/scoring-config` (admin only for edits).
  2. Calculate risk breakdown via `POST /api/v1/risk/score`.
  3. If likelihood is uncalibrated, qualitative rating is returned without an aggregate score.
- **Limitations & data needs**: Requires calibrated probability from a verified model; uncalibrated inputs produce qualitative risk categories only.
- **Evidence**: `tests/test_stage5_api.py::test_risk_scoring_qualitative_fallback`.

---

## 6. Aggregated Supply-Chain Network & Tracing

### Aggregated Cohort Network Visualizer

- **Description**: Visualizes supply-chain entities grouped into meaningful cohorts (suppliers, product categories, shipment groups, carriers, warehouses, process stages) rather than individual orders. Node health is calculated against peer group baselines with pulsing indicators on problem nodes.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/network/aggregated_graph.py`, `api/main.py` (`GET /api/v1/projects/{project_id}/graph/aggregated`), UI: **Supply-Chain Graph**.
- **How to use it**:
  1. Select a project and open **Supply-Chain Graph** in the dashboard.
  2. Toggle between **Network View** (force-directed) and **Process Flow** (layered left-to-right).
  3. Inspect problem nodes highlighted with red pulsing rings and view ranked candidate sources.
- **Limitations & data needs**: Capped at 150 nodes by default; tail nodes are clustered into `{type}:Other` groups with clustering statistics reported.
- **Evidence**: `tests/test_graph_redesign.py::test_aggregated_graph_identifies_planted_faulty_supplier`, `dashboard/src/components/SupplyGraphScreen.test.tsx`.

### Upstream & Downstream Exposure Tracing

- **Description**: Traverses supply network paths upstream to find candidate problem sources and downstream to quantify affected product groups. Traversal proceeds strictly along confirmed `ESTABLISHED` edges and is labelled `"exposure/hypothesis, not confirmed cause"`.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/network/aggregated_graph.py`, `api/main.py` (`GET /api/v1/projects/{project_id}/graph/aggregated/trace`), UI: **Supply-Chain Graph** -> *Side Panel Tracing*.
- **How to use it**:
  1. Click any node in the graph visualizer to open its side panel.
  2. Click **Trace Downstream Exposure** or **Trace Upstream Sources**.
  3. The canvas highlights traversed path edges and affected nodes in violet, dimming unaffected entities.
- **Limitations & data needs**: Only follows `ESTABLISHED` edges; `INFERRED` edges are excluded from automated trace paths to prevent speculative graph walking.
- **Evidence**: `tests/test_graph_redesign.py::test_downstream_trace_from_faulty_supplier`.

### Historical Health Evolution Replay

- **Description**: Captures time-bucketed health snapshots per node across historical weekly intervals for interactive time-series replay. Users can scrub or play the slider to observe exactly when a supplier or cohort deteriorated into a problem state.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/network/aggregated_graph.py`, `dashboard/src/components/SupplyGraphScreen.tsx`, UI: **Supply-Chain Graph** -> *Time Slider Bar*.
- **How to use it**:
  1. Load a project graph containing multi-week time buckets.
  2. Use the time slider at the bottom of the canvas or click **Play**.
  3. Node colors update dynamically reflecting historical snapshot health for that bucket.
- **Limitations & data needs**: Requires time-series timestamps in the underlying canonical records.
- **Evidence**: `tests/test_graph_redesign.py::test_time_bucketed_health_shows_when_node_turned_problem`.

---

## 7. Recommendations, What-If, Alerts, Approvals & Guarded Actions

### Evidence-Linked Playbooks & Recommendations

- **Description**: Emits contextual mitigation recommendations linked to verified incident evidence, outlining rationale, assumptions, trade-offs, and uncertainties. Effects are explicitly marked `HYPOTHETICAL` unless supported by qualifying history.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/recommendations/engine.py`, `api/main.py` (`GET /api/v1/recommendations`, `POST .../playbooks`), UI: **Recommendations & Approvals**.
- **How to use it**:
  1. Open **Recommendations & Approvals** to view generated mitigation cards.
  2. Review preconditions, trade-offs, and linked evidence items.
  3. Analysts may request approval for an action linked to a recommendation.
- **Limitations & data needs**: Playbooks require mapped entity roles. Missing roles return `NEEDS_DATA`.
- **Evidence**: `tests/test_stage6_api.py::test_recommendations_evidence_linkage`.

### Hypothetical What-If Arithmetic Simulator

- **Description**: Evaluates hypothetical mitigation scenarios through explicit probability reduction arithmetic with mandatory assumption tracking. Responses and scenario outputs are labelled `HYPOTHETICAL` with cost/capacity calculations strictly omitted.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/recommendations/what_if.py`, `api/main.py` (`POST /api/v1/recommendations/what-if`), UI: **Recommendations & Approvals** -> *What-If Simulator*.
- **How to use it**:
  1. Navigate to the **What-If Simulator** tab in Recommendations.
  2. Enter baseline delay probability, affected orders, and scenario reduction percentages.
  3. Specify required scenario assumptions and calculate hypothetical outcome changes.
- **Limitations & data needs**: Requires calibrated probability; does not predict real-world cost savings or inventory impact.
- **Evidence**: `tests/test_stage6_api.py::test_what_if_scenario_labeling`.

### Guarded Action Engine & Kill Switch

- **Description**: Executes mitigation actions strictly under a `dry_run: true` default, protected by a global emergency kill switch, sliding-window rate limits, and a circuit breaker. High-impact actions require recorded human reviewer approval.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/actions/executor.py`, `api/main.py` (`POST /api/v1/actions`, `PUT /api/v1/admin/kill-switch`), UI: *Header Kill Switch & Actions*.
- **How to use it**:
  1. Analysts record actions via `POST /api/v1/actions`; executions default to `DRY_RUN`.
  2. High-impact actions require an `approval_id` from the approval queue.
  3. Admins toggle the kill switch via `PUT /api/v1/admin/kill-switch` with mandatory justification.
- **Limitations & data needs**: Process-local kill switch resets on restart. Dry-run actions do not trigger external HTTP or operational side-effects.
- **Evidence**: `tests/test_stage6_workflow_connectors.py::test_kill_switch_and_rate_limits`.

### Alert Deduplication, Routing & Escalation

- **Description**: Groups incident notifications by source and key, suppressing duplicates within a 900-second window and escalating unacknowledged alerts over elapsed time. Console and append-only JSONL file sinks are fully implemented.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/alerts/service.py`, `api/main.py` (`GET /api/v1/alerts`, `POST .../acknowledge`, `POST .../assign`), UI: **System Health & Audit** -> *Alert History*.
- **How to use it**:
  1. Pipeline incidents automatically trigger alert routing based on severity.
  2. Analysts acknowledge or assign alerts via `POST /api/v1/alerts/{id}/acknowledge`.
  3. View escalation history in the **Alert History** tab.
- **Limitations & data needs**: In-process deduplication window. External notification channels (SMTP, Slack) remain simulated.
- **Evidence**: `tests/test_stage6_workflow_connectors.py::test_alert_routing_and_escalation`.

### Local Workflow Scheduler & Connectors

- **Description**: Manages local periodic cron intervals, batch triggers, and folder/REST/database connector health checks. External enterprise connectors (ERP, WMS) return `EXTENSION_NOT_IMPLEMENTED`.
- **Status**: IMPLEMENTED AND TESTED (Scheduler & core connectors); SIMULATED (ERP/WMS)
- **Where it lives**: `src/workflow/scheduler.py`, `src/connectors/manager.py`, `api/main.py` (`GET /api/v1/connectors/health`).
- **How to use it**:
  1. Check connector health via `GET /api/v1/connectors/health`.
  2. Scheduler runs locally via `LocalWorkflowScheduler(settings)` and is not auto-started by the web API.
- **Limitations & data needs**: Notifications disabled unless `CONNECTORS_ENABLED=true` is set in the environment.
- **Evidence**: `tests/test_stage6_workflow_connectors.py::test_connector_health_and_scheduler`.

---

## 8. Monitoring, Drift, Model Versioning & Governance

### Schema & Statistical Feature Drift

- **Description**: Compares newly imported dataset versions against prior baselines to detect added, removed, or retyped columns and numerical distribution shifts. Drift is strictly an advisory signal (`drift_is_warning_only: true`) and never triggers automatic retraining.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/monitoring/drift.py`, `api/main.py` (`GET /api/v1/datasets/{name}/drift`), UI: **Monitoring & Anomalies** -> *Drift Advisory*.
- **How to use it**:
  1. Upload a subsequent version of an existing dataset.
  2. Call `GET /api/v1/datasets/{name}/drift` to compare against baseline.
  3. View schema additions, type changes, and mean shift flags in the UI.
- **Limitations & data needs**: Requires at least two committed dataset versions. Advisory only; does not mutate running models.
- **Evidence**: `tests/test_stage7_governance_monitoring.py::test_schema_and_feature_drift`.

### Model Registry, Promotion & Rollback

- **Description**: Maintains reproducible evaluation reports per model version with explicit holdout hashes and parameters. Model promotion to active status requires reviewer authorization with recorded rationale, and rollback restores the prior version.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/ml/registry.py`, `api/main.py` (`GET /models`, `GET .../metrics`, `POST .../promote`, `POST .../rollback`), UI: **System Health & Audit** -> *Model Governance*.
- **How to use it**:
  1. Inspect registered candidate models and metric comparisons in **Model Governance**.
  2. Reviewers call `POST /api/v1/models/registry/{version}/promote` with documented reasoning.
  3. If performance degrades, call `POST /api/v1/models/registry/rollback` to revert.
- **Limitations & data needs**: Promotion requires matching holdout data hashes. Candidate metrics must satisfy configured promotion criteria.
- **Evidence**: `tests/test_stage7_governance_monitoring.py::test_model_registry_promote_rollback`.

### Post-Hoc Outcome Tracking & Alert Evaluation

- **Description**: Records verified operational outcomes and calculates true alert precision, missed event rates, and Brier calibration scores. Unverified observations are stored but excluded from alert metrics until verified by a reviewer.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/monitoring/evaluator.py`, `api/main.py` (`GET /api/v1/evaluation/outcomes`, `.../alerts`), UI: **System Health & Audit** -> *Evaluation*.
- **How to use it**:
  1. Reviewers submit verified binary labels via `POST /api/v1/outcomes`.
  2. Query `GET /api/v1/evaluation/outcomes` to inspect forecast MAE/MAPE, accuracy, and confusion matrix.
  3. When verified labels are unavailable, returns `INSUFFICIENT_VERIFIED_OUTCOMES`.
- **Limitations & data needs**: Requires reviewer-verified ground truth labels. Evaluated observations must chronologically succeed predictions.
- **Evidence**: `tests/test_stage7_governance_monitoring.py::test_outcome_evaluation_verified_labels`.

---

## 9. Security: Authentication, Roles, Multi-Tenancy & Audit

### Role-Based Access Control (RBAC)

- **Description**: Enforces hierarchical API authentication (`admin` > `reviewer` > `analyst` > `viewer`) via constant-time API key comparisons loaded from `API_KEYS_JSON`. Unauthorized requests receive structured `401 Unauthorized` or `403 Forbidden` responses.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/security/auth.py`, `api/main.py`.
- **How to use it**:
  1. Pass header `X-API-Key: {key}` with every HTTP request.
  2. Minimum roles: `viewer` for read queries, `analyst` for creating hypotheses/actions, `reviewer` for confirmations/approvals, `admin` for kill-switch/audit.
- **Limitations & data needs**: Configured via environment variable JSON mapping; keys must never be committed to source control.
- **Evidence**: `tests/test_phase10_security.py`, `tests/test_stage7_cross_company.py`.

### Cryptographic SHA-256 Audit Log

- **Description**: Appends all governance decisions, mapping approvals, model promotions, and actions to an immutable hash-chained audit log. Event records include previous and current SHA-256 hashes with sensitive payloads redacted.
- **Status**: IMPLEMENTED AND TESTED
- **Where it lives**: `src/core/repository.py` (`AuditEventRow`), `api/main.py` (`GET /api/v1/audit`), UI: **System Health & Audit** -> *Audit Log*.
- **How to use it**:
  1. Governance actions automatically generate hash-chained records.
  2. Admins query `GET /api/v1/audit` with optional category and event-type filters.
  3. Inspect audit events in the UI **Audit Log** tab.
- **Limitations & data needs**: Read access is strictly restricted to the `admin` role.
- **Evidence**: `tests/test_stage7_governance_monitoring.py::test_audit_hash_chain_integrity`.

---

## 10. UI Screens

All 10 dashboard screens are located in `dashboard/src/components/` and communicate with the backend via `ApiClient`:

| Screen Component | File Location | Purpose & Core Capabilities |
|---|---|---|
| **Login / Credentials** | `LoginScreen.tsx` | Authenticates sessions, stores API URL, API key, Company ID, and role hint in tab session storage. |
| **Company Switcher** | `CompanySwitcher.tsx` | Allows switching active company tenant and project scope from the header and sidebar. |
| **Overview** | `OverviewScreen.tsx` | High-level system posture, incident counts, quality freshness cards, and active kill-switch status. |
| **Data Sources** | `DataSourcesScreen.tsx` | Multipart upload, streaming profile cards, mapping suggestion wizard, relationship join approvals, and capability checklist. |
| **Monitoring & Anomalies** | `MonitoringScreen.tsx` | Quality metric items, anomaly counts by detector type, and schema/feature drift advisory badges. |
| **Predictions & Forecasts** | `PredictionsScreen.tsx` | Leakage-controlled delay predictions with SHAP attribution disclaimers and rolling demand forecasts. |
| **Incidents & Investigations** | `IncidentsScreen.tsx` | Incident queue, evidence viewer, statistical driver analysis, and reviewer-gated hypothesis ledger. |
| **Supply-Chain Graph** | `SupplyGraphScreen.tsx` | Cytoscape network with Network/Process views, peer baselines ($z$-scores), candidate sources strip, time replay slider, and exposure tracing. |
| **Recommendations & Approvals** | `RecommendationsScreen.tsx` | Evidence-linked playbook cards, hypothetical what-if simulator, approval queue, and dry-run action recorder. |
| **System Health & Audit** | `SystemHealthScreen.tsx` | Model registry governance, outcome evaluation metrics, admin kill-switch toggle, and hash-chained audit log viewer. |

---

## Before vs Now

| Capability | Before (Dataset-Specific) | Now (Company-Independent / Generic) |
|---|---|---|
| **Data Ingestion** | Hardcoded loaders tied to specific ZIP structures (`olist.zip`, `dataco.zip`). | Streaming upload for CSV, TSV, JSON, JSONL, XLSX, and single-table ZIP with SHA-256 verification. |
| **Schema Flexibility** | Fixed column names hardcoded in parsing scripts. | Heuristic mapping wizard suggesting canonical roles with immutable versioning. |
| **Relationships** | Single-table assumption or hardcoded joins. | Multi-file join preview reporting matched percentages and orphan key counts prior to approval. |
| **Multi-Tenancy** | Single global workspace without company boundaries. | Strict tenant isolation (`company_id`) on database queries, file storage, and audit logs. |
| **Pipeline Triggering** | Fixed scripts executed per dataset. | Dynamic capability assessment enabling features based on mapped canonical roles. |
| **Anomaly Detection** | Dataset-specific thresholds hardcoded in scripts. | Entity-grouped multi-detector suite (Robust Z, IQR, Rule, Isolation Forest) on canonical fields. |
| **Network Visualization** | Order-item subgraphs returning individual orders. | Cohort-level network (Suppliers, Products, Carriers, Groups) with peer $z$-score baselines and node capping. |
| **Governance & Actions** | Ad-hoc scripts with direct execution. | Role-gated review queues, dry-run action engine, circuit breaker, rate limiter, and global kill switch. |
| **Audit & Integrity** | Plain JSONL log files. | Cryptographic SHA-256 hash-chained tamper-evident audit records with admin-only access. |

---

## Supported Inputs

Read directly from `config/settings.yaml` and source validation logic:

- **Supported File Formats**: `.csv`, `.tsv`, `.json` (array of objects), `.jsonl`, `.xlsx`, `.zip` (single tabular entry).
- **Upload Size Limits**:
  - Maximum upload size: `52,428,800` bytes (50 MB).
  - Stream chunk size: `1,048,576` bytes (1 MB).
  - Chunk rows: `10,000` rows per profiling chunk.
  - ZIP entries: At most `500` entries, maximum `209,715,200` uncompressed bytes (200 MB), maximum compression ratio `100`.
- **Minimum Columns per Capability**:
  - **Demand Analysis**: `event_timestamp`, `quantity`.
  - **Delay Risk Prediction**: `event_timestamp`, `quantity`, `price`, `supplier_id`, `product_id`, `carrier`, `destination`, plus non-leaked post-outcome label.
  - **Supplier Risk**: `supplier_id`, `quantity`, `price`, `event_timestamp`.
  - **Graph Visualizer**: `supplier_id`, `product_id`, `carrier` (or mapped entity identifiers).
  - **Incident Assembly**: Requires at least one active anomaly detector or delay prediction source.

---

## Not Built Yet / Simulated

The following components represent simulated prototypes or unbuilt extensions:

- **Enterprise ERP / WMS Integrations**: SAP, Oracle, and Manhattan WMS connectors return `EXTENSION_NOT_IMPLEMENTED` (simulated stubs in `src/connectors/manager.py`).
- **External Notifications**: SMTP email and Slack webhook channels log to local JSONL files; network delivery is simulated while `CONNECTORS_ENABLED` is false.
- **Real-Time Streaming**: Ingestion operates via chunked batch uploads and polling; real-time Kafka or WebSocket ingestion is not implemented.
- **Automated External Actions**: Mitigation actions default to `dry_run: true` and record database audit rows; direct automated ERP purchase-order modifications are omitted by design.
- **Automated Project Listing**: The API does not provide a dynamic project enumeration endpoint; project identifiers are entered manually or selected from session history.

---

## Honest Limitations

- **Academic Prototype Boundary**: The system is an educational and exploratory prototype. It is not certified for production deployment or automated operational execution.
- **Proxy Labels**: Olist review classifications use customer rating bands (1-2 complaint, 3 neutral, 4-5 positive) as proxy signals; they are not human-annotated sentiment ground truth.
- **Correlation vs Causation**: Driver analysis and network traces identify statistical associations and exposure paths, never proven causal agency. Confirmed causes require human reviewer verification.
- **Synthetic Test Data**: Unit, scenario, and component tests utilize synthetic data (`acme_industrial`) to verify mechanics and API contracts. Synthetic results must never be cited as real-world accuracy.
- **Unverified Predictions**: Predictions remain unproven statistical estimates until evaluated against reviewer-verified historical outcomes.

---

## Verified Test Summary

Real executed test suite results from terminal verification:

```text
============================= Backend Test Suite (pytest) =============================
Command: powershell -Command "$env:PYTHONPATH='.'; .venv\Scripts\python.exe -m pytest -q"
Result:  176 passed, 1 skipped, 1 warning in 79.65s (0:01:19)
Notes:   1 skipped test is the synthetic Excel-loader test requiring openpyxl in base env.
         1 warning is StarletteDeprecationWarning regarding httpx testclient.

============================= Frontend Test Suite (vitest) ============================
Command: npm test -- --run (in dashboard/)
Result:  4 test files passed, 27 tests passed in 5.27s
Files:   - src/components/transparency.test.tsx (3 passed)
         - src/components/SupplyGraphScreen.test.tsx (4 passed)
         - src/components/phase11b.test.tsx (6 passed)
         - src/components/stage9.test.tsx (14 passed)

============================= Frontend Code Quality ===================================
Command: npm run lint
Result:  0 errors, 0 warnings

Command: npm run typecheck
Result:  Clean (tsc -b exited with code 0)

Command: npm run build
Result:  Vite v6.4.5 built 1769 modules in 15.43s
```
