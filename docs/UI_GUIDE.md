# Dashboard UI guide

The dashboard is a local API client. It does not include sample records; test fixtures are synthetic and used only by tests. Finding badges distinguish `FACT`, `PREDICTION`, `HYPOTHESIS`, and `RECOMMENDATION`. Provenance or unavailable source metadata appears with the finding. The visible role is a session hint, while the backend enforces the API-key role.

## Connect

1. Start the local API using [RUN_LOCALLY.md](RUN_LOCALLY.md).
2. Run the frontend from `dashboard/` with `npm install` and `npm run dev`.
3. Open **Session credentials** in the sidebar, enter the API key and role hint, then save. The key is kept in the tab session and sent only to the configured API base URL.
4. The header shows API connection, kill-switch state (when the admin-only route is permitted), and dry-run state. A dry-run banner appears when action history contains dry-run records. If the configured state is not exposed, the UI says it is unavailable.

## Screens

### Overview

Shows stored incident count, returned data-quality/freshness snapshots, recent incidents, and monitoring posture. Severity aggregation and pipeline-run history are explicitly unavailable because the API has no endpoint/field for them.

### Incidents

Search, sort, and filter the incident list. Severity/status controls disclose that the current incident schema does not provide those attributes. Select a record to open the incident investigation.

### Incident investigation

Displays the incident record and its linked evidence, prediction, feature explanation when returned, risk breakdown when returned, hypotheses and review history, recommendations, stated limitations, missing-evidence notes, and linked action/approval history. Feature explanations display `feature contribution, not proven cause`. Missing alternatives or evidence values are shown as unavailable; the UI does not invent a cause or confidence.

### Dependency graph

Select an incident to view the graph returned by its API graph route. Each edge label shows its meaning, `ESTABLISHED`/`INFERRED` state, and source reference. Inferred edges use a dashed visual treatment and are explicitly described as hypotheses, not confirmed causes. The current graph endpoint provides stored incident, evidence, hypothesis, and recommendation nodes; it does not return supplier/order dependency relationships.

### Supply-chain graph (Aggregated network visualizer)

Interactive Cytoscape visualizer representing supply-chain entities grouped into meaningful cohorts (suppliers, product categories, shipment groups, carriers, warehouses, customer regions, and process stages) rather than individual orders.
- **Layout Switcher**: Toggle between force-directed Network View (`cose`/`fcose`) for discovering clusters and layered Process Flow View (`dagre` left-to-right) for tracing end-to-end supply progression.
- **Node Health & Peer Baselines**: Health states (`HEALTHY` green, `WATCH` amber, `PROBLEM` red with pulsing ring indicator, `UNKNOWN` grey) are dynamically evaluated against peer cohorts. Selecting a node displays its exposure volume, anomalies, and z-score comparisons against peer mean ± std in the side panel.
- **Problem Focus & Candidate Sources**: Top candidate source nodes are ranked in a dedicated strip above the canvas. Clicking a candidate focuses the graph on the source and triggers exposure tracing.
- **Exposure Tracing**: Trace downstream affected entities or upstream candidate sources along confirmed `ESTABLISHED` edges with visual canvas highlighting; all paths are explicitly labelled `"exposure/hypothesis, not confirmed cause"`.
- **Historical Health Replay**: The time slider allows scrubbing through historical weekly buckets or auto-playing health state transitions to pinpoint when an entity transitioned into a `PROBLEM` state.
- **Persistent Legend**: Always-visible guide detailing health colors, edge styles (Solid: Established, Dashed: Inferred, Dotted: User-entered), and exposure volume sizing.
- **Capping & Missing Roles Disclosures**: Informative notices when tail nodes are clustered into "Other" nodes due to graph size limits, and pill badges for node roles omitted from the active dataset.

### Hypothesis ledger

Analyst-or-higher session settings expose the create form. New hypotheses are created as `UNVERIFIED`. Reviews require a selected status and rationale; confirmation is enabled only when the UI role is exactly `reviewer` and a reason is supplied. The API rechecks the key's actual role and evidence requirements. The backend response supplies the displayed lifecycle and review history.

### Recommendations & approvals

Lists recommendations and approval records. Analyst-or-higher may request approval or record an action. Reviewer-or-higher may approve/reject a pending item only after entering a reason. Recorded actions are labelled `DRY_RUN`; the UI does not represent these records as executed actions.

### Alerts & outcomes

Shows alert history, action history, stored outcomes, and the count of returned predictions. Outcome facts are kept separate from prediction values. The API does not expose a prediction reference on an outcome or a prediction/outcome comparison result, so the screen does not pair them speculatively.

### Models & evaluation

Shows model versions returned by the API and their `training_data_version` references. Exact computed evaluation values are shown from `docs/EVALUATION_REPORT.md`, with the report identified as their source. Olist review results are labelled proxy score bands; limitations include no human verification and no causal claim. Dataset versions have no list endpoint in the current API contract.

### Audit log

Read-only and admin-key restricted. The table displays event type, actor, source, timestamp, and hash-chain fields. Event details and record-reference payloads are omitted from the UI to minimize exposure of potentially sensitive data.

### Settings

Change the API base URL, switch light/dark theme, and view the kill-switch status. Only an admin-role session shows the toggle. Changing it opens a confirmation dialog and requires a reason; the backend still checks the actual API key role and records the request in its audit log. The kill-switch state is process-local in the current backend and resets on restart.

### 404 and rendering errors

Unknown dashboard paths show a 404 page with a route back to Overview. A global error boundary hides rendering internals and offers a reload action.

## Backend gaps

- No supplier/order relationship graph is returned by the incident graph endpoint.
- No dataset-version listing endpoint exists; models expose only their training-data version reference.
- Outcome records do not expose prediction IDs or a prediction-versus-observed comparison object.
- The API does not provide pipeline run history, incident severity/status, or the configured dry-run flag.
- Incident details do not separately structure SHAP values, risk-factor breakdowns, alternative explanations, or missing-evidence records; the dashboard only displays fields the endpoint returns.
- Audit is admin-only. Other roles receive the restricted/unauthorized state.
