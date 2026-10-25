# API contract (v1)

FastAPI publishes the machine-readable schema at `/openapi.json` and interactive documentation at `/docs` (ReDoc at `/redoc`). All API routes use `/api/v1`. Supply `X-API-Key`; the server maps secrets to roles using the `API_KEYS_JSON` environment variable, for example `{"replace-viewer-key":"viewer","replace-analyst-key":"analyst","replace-reviewer-key":"reviewer","replace-admin-key":"admin"}`. Never commit real keys. Roles are hierarchical: analyst includes viewer access; reviewer includes analyst access; admin includes reviewer access. CORS origins are comma-separated in `CORS_ORIGINS`.

Errors have the same structure: `{"error":{"code":"forbidden","message":"reviewer role required","details":null}}`. Invalid payload errors use `invalid_request` and include validation details. Request models reject unknown fields. Examples below are **synthetic** identifiers and values; they are contract examples only, not production records.

| Method and path | Minimum role | Purpose / response |
|---|---|---|
| `GET /api/v1/health` | viewer | API health and version |
| `GET /api/v1/quality` | viewer | Quality snapshots, null rates, drift and freshness |
| `GET /api/v1/incidents` | viewer | Incident list |
| `GET /api/v1/incidents/{incident_id}` | viewer | Incident with evidence, hypotheses, explanation and limitations |
| `GET /api/v1/predictions` | viewer | Prediction records |
| `GET /api/v1/anomalies` | viewer | Anomaly records and evidence fields |
| `GET /api/v1/hypotheses` | viewer | Hypothesis list and lifecycle status |
| `POST /api/v1/hypotheses` | analyst | Create an unverified hypothesis |
| `POST /api/v1/hypotheses/{hypothesis_id}/review` | analyst | Review a hypothesis (confirmation is disallowed here) |
| `POST /api/v1/hypotheses/{hypothesis_id}/confirm` | reviewer | Confirm only when evidence thresholds pass |
| `GET /api/v1/recommendations` | viewer | Recommendation list |
| `GET /api/v1/approvals` | viewer | Approval history |
| `POST /api/v1/approvals` | analyst | Create a pending approval for an existing recommendation |
| `POST /api/v1/approvals/{approval_id}/approve` | reviewer | Approve a pending item with rationale |
| `POST /api/v1/approvals/{approval_id}/reject` | reviewer | Reject a pending item with rationale |
| `GET /api/v1/actions` | viewer | Action records |
| `GET /api/v1/actions/history` | viewer | Action history |
| `POST /api/v1/actions` | analyst | Record a dry-run action; high-impact class requires an approved record; kill switch blocks it |
| `GET /api/v1/alerts` | viewer | Alert-related audit history |
| `GET /api/v1/incidents/{incident_id}/graph` | viewer | Stored incident, evidence, hypothesis and recommendation nodes/edges |
| `GET /api/v1/models` | viewer | Model versions |
| `GET /api/v1/models/{model_id}/metrics` | viewer | Evaluation metrics stored with a model version |
| `GET /api/v1/outcomes` | viewer | Recorded outcomes |
| `GET /api/v1/audit` | admin | Hash-chained audit events |
| `GET /api/v1/admin/kill-switch` | admin | Read process-local kill-switch state |
| `PUT /api/v1/admin/kill-switch` | admin | Change process-local kill-switch state and audit the request |
| `POST /api/v1/pipeline/run` | analyst | Record a pipeline dry-run request; this endpoint does not execute the pipeline |
| `POST /api/v1/datasets/upload` | reviewer | Stream CSV, XLSX, JSON, JSONL or single-table ZIP into a company-scoped immutable source file; returns an asynchronous import job ID and SHA-256 |
| `GET /api/v1/imports` | reviewer | Company-scoped import history |
| `GET /api/v1/imports/{job_id}` | reviewer | Import job status, processed/total rows, aggregate profile statistics or failure details |
| `POST /api/v1/imports/{job_id}/preview` | reviewer | Preview `append` or `replace` row counts without changing monitoring state |
| `POST /api/v1/imports/{job_id}/commit` | reviewer | Commit an explicitly accepted mapping and materialize the complete canonical JSONL derivative in a background task |
| `POST /api/v1/imports/{job_id}/reprocess` | reviewer | Queue a new profile job after an accepted mapping version changes |
| `GET /api/v1/datasets/{dataset_name}/suggestions` | reviewer | Get mapping suggestions with confidence scores (never auto-confirms) |
| `GET /api/v1/datasets/{dataset_name}/mappings` | reviewer | Version history including pending/accepted/rejected status and review history |
| `POST /api/v1/datasets/{dataset_name}/mappings` | reviewer | Create an unconfirmed mapping version, including custom fields, units, time zone and date format |
| `PUT /api/v1/datasets/{dataset_name}/mappings/{version}` | reviewer | Edit a mapping by creating a new pending version; prior versions remain immutable |
| `POST /api/v1/datasets/{dataset_name}/mappings/{version}/accept` | reviewer | Explicitly accept a mapping version with a required reason |
| `POST /api/v1/datasets/{dataset_name}/mappings/{version}/reject` | reviewer | Reject a mapping version with a required reason |
| `PUT /api/v1/datasets/{dataset_name}/confirm-mapping` | reviewer | Compatibility route; records a new explicit accepted mapping version |
| `GET /api/v1/datasets` | reviewer | Company-scoped source list, mapping state, hash and monitoring state |
| `DELETE /api/v1/datasets/{dataset_name}` | reviewer | Remove source from monitoring via soft deletion; preserves raw file, versions, jobs and audit history |
| `POST /api/v1/datasets/relationships/preview` | reviewer | Preview key joins across company-owned files; returns matched, orphan and null-reference counts only |
| `POST /api/v1/datasets/relationships/{proposal_id}/approve` | reviewer | Persist a proposed relationship only after explicit approval with a reason |

Upload requests use `multipart/form-data` with a `file` field and an optional `dataset_name`. JSON inputs must be top-level arrays of objects or JSONL. Upload limits are configured in `config/settings.yaml` under `uploads` (`max_size_bytes`, `chunk_bytes`, `chunk_rows`, ZIP entry/uncompressed-size/compression-ratio limits). Uploads are streamed into tenant-specific raw storage and SHA-256 is checked against stored bytes. The raw file is never normalized in place. Profiles retain column names and aggregate statistics only; no sample values are saved. Oversized uploads are rejected before a job is created. If row processing fails after consuming rows, the job is `PARTIAL` with `processed_rows` and an unknown `total_rows`; a complete import requires processed rows to equal the profiled total. ZIP archives are not extracted to disk; to avoid silently combining unrelated tables, each archive may contain one supported tabular member. Multi-table inputs should be uploaded as separate files.

## Synthetic request examples

Upload a **synthetic** CSV, then poll the returned `import_job_id` (the response starts in `QUEUED`; profiling runs in a background task). The original uploaded bytes are stored unchanged and the response SHA-256 is checked against the stored file.

```json
{
  "dataset_name": "synthetic_orders",
  "source_id": "synthetic-source-001",
  "dataset_version_id": "synthetic-dataset-version-001",
  "import_job_id": "synthetic-import-001",
  "sha256": "synthetic-example-only",
  "status": "QUEUED",
  "processed_rows": 0,
  "total_rows": null
}
```

Create a pending **synthetic** mapping version; no suggestion is ever confirmed automatically:

```json
{
  "mappings": {"Order Ref": "order_id", "Event Date": "order_ts"},
  "custom_fields": {"vendor_ref": "Vendor Ref"},
  "units": {"quantity": "items"},
  "time_zone": "UTC",
  "date_format": "%Y-%m-%d",
  "reason": "Synthetic reviewer mapping"
}
```

Preview **synthetic** source relationships before approval:

```json
{
  "links": [{
    "left_source_id": "synthetic-orders-source",
    "left_key": "order_ref",
    "right_source_id": "synthetic-shipments-source",
    "right_key": "order_ref",
    "relationship": "order_shipment"
  }]
}
```

The preview includes matched rows, orphan rows and null-key counts. It creates only a pending proposal; call `/api/v1/datasets/relationships/{proposal_id}/approve` with `{"reason":"Synthetic explicit approval"}` to persist an approved relationship record.

Create an unverified hypothesis:

```json
{
  "incident_id": "synthetic-incident-001",
  "statement": "Synthetic hypothesis for review",
  "source": "synthetic",
  "record_refs": ["synthetic-row-001"]
}
```

Review/confirm and approval decisions use a rationale:

```json
{"status":"SUPPORTED","rationale":"Synthetic evidence review"}
```

```json
{"rationale":"Synthetic reviewer decision"}
```

Create a pending approval:

```json
{"recommendation_id":"synthetic-recommendation-001"}
```

Create a dry-run action (no external side effect is performed):

```json
{
  "recommendation_id":"synthetic-recommendation-001",
  "action_class":"READ_ONLY",
  "approval_id":null
}
```

Toggle the kill switch:

```json
{"enabled":true,"reason":"Synthetic operator request"}
```

Request a pipeline dry-run:

```json
{"datasets":["olist","dataco","online_retail_ii"]}
```

Example dry-run response:

```json
{
  "status":"DRY_RUN",
  "executed":false,
  "message":"Request recorded; pipeline was not executed by this dry-run endpoint.",
  "datasets":["olist"],
  "kill_switch":false
}
```

## Operational boundaries

- These routes expose persisted local SQLite state through the Phase 8 repository. The process-local kill switch resets when the API process restarts; configure the persistent default in `config/settings.yaml`.
- `POST /pipeline/run` records an audited dry-run request only. A background scheduler/worker API has not been added.
- Action requests accept only a constrained action class and recommendation identifier. Request text is not interpreted as a command. Actions are recorded as `DRY_RUN`; the API does not execute external actions.
- Graph edges describe stored incident relationships only; no cross-dataset links are inferred here.
- API keys are a simple local authentication mechanism. For deployment, key distribution, rotation, storage and transport security must be configured by the operator.

## Stage 5 extensions

All examples below use synthetic identifiers and require the API key role shown.

| Method and path | Role | Purpose and limits |
|---|---|---|
| `POST /api/v1/incidents/assemble` | analyst | Assemble persisted anomalies/predictions from one dataset version into an incident with fact/prediction evidence and `UNVERIFIED` hypotheses. Body: `{"anomaly_ids":["synthetic-anomaly-1"],"prediction_ids":["synthetic-prediction-1"],"title":"Synthetic incident"}`. Each ID list is capped at 100. |
| `POST /api/v1/projects/{project_id}/drivers` | analyst | Compare affected refs to the same source's accepted-mapping canonical records. Body: `{"project_id":"synthetic-project","source_id":"synthetic-source","affected_record_refs":["synthetic:row-1"]}`. Up to 5,000 refs; returns ranked hypotheses, support, effect size, corrected p-value, change-point estimate and limitations. It states `correlation, not proof`. |
| `GET /api/v1/projects/{project_id}/graph` | viewer | Bounded graph and analytics. Query filters: `company_id`, `supplier_id`, `product_id`, `start`, `end`, `risk`, and `limit` (1–5,000). Company scope is enforced by the repository; a different company ID returns 403. |
| `GET /api/v1/projects/{project_id}/graph/neighborhood?node_id=supplier:synthetic:1&hops=1&limit=100` | viewer | Expand 1–3 graph hops, at most 500 returned nodes/edges. Results are exposure/hypothesis. |
| `GET /api/v1/projects/{project_id}/graph/trace/downstream?node_id=supplier:synthetic:1&limit=100` | viewer | Downstream exposure trace on `ESTABLISHED` edges only. Limit 1–500. |
| `GET /api/v1/projects/{project_id}/graph/trace/upstream?node_id=order:synthetic:1&limit=100` | viewer | Upstream hypothesis trace on `ESTABLISHED` edges only. Limit 1–500. |
| `POST /api/v1/projects/{project_id}/graph/relationships` | analyst | Propose a user-entered edge. Body: `{"left_node_id":"supplier:synthetic:1","right_node_id":"product:synthetic:2","meaning":"Synthetic approved supply link","source_record_ref":"synthetic:approval-record","valid_from":"2025-01-01T00:00:00Z","valid_to":null}`. It is not active until reviewer approval. |
| `POST /api/v1/graph/relationships/{proposal_id}/approve` | reviewer | Approve a proposed graph edge. Body: `{"rationale":"Synthetic review"}`. Approved edge remains flagged `USER_ENTERED`. |
| `GET /api/v1/risk/scoring-config` | viewer | Return latest company risk config or defaults, including version, weights and severity thresholds. |
| `PUT /api/v1/risk/scoring-config` | admin | Create an inactive candidate config version. Body: `{"weights":{"likelihood":0.35,"impact":0.3,"evidence_strength":0.2,"uncertainty":0.15},"thresholds":{"low_max":0.2,"medium_max":0.45,"high_max":0.7}}`. Weights must define all four factors and be non-negative; thresholds must increase within 0–1. Reviewer promotion is required before use. |
| `POST /api/v1/risk/score` | analyst | Body: `{"likelihood":0.8,"likelihood_calibrated":false,"impact":0.6,"evidence_strength":0.5,"uncertainty":0.4}`. Returns factor-by-factor breakdown; uncalibrated likelihood is omitted and numeric severity is withheld where not defensible. |

Hypothesis responses now include both canonical `status` and a presentation `status_label`. The label is display-only; confirmation continues to require the reviewer role.

## Stage 6 workflow extensions

Examples use synthetic values. Notifications and action endpoints remain dry-run by default.

| Method and path | Role | Payload / behavior |
|---|---|---|
| `POST /api/v1/recommendations/playbooks` | analyst | Select an evidence-linked playbook. Body: `{"incident_id":"synthetic-incident","driver_type":"supplier","driver_value":"synthetic-supplier","evidence_refs":["synthetic-evidence"]}`. The API checks evidence belongs to the incident and derives available roles from the accepted mapping. Missing roles return `NEEDS_DATA`. Recommendations include rationale, assumptions, uncertainty, trade-offs, approvals, preconditions, status and result. Effect estimates are omitted unless qualifying history is available and are always `HYPOTHETICAL`. |
| `POST /api/v1/recommendations/what-if` | analyst | Explicit hypothetical scenario arithmetic. Body: `{"affected_order_count":10,"calibrated_delay_probability":0.4,"probability_calibrated":true,"scenarios":[{"name":"synthetic-monitoring","assumed_relative_probability_reduction":0.1,"assumptions":["synthetic planning assumption"]}]}`. Each scenario requires assumptions; no capacity, inventory or cost-savings estimates are made. |
| `POST /api/v1/alerts/{group_id}/acknowledge` | analyst | Body: `{"reason":"Synthetic review started"}`. Appends acknowledgement history. |
| `POST /api/v1/alerts/{group_id}/assign` | analyst | Body: `{"assigned_to":"synthetic-reviewer"}`. Appends assignment history. |
| `GET /api/v1/alerts/history?limit=100` | viewer | Read local alert grouping, escalation, acknowledgement and assignment history. Limit 1–1,000. |
| `GET /api/v1/connectors/health` | admin | Check configured folder, REST, database, SMTP and webhook connectors. Notification checks perform no network call while `CONNECTORS_ENABLED` is false. ERP and WMS are returned as `EXTENSION_NOT_IMPLEMENTED`. |
| `POST /api/v1/actions/{action_id}/verification` | reviewer | Record an external execution verification, not execute an action. Body: `{"executed":true,"verified":true,"result":{"status":"synthetic verified"}}`. Dry-run actions cannot be verified as executed; high-impact actions still require approved reviewer approval. |
| `POST /api/v1/outcomes` | analyst | Record later observation. Body: `{"action_id":"synthetic-action","source":"synthetic","observed_at":"2026-01-01T00:00:00Z","facts":{"delay":1},"record_refs":["synthetic-order"],"prediction_refs":["synthetic-prediction"],"recommendation_refs":["synthetic-recommendation"],"result":{}}`. Linked predictions/recommendations must predate the observation. Comparisons do not establish causality. |

The Python `LocalWorkflowScheduler` exposes timer and new-batch triggers, durable job history, retry attempts and status; it is controlled locally and is not started automatically by the API. See `docs/WORKFLOW.md` and `docs/CONNECTORS.md`.

## Stage 7 monitoring and model governance

Examples use synthetic values. Schema and feature drift store aggregate statistics only. Drift is an advisory signal and never triggers automatic retraining or deployment. Model promotion is reviewer-gated and never automatic. Requests can supply `X-Company-Id: <company_id>` to enforce strict tenant isolation.

| Method and path | Role | Payload / behavior |
|---|---|---|
| `GET /api/v1/datasets/{dataset_name}/drift` | reviewer | Schema changes (added, removed, retyped columns) and statistical feature drift between the latest dataset upload and prior baseline. Returns `drift_is_warning_only: true` and never triggers retraining. |
| `GET /api/v1/evaluation/outcomes` | viewer | Company-scoped outcome evaluation covering forecast-vs-actual (MAE, MAPE, bias), prediction-vs-outcome (accuracy, precision, recall, brier score, confusion matrix), and verified alert precision/missed events. Where verified outcomes are unavailable, returns `INSUFFICIENT_VERIFIED_OUTCOMES` with `"not enough verified outcomes"`. |
| `GET /api/v1/evaluation/alerts` | viewer | Return alert precision and missed-event counts only from reviewer-verified binary labels; otherwise return `INSUFFICIENT_VERIFIED_LABELS` stating `"not enough verified outcomes"`. |
| `GET /api/v1/models/{model_version}/evaluation-report` | viewer | Reproducible evaluation report stored per model version, containing `model_version`, `data_version`, `mapping_version`, `seed`, `metrics`, and `limitations`. |
| `GET /api/v1/models/registry/comparisons/{candidate_version}` | analyst | Compare candidate/current metrics under configured criteria. Requires matching holdout data hash and chronological split context. |
| `POST /api/v1/models/registry/{model_version}/set-current` | reviewer | Explicitly approve the initial current model when no current version exists. Body: `{"reason":"Synthetic baseline approval"}`. |
| `POST /api/v1/models/registry/{candidate_version}/promote` | reviewer | Body: `{"reason":"Synthetic reviewer approval"}`. Promotion fails if criteria are unmet or evaluation contexts differ. |
| `POST /api/v1/models/registry/rollback` | reviewer | Body: `{"model_key":"olist:delay_model","reason":"Synthetic rollback review"}`. Restores the prior explicitly recorded model version. |
| `GET /api/v1/risk/scoring-config/{version}/comparison` | analyst | Compare candidate risk configuration with the current version; performance effect stays `NOT_ESTIMATED`. |
| `POST /api/v1/risk/scoring-config/{version}/promote` | reviewer | Promote a validated candidate risk configuration with a required reason. |
| `POST /api/v1/risk/scoring-config/rollback` | reviewer | Restore the previous risk configuration with a required reason. |
| `PUT /api/v1/admin/permission-policy` | admin | Body: `{"role_levels":{"viewer":1,"analyst":3,"reviewer":5,"admin":8}}`. Role ordering is validated and changes are audited. |
| `GET /api/v1/audit?category={category}&event_type={event_type}` | admin | Hash-chained audit log with optional filtering by event type or category (`source`, `mapping`, `rule`, `model`, `permission`, `prediction`, `investigation`, `action`). |

To include a verified label while recording an outcome, both `verified_alert_label` and `alert_was_raised` booleans are required, and the caller must have reviewer role. Unverified observations remain stored but are excluded from alert evaluation.

## Functionality 5 Aggregated Supply-Chain Network Redesign

Aggregated, interactive network representation where each node represents a product family, supplier cohort, carrier, warehouse/region or process group rather than individual orders. Node health is calculated relative to peer baselines (z-score on anomaly and exposure rates). Time-bucketed health evolution snapshots enable historical health replay in the UI. Upstream and downstream exposure traces traverse along confirmed `ESTABLISHED` edges and are labelled `"exposure/hypothesis, not confirmed cause"`. Tail nodes exceeding the node limit (default 150) are clustered into "Other" nodes with full capping metadata.

| Method and path | Minimum role | Purpose / response |
|---|---|---|
| `GET /api/v1/projects/{project_id}/graph/aggregated?incident_id={id}&max_nodes=150&min_flow_weight=1` | viewer | Aggregated network with group nodes (`Supplier`, `Product`, `ShipmentGroup`, `Carrier`, `Warehouse`, `CustomerRegion`, `ProcessStage`, `Other`). Response includes `nodes`, `edges`, `time_buckets`, `capping`, `missing_roles`, and ranked `candidate_sources`. Nodes have `health` (`HEALTHY`, `WATCH`, `PROBLEM`, `UNKNOWN`), `health_reason`, `metrics_vs_peer_baseline`, `anomaly_count`, and `time_series`. |
| `GET /api/v1/projects/{project_id}/graph/aggregated/trace?node_id={id}&direction={upstream\|downstream}&max_depth=6` | viewer | Exposure traversal along `ESTABLISHED` edges only. Returns `reached_nodes`, `path_edges`, `node_count`, and disclaimer `"exposure/hypothesis, not confirmed cause"`. |
| `GET /api/v1/incidents/{incident_id}/graph/aggregated?max_nodes=150` | viewer | Aggregated network scoped to an incident, marking candidate source nodes as culprits (`culprit: true`), downstream nodes as affected (`affected: true`), and ranking candidate source nodes. |


