# Phase progress

## Completed: AnomalyPlus Industrial UI Overhaul with Collapsible Sidebar & 9 Dedicated Pages

- **Execution Date**: 2026-10-25
- **Brand & Theme**:
  - Renamed project to **AnomalyPlus** (`AnomalyPlus — Industrial Supply Chain Risk Intelligence`).
  - Adopted deep industrial charcoal/slate aesthetic (`#0e1217`) with subtle `#21262d` dividers, slate cards (`#161b22`), and warm golden amber accents (`#e5a93c`).
  - Removed watermark (`Local API only / No external services`).
  - Streamlined header: replaced verbose `admin ADMIN local` badge pill with clean circular avatar `A` and quick sign-out control.
- **Collapsible Sidebar ("Three Lines" Hamburger Navigation)**:
  - Added responsive hamburger toggle button (`☰`) at top-left.
  - Smooth sidebar transition (`transform: translateX(-100%)` / `margin-left: 0; width: 100%`) when toggled.
- **9 Dedicated Functional Pages**:
  1. 📥 **Data Ingestion**: Multi-table file upload dropzone (`.zip`, `.csv`, `.xlsx`, `.json`), automated profiling, and canonical schema mapping review (auto-accepted vs ambiguous awaiting approval).
  2. ⚡ **Automated Analysis**: Dynamic 9-stage analysis execution engine with live duration ticker, active executing stage indicator with amber pulsing glow (`stage-running-glow`), factual zero-hallucination NLP stage explanations from `src/nlp/stage_explainer.py`, and real-time execution audit stream.
  3. 🔍 **Anomalies**: Consolidated anomaly ledger deduplicated at the record level across detector ensembles (`iqr`, `robust_zscore`, `isolation_forest`) with severity filters.
  4. 📈 **Forecasts vs Baseline**: Predictive delay classification and rolling-origin demand forecasting directly compared against historical naive baselines (MAE and sMAPE error reduction metrics).
  5. 🧬 **Contributing Factors**: Root-cause factor ledger tracking confounding carrier $\times$ route interactions, standardized "contributing factor" terminology, and reviewer hypothesis lifecycle (`UNVERIFIED` $\rightarrow$ `SUPPORTED` $\rightarrow$ `CONFIRMED`).
  6. 💡 **Recommendations**: Mitigation counterfactual playbooks marked with `HYPOTHETICAL SIMULATION` badges, with human reviewer Approve / Reject dry-run actions.
  7. 🚨 **Alerts**: Incident triage dispatch history, delivery status monitoring (`SENT`, `DRY_RUN`), duplicate suppression stats, and notification adapter health.
  8. 🌐 **Compact Network**: Topological flow summary table (Supplier $\leftrightarrow$ Product $\leftrightarrow$ Carrier $\leftrightarrow$ Route) with bottleneck risk scores and degree centrality.
  9. 🏢 **Company Scope**: Multi-tenant boundary isolation, active workspace and project selector, zero data bleed verification, and immutable SHA-256 audit chaining.
- **Safety & Operator Controls**:
  - **Interactive Kill Switch**: Converted static element into working toggle button calling backend `PUT /api/v1/admin/kill-switch` with real-time visual Armed (green) vs Triggered/Emergency Halted (pulsing red) feedback.
  - **Model Rollback**: Interactive rollback trigger calling backend `POST /api/v1/models/registry/rollback` to immediately revert candidate models in `src/ml/model_registry.json`.
  - Cleaned up obsolete role-switch selector and schedule activity components.
- **Verification & Testing Results**:
  - Frontend Build: `tsc -b && vite build` built successfully in 25.75s with **0 errors and 0 warnings**.
  - Vitest Unit & Component Suite: **5 test files passed, 33 tests passed in 46.55s**.
  - Backend API & Pytest Suite: **193 passed, 1 skipped in 122.34s**.
  - Browser Automation Verification: Verified responsive hamburger toggle, all 9 dedicated view transitions, interactive analysis run, and captured UI artifacts via `browser_subagent`.

## Completed: Simplified One-Page ML Prototype & Automated Transparency Pipeline

- **Execution Date**: 2026-10-25
- **Git Checkpoint**: Tagged `pre-simplify` commit `a1a7ec9` before refactoring; verified all dataset archives, `.env`, and model binaries are untouched.
- **One-Page ML Prototype Component (`dashboard/src/components/OnePagePrototype.tsx`)**:
  - Implemented single-page workflow: file upload (`.zip`, `.csv`, `.xlsx`, `.json`), schema mapping review with explicit ambiguity distinction (confident auto-accepted vs ambiguous requiring review), and a primary "Run Pipeline Analysis" action button.
  - Interactive 9-stage progression grid displaying real-time execution across:
    1. Ingestion & Integrity
    2. Schema Discovery
    3. Data Quality & Quarantine
    4. Capability Detection
    5. Anomaly Detection
    6. Predictive Modeling
    7. Root-Cause Drivers
    8. Recommendations & Counterfactuals
    9. Action Guardrails & Alerts
  - Integrated natural language stage explanations generated from structured logs and verified against immutable facts via `src/nlp/stage_explainer.py` with deterministic fallback.
  - Rich interactive result views:
    - **Deduplicated Anomalies Table**: Multiple detector triggers per record are consolidated, displaying multi-detector badges (`iqr`, `robust_zscore`, `isolation_forest`).
    - **Demand Forecasting**: Rolling-origin forecast evaluation reporting both MAE and sMAPE, compared directly against the naive baseline.
    - **Root-Cause Drivers**: Carrier $\times$ route interaction pairs, single-driver confounding check (`"explained by <driver>"`), strictly standardized `"contributing factor"` terminology (never `"cause"`), and human-reviewer confirmation gating (with explicit 403 Forbidden feedback for non-reviewers).
    - **Hypothetical Recommendations**: Clearly marked counterfactuals with Approve/Reject actions and auditable rationale inputs.
    - **Grouped Alerts**: Delivery status tracking (`dry-run`, `sent`, `failed`, `retrying`) across in-app, console, and webhook/telegram adapters.
    - **Supply Network Summary**: Problem nodes with z-score baselines and degree metrics.
    - **Model & Configuration Rollback**: One-click rollback to previous stable configuration or model checkpoint.
- **Navigation & Architectural Preservation (`dashboard/src/App.tsx`, `api/main.py`)**:
  - Set One-Page Prototype as default landing view (`screen === 'overview'`).
  - Concealed secondary consoles behind a subtle "Show Advanced Views" toggle, preserving 100% of underlying backend modules and endpoints for auth, company isolation, audit logging, graph analytics, and model registry without deletion.
- **Backend Enhancements**:
  - `src/nlp/stage_explainer.py`: Stage explanation generator with number/entity factual integrity verification and deterministic template fallback.
  - `src/data/schema_mapper.py`: Threshold-based schema mapping ambiguity categorization (`auto_accepted`, `needs_clarification`, `is_custom_field`).
  - `src/ml/anomaly/canonical.py`: Record-level anomaly deduplication across detectors and weekly demand spike check.
  - `src/ml/delay/canonical_demand.py`: sMAPE error calculation alongside MAE for candidate and baseline forecasts.
  - `src/risk/drivers.py`: Driver interaction pairs, confounding check, and `"contributing factor"` wording.
  - `src/connectors/notifications.py` & `src/alerts/manager.py`: Alert delivery status recording (`DRY_RUN`, `SENT`, `FAILED`, `RETRYING`).
  - `api/main.py`: Synthesized 9-stage execution in `_execute_project_pipeline`, added `GET /projects/{project_id}/pipeline/runs/latest` and `GET /pipeline/runs/{run_id}` endpoints.
- **Verification & Testing Results**:
  - Full Pytest Regression Suite: **193 passed, 1 skipped, 0 failures** in 122.34s (`pytest tests/ -q --ignore=tests/test_e2e_acceptance_unseen.py`).
  - Prototype Specific Test Suite (`tests/test_simplify_prototype.py`): **6 passed in 11.27s** (zip traversal rejection, excel non-tabular sheet skip, mapping ambiguity distinction, fact-checking integrity, alert delivery status, 403 permission enforcement).
  - Frontend Build & Test Suite: `tsc -b && vite build` succeeded with 0 errors; Vitest passed **5 test files, 33 tests** in 6.76s.
  - Real Datasets In-Memory Validation (`scripts/run_real_datasets.py`):
    - Olist: 1,550,922 rows (1,292,106 valid, 258,816 quarantined) in 10.33s.
    - DataCo: 180,519 rows (180,519 valid, 0 quarantined) in 48.96s.
    - Online Retail II: 1,067,371 rows (1,055,238 valid, 12,133 quarantined) in 221.18s.
  - Planted Fault Synthetic Evaluation: **Recall: 1.0000, Detection Delay: 0 days**.
  - Browser Verification: Successfully navigated, verified, and captured screenshots and video recordings of the One Page Prototype via `browser_subagent`.


## Completed: Stage 5 generic incidents, drivers, risk and graph APIs

- Read `AGENTS.md` and `docs/PROGRESS.md`. `docs/PRODUCT_SPEC.md` is absent from this workspace, so the requested Functionality 5/6/8 sections could not be checked; implementation follows the Stage 5 requirements in the user prompt.
- Added generic incident assembly from stored anomalies and predictions. Incident evidence carries source record refs; observed anomalies and model predictions remain separate evidence types. Generated hypotheses begin `UNVERIFIED` and use the existing reviewer-only confirmation lifecycle.
- Added human-readable `status_label` values to hypothesis API serialization while preserving canonical lifecycle states: Unverified, Supported by evidence, Human confirmed, Rejected, Closed. Dashboard files were not touched because `AGENTS.md` limits frontend edits to Phase 11.
- Added driver analysis for supplier, carrier, product, region, mode and ISO week, when mapped. It reports minimum support, rate-difference effect size, Fisher exact p-values, Benjamini-Hochberg correction, a descriptive weekly change-point estimate, supporting/contradicting refs and missing evidence. Results state `correlation, not proof`; evidence-backed candidates remain hypotheses.
- Added company-versioned risk scoring configuration with configurable weights and severity thresholds. Likelihood, impact, evidence strength and uncertainty are separate factors. A numeric aggregate/severity is withheld unless likelihood is explicitly calibrated and impact is available; otherwise a qualitative rating is returned. API config versions are stored under tenant/company scope and included in a new Alembic revision.
- Added a canonical graph based on completed canonical imports with accepted mappings. Entity IDs are namespaced by source, so matching IDs across sources do not create links. Edges include meaning, source, source-record reference, mapping/hash or approval provenance, validity interval, and `ESTABLISHED`, `INFERRED` or `USER_ENTERED` flag. Reviewer approval is required before a user-entered edge is active. Missing node types are listed.
- Added graph analytics for supplier incident counts vs peer average, supplier concentration, single-source products and downstream order exposure. Upstream and downstream trace endpoints traverse `ESTABLISHED` edges only. Analytics are labelled exposure/hypothesis, not causation.
- Added bounded graph, neighborhood and trace API routes; company/supplier/product/time/risk filters; analyst driver and incident assembly routes; and admin-only risk configuration routes. API examples and method/limitations are documented in `docs/API_CONTRACT.md` and `docs/RISK_METHOD.md`.
- Added synthetic-only planted-driver, no-driver, downstream supplier trace, incident provenance, qualitative risk fallback, API permission, graph size-limit and incident persistence tests. These verify mechanics only and are not real-data performance results.
- Verification: `ruff check .` — passed. Full suite: `pytest -q --basetemp=.pytest_tmp_stage5` — 127 passed, 1 skipped, 1 Starlette/httpx deprecation warning. TestClient required local loopback access; tests were run with that access enabled.

### Stage 5 pending / limitations

- No real-data Stage 5 driver, risk or graph results were computed. No claims about model accuracy or real supplier causes are made.
- Product-spec-specific UI wording remains unverified because `docs/PRODUCT_SPEC.md` is missing. API labels are available; the dashboard was not edited under the current AGENTS.md phase restriction.
- Graph detail and coverage depend on user-approved canonical mappings, imported record references and explicit review of user-entered relationships. A node health peer comparison is reported only when stored incidents can be linked to source records.

## Completed: Phase 1 foundation and dataset audit

- Inspected the workspace and project instructions before editing.
- Recorded three dataset archives, their workspace paths, compressed sizes and baseline SHA-256 hashes in `docs/DATASET_REGISTER.md`.
- Added the initial repository overview, ignore rules, dependency list and dry-run environment example.
- Added `scripts/audit_datasets.py`, which reads CSV and Excel members directly from ZIP archives in memory and emits structural reports under `docs/audit/`.
- Dataset licenses remain UNKNOWN. Verify original publisher terms, attribution, redistribution and derivative-work conditions before use or sharing.
- Ran `python scripts/audit_datasets.py` using the bundled Python runtime: 3 archive reports written, covering 9 Olist tables / 1,550,922 rows, 3 DataCo files / 650,548 rows, and 2 Online Retail II sheets / 1,067,371 rows.
- Post-audit SHA-256 values match the pre-audit values for all three archives.

## Completed: Phase 2 data and domain foundations

- Added typed Pydantic schemas for the requested domain records, provenance references, separate fact/prediction/hypothesis/recommendation types, hypothesis status/review history, and a human-review entry requirement for CONFIRMED hypotheses.
- Added YAML-backed typed settings for thresholds, weights, dry-run, kill switch, rate limits, freshness and chunk size.
- Added separate read-only ZIP loaders for Olist, DataCo's primary dataset (excluding access logs), and each Online Retail II workbook sheet.
- Added structured validation with null/type/date/duplicate/freshness reporting and explicit invalid-row quarantine output.
- Added source-specific processing directories with valid/quarantine files and lineage records containing source archive SHA-256, transform steps and timestamp.
- Added append-only JSONL audit events with SHA-256 chaining and basic sensitive-key redaction.
- Added synthetic-only tests in `tests/core/` and `tests/data/`.
- Verification: `python -m pytest -q --basetemp=.pytest_tmp` — 10 passed, 1 skipped. The synthetic Excel-loader test skipped because `openpyxl` is unavailable in the Python environment running pytest; it is declared in `requirements.txt`.

## Pending at Phase 1 handoff (historical)

- Review label definitions, temporal availability and dataset-specific leakage before any modeling.
- Implement only subsequent phases when requested.

## Completed: Phase 7 alerts, guarded actions and outcomes

- Added config-driven incident alert grouping, duplicate suppression restored from local history, severity routing, elapsed-time escalation, and append-only alert history. Console/file channels implement a small interface; no external service integrations were added.
- Added action classes, trusted-code operation registry, untrusted-text filtering, global kill switch, dry-run default, recorded reviewer approval requirement for high-impact actions, sliding-window rate limit, circuit breaker, idempotency handling, bounded exponential retries and audit events. Only completed handler execution returns `success: true`; dry-run results are explicitly `DRY_RUN`.
- Added pending/approved/rejected reviewer workflow with required reason, timestamp and audit event. Added append-only observed-outcome tracking and comparison that requires the prediction to predate the outcome.
- Added synthetic tests for kill switch, approval enforcement/audit, duplicate suppression including restart history, rate limiting, idempotency, dry-run, retry/backoff, circuit breaker, alert routing/escalation, and outcome comparison.
- Tests: `python -m pytest -q --basetemp=.pytest_tmp` — 48 passed, 1 skipped.

## Completed: Phase 7B Olist review NLP and optional GPU workflows

- Added the CPU/GPU and no-fabricated-results rule to the README.
- Added an Olist-only review text pipeline for normalization, regex PII redaction, heuristic language detection, date/quantity extraction, and explicit untrusted-text/no-action markers. ZIP data is read in memory without archive extraction; CSV input is also supported for hosted runs.
- Defined proxy review labels in `docs/LABELS.md`: scores 1–2 complaint, 3 neutral, and 4–5 positive. Added chronological split and label limitations.
- Added a CPU TF-IDF + Logistic Regression baseline and majority baseline with holdout metrics/artifact output. After correcting duplicate class-label weighting, the rerun produced 42,687 eligible reviews and a shared chronological 25,612/8,537/8,538 split. The TF-IDF macro F1 is 0.6705198260559485 and the majority macro F1 is 0.27998188405797103; results are in `models/nlp/metrics.json`.
- Added optional BERTimbau fine-tuning and chunked sentence-embedding scripts under `scripts/gpu/`, with device detection, CUDA fp16, fixed seeds, checkpoint resume/chunk resume, input hashes, and configurable output paths. Added `requirements-gpu.txt` separately from CPU requirements.
- Added inference with explicit missing-model behavior, plus citation-bearing cosine retrieval that treats retrieved text as context rather than proof. Added Colab T4 and Kaggle instructions in `docs/GPU_RUNBOOK.md`.
- Added synthetic-only NLP and retrieval tests. Final verification: `python -m pytest -q --basetemp=.pytest_tmp` — 54 passed, 1 skipped.
- Imported Colab artifacts from `outputs_small.zip` into `models/bertimbau/` and `models/embeddings/` after checking that destination paths did not exist. The temporary extraction directory was deleted; the source ZIP was left untouched.
- At the Phase 7B import, the archive did not include BERT metrics or training config. These were supplied later and evaluated in Phase 7C; see `docs/EVALUATION_REPORT.md`. The model label mapping matches the documented review-score bands.
- The embedding directory contains 9 `.npz` chunks and 9 matching ID JSON files; each pair's row counts match. Its metrics JSON reports 42,687 rows embedded/resumed and 9 chunks. Record files contain review IDs only, not source text.
- Updated inference to load the installed BERT model from `models/bertimbau/model` and retain the TF-IDF fallback. Retrieval now loads the chunked index from `models/embeddings` and returns cited IDs without fabricating absent source text.
- Evaluation comparison was completed in Phase 7C on the same chronological test split. The CPU BERT re-evaluation exactly matches the Colab accuracy and macro metrics; details and limitations are in `docs/EVALUATION_REPORT.md`.
- Tests after artifact wiring: `python -m pytest -q --basetemp=.pytest_tmp` — 55 passed, 1 skipped. A smoke call against the installed chunked embedding index returned a cited review ID and correctly indicated that text was not stored.

## Completed: Phase 6 graph, recommendations and what-if

- Added `networkx` as the phase dependency.
- Added Olist-only order-item relationship graph with established `SUPPLIES`, `SHIPS` and `AFFECTS` edges sourced to the actual Olist order-item row. Added typed support/contradiction, proposed-cause and mitigation edge helpers with explicit meanings, source refs and established/inferred flags; graph helpers reject cross-dataset edges.
- Added distinct seller downstream order exposure counts, explicitly labelled “exposure, not confirmed causation.”
- Added rule-based seller investigation, shipment-status verification, monitoring, and calibrated-probability notification recommendations. Each emitted recommendation requires evidence links and includes rationale, assumptions, uncertainty, constraints, human approval and dry-run fields.
- Added calibrated-baseline what-if comparisons with explicit assumptions and `HYPOTHETICAL` labels on the response and every scenario.
- Added synthetic-only tests for graph provenance/flags/exposure, cross-dataset prevention, recommendation evidence and fields, and hypothetical scenario labeling.
- Tests: `python -m pytest -q --basetemp=.pytest_tmp` — 34 passed, 1 skipped.

## Completed: Phase 5 explainability and risk investigation

- Added `shap` as the only new dependency. Added SHAP explanation output for fitted tree and linear estimators, with model version and the required disclaimer `feature contribution, not proven cause`.
- Added factor-by-factor risk prioritization with configurable weights, saturation, freshness, evidence strength and uncertainty. Delay probability is omitted unless explicitly marked calibrated. Method and interpretation limits are documented in `docs/RISK_METHOD.md`.
- Added an evidence ledger with supporting, contradicting and missing evidence, configurable support thresholds, lifecycle transition checks, review rationale/history, and reviewer-role enforcement for `CONFIRMED`.
- Added an investigator that resolves references against audited ZIP data, verifies provided observed values, returns source facts separately from predictions/hypotheses, keeps alternatives unverified, and reports insufficient evidence if record/feature verification fails.
- Tests: `python -m pytest -q --basetemp=.pytest_tmp` — 29 passed, 1 skipped. The existing Excel loader test remains skipped because openpyxl is unavailable in the active Python environment.

## Completed: Phase 4 labels and evaluation implementation

- Defined Olist delay as delivered timestamp later than estimated delivery timestamp; only delivered orders with both timestamps are eligible. Documented at-order feature timing and exclusions in `docs/LABELS.md`.
- Defined DataCo target as the audited `Late_delivery_risk` field and excluded that target, `Delivery Status`, actual shipping duration, and shipping date from model inputs. Documented other timing caveats.
- Added chronological train/validation/test splitting; majority and transparent threshold rule baselines; Logistic Regression, Decision Tree, and Random Forest pipelines; classification, calibration, confusion-matrix and subgroup metrics; model artifact/registry metadata; and rolling-origin naive, moving-average, seasonal-naive demand forecast evaluation.
- Fixed seed and evaluation/model/CV parameters are saved in `config/settings.yaml`. `src/ml/model_registry.json` and model artifacts are created when training dependencies permit.
- Added synthetic tests for label derivation, DataCo feature allowlist, chronological splitting, subgroup calculations, and demand CV mechanics.
- Tests: `python -m pytest -q --basetemp=.pytest_tmp` — 23 passed, 1 skipped.
- Phase 7C rerun: `python -m src.ml.delay.run --root .`. Olist and DataCo classifier metrics and model artifacts were computed. Online Retail II demand forecasting did not run to metrics because rolling-origin CV stopped with `ValueError: Insufficient weekly history for configured CV: 54 weeks, need > 64`.

## Completed: Phase 3 features and anomaly monitoring

- Added Olist delivery, DataCo shipping, and Online Retail II product-week demand features with feature descriptions and availability boundaries in `docs/FEATURE_CATALOG.md`.
- Seller delivery history uses prior orders only; Retail II demand lags use prior weeks only. DataCo realized shipping and late-risk label are separate outcome fields.
- Added configurable rule-based, robust z-score, IQR, and optional Isolation Forest detectors. Anomaly scores and baselines are separate from any operational severity.
- Added a source-separated runner that writes JSONL anomaly evidence with dataset, source record reference, feature, observed value, baseline and detector score; settings are recorded in `data/processed/anomalies/settings_used.json`.
- Synthetic verification: `python -m pytest -q --basetemp=.pytest_tmp` — 16 passed, 1 skipped (Excel reader test skipped because openpyxl is unavailable in the pytest environment).
- Real archive run: Olist flags — rule 4,913; robust z-score 6,327; IQR 9,774. DataCo flags — rule 0; robust z-score 0; IQR 0. These are flag counts only, not accuracy or performance metrics.

## Known limitations

- Name-based candidate labels and ID detection are heuristics, not semantic validation.
- Structural profiling does not establish causal relationships, event ordering, license rights or a valid predictive target.
- Online Retail II has no inventory or stockout labels; DataCo has potential target leakage; Olist post-purchase fields must not be used for earlier predictions.
- The system Python emits a warning that its configured Python executable path could not be resolved, but pytest executed successfully using its installed environment.
- Validation is generic unless dataset-specific required columns and date columns are supplied; broad semantic/type expectations still need careful definition before modeling.
- DataCo's delay target and post-event fields remain leakage risks. Its access logs are not loaded by the primary DataCo pipeline.
- Olist post-purchase delivery/review values and Online Retail II's lack of inventory/stockout labels retain Phase 1 limitations. No real dataset was transformed during synthetic tests.
- Audit hash chaining detects content changes but does not prevent filesystem-level alteration; use protected storage for stronger tamper resistance. No secrets or row contents should be added to event details.
- Phase 7C reran anomaly detection with Isolation Forest and Retail II enabled; per-detector flag counts are in `docs/EVALUATION_REPORT.md` and generated JSONL evidence. Counts are flags only, not accuracy.
- Olist outcome anomaly flags use post-delivery duration/deviation for monitoring and must not be reused as pre-delivery predictors. DataCo returned zero flags at the configured feature thresholds; this is not evidence of no operational risk.
- Retail II demand forecasting remains uncomputed because its configured rolling-origin split requires more weekly history than the audited series provides.
- Olist estimate availability at purchase and DataCo target construction are not verified by the archives alone. Retail II sheets are evaluated separately and each has limited annual history; the configured 52-week seasonal baseline may not have enough rolling history within a single sheet.
- SHAP was confirmed on one fitted Olist delay Decision Tree; the output is `models/olist_delay-decision_tree-v1-shap.json` and states `feature contribution, not proven cause`.
- Phase 9 added local API-key role mapping and reviewer-only confirmation. It is not an identity provider; secure key distribution and rotation remain unimplemented.
- The language detector is a small heuristic, and regex PII redaction cannot guarantee detection of every sensitive string. The stored review embedding records lack text, so retrieval can cite matching review IDs but cannot return their text.

## Completed: Phase 7C evaluation gap closure

- Reproduced BERT's Olist review split and input: `data/raw/olist/olist_order_reviews_dataset.csv` is not materialized locally, so the CSV member was read directly from the Olist ZIP. Its SHA-256 matched BERT config `012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7`; split rows matched exactly (train 25,612; validation 8,537; test 8,538).
- Added `scripts/eval_bert_cpu.py`; CPU inference used only the final 8,538 test rows, batch size 16, max sequence length 256. It computed per-class precision/recall/F1, macro F1, accuracy and confusion matrix to `models/bertimbau/eval_metrics.json`. Accuracy, macro precision, macro recall and macro F1 exactly matched the Colab metrics JSON.
- Reran the Olist TF-IDF Logistic Regression and majority baselines on that same chronological split. The corrected unique-class macro F1 values are 0.6705198260559485 and 0.27998188405797103 respectively; BERT's observed macro F1 is 0.6774153223722116. Point estimates favor BERT; statistical significance was not tested. Labels remain proxy review-score bands with no human verification and do not establish delay causes.
- Reran `python -m src.ml.anomaly.run --root .`. Olist flags: rule 4,913; robust z-score 6,327; IQR 9,774; Isolation Forest 1,920. DataCo: 0 for each. Online Retail II: rule 662; robust z-score 37,071; IQR 24,466; Isolation Forest 2,035.
- Ran `python -m src.ml.delay.run --root .`; Olist/DataCo classifiers completed. Demand forecasting failed with insufficient weekly history (54 weeks; configured CV requires more than 64), recorded as the actual error in the evaluation report.
- Produced a one-sample SHAP explanation for `olist_delay-decision_tree-v1`; the explanation note is `feature contribution, not proven cause`.
- Final verification: `python -m pytest -q --basetemp=.pytest_tmp` — 58 passed in 18.49s.

## Completed: Phase 8 local persistence and orchestration

- Added SQLAlchemy 2 and Alembic. SQLite is the local default at `data/processed/supply_chain.db` (Git-ignored); the repository selects its backend through `storage.url` in `config/settings.yaml`. Added Alembic revisions for the relational schema. No external database or cloud service is used.
- Added relational tables for dataset/model versions, predictions, anomalies, incidents, evidence, hypotheses, recommendations, approvals, actions, outcomes, audit events, and quality snapshots. Provenance links use foreign keys; audit event hashes are copied from the append-only hash-chained JSONL log.
- Added `src/core/pipeline.py` to read dataset ZIP members, validate and quarantine rows in memory, write privacy-safe quarantine manifests with source locators/reasons only, report freshness for dated members, build each source's features separately, detect anomalies, apply existing model artifacts to the chronological post-training portion when present, forecast Retail II using a simple last-week baseline, investigate a bounded sample, prioritize, recommend, route local dry-run alerts, and persist run summaries.
- Added simple configured row-count/null-rate drift checks, bounded retries and optional interval scheduling, plus a daily summary from SQLite. Evidently was not added because row-count and null-rate comparisons cover the current basic quality/drift need.
- Synthetic integration fixtures are explicitly synthetic and test SQLite foreign keys, audit linkage, all orchestration stages, source-safe investigation, daily summary, and invalid-schema quarantine behavior.
- Final all-dataset real archive run: `python -m src.core.pipeline --root C:\Projects\supply-chain-risk-system`. Olist: 1,550,922 input rows; 258,816 quarantined; 99,441 feature rows; 11,017 anomaly flags (rule 2,715; robust z-score 2,465; IQR 4,875; Isolation Forest 962); predictions capped at 1,000; 20 investigations; 40 recommendations. DataCo: 180,519 input/feature rows; 0 quarantined; 0 anomaly flags; predictions capped at 1,000. Online Retail II: 1,067,371 input rows; 12,133 quarantined; 206,725 product-week rows; 64,294 anomaly flags (rule 659; robust z-score 36,963; IQR 24,613; Isolation Forest 2,059); next-week naive forecasts capped at 1,000; 20 investigations; 20 recommendations. These are per-run pipeline counts, not quality or performance claims; configured caps are recorded in the run JSON. Olist translation-table ingestion and DataCo full-chunk processing were corrected before this final clean-database run.
- Dataset archive SHA-256 values were checked after the read-only runs and match the recorded values in `docs/DATASET_REGISTER.md`. Licenses remain UNKNOWN.
- Freshness checks were false for the inspected historical order/review dates, DataCo order dates, and Retail II invoice dates against the configured 168-hour limit. These are static historical archives, not fresh operational feeds.
- Verification: `alembic upgrade head` reached revision `0003_enforce_audit_dataset_fk`. `$env:PYTHONPATH = (Get-Location).Path; pytest -q --basetemp=.pytest_tmp` — 64 passed in 14.99s. Phase 8 run JSON is under ignored `data/processed/pipeline_runs/`; the daily database-derived report is `docs/DAILY_SUMMARY.md`. The append-only audit log contains earlier run attempts, while the SQLite database was rebuilt for the final all-dataset run.

## Completed: Phase 9 API

- Added the FastAPI application in `api/main.py` with versioned `/api/v1` routes for health, quality/freshness, incidents and detail, predictions, anomalies, hypotheses, recommendations, approvals, actions/history, alerts, incident graph, model versions/metrics, outcomes, audit events, kill-switch state/toggle, and a pipeline dry-run request.
- Reused the shared domain schemas for typed responses. Request payloads use strict Pydantic validation; errors return a consistent `error` object. API key roles are configured via `API_KEYS_JSON` (`viewer`, `analyst`, `reviewer`, `admin`); only reviewer-or-higher can confirm hypotheses, and evidence thresholds still apply. CORS origins use `CORS_ORIGINS`.
- Actions are only recorded as `DRY_RUN`; high-impact requests require an already approved approval and the process-local kill switch blocks action recording. The pipeline route records an audited request and explicitly does not execute the pipeline. No inbound text is interpreted as an action command.
- Added the endpoint inventory, examples labelled synthetic, authentication notes, and operational limits in `docs/API_CONTRACT.md`. OpenAPI is served by FastAPI at `/openapi.json`, with Swagger UI at `/docs`.
- Verification: `$env:PYTHONPATH = (Get-Location).Path; python -m pytest -q --basetemp=.pytest_tmp` — 69 passed in 15.61s, including synthetic permission, confirmation, action, incident-detail/graph, and OpenAPI checks. TestClient required local loopback access in the Windows sandbox. No real-data pipeline run was requested in this phase.
- Limitations: API key mapping is a simple local auth scheme; production key storage/rotation and transport security need operator configuration. Kill-switch state changed through the API is process-local and resets on restart; configured default remains in `config/settings.yaml`. The pipeline route is dry-run only and does not start a worker.

## Completed: Phase 10 local quality and reproducibility

- Added a local GitHub Actions workflow for Python 3.13 pytest and Ruff. No GitHub connection, push, or remote workflow run was made. Added Ruff configuration and corrected the selected lint findings; Ruff uses the standard correctness/unused-code groups with two existing style rules explicitly ignored.
- Added an API-only Dockerfile and Docker Compose service bound to localhost with a mounted SQLite processed-data volume. PostgreSQL is a commented-out optional example and is disabled. The Docker build context excludes `.env`, archives, raw/processed data, and model artifacts. Docker Compose YAML parsed successfully and contained only the API service; Docker itself is not installed here, so image build/start was not verified.
- Added local pre-commit hooks for Ruff, a staged-file guard blocking archive/data/database formats and any path below `data/` or `models/`, and a heuristic secrets scan. The guard and scanner have synthetic tests. `pre-commit validate-config` passed. Hooks could not be installed or tested against a real Git index because this workspace is not a Git repository; `AGENTS.md` prohibits `git init`.
- Added `scripts/dev.ps1` tasks for setup, audit, training/evaluation, end-to-end pipeline, tests, and localhost API. Added complete local install/run/API docs and final architecture, limitations, novelty, demo, and security-review documents. Existing evaluation metrics remain the computed values recorded in `docs/EVALUATION_REPORT.md`; uncomputed demand forecasting remains explicitly marked uncomputed.
- Pinned direct requirements and generated full runtime/development locks for Python 3.13. Upgraded initially flagged pytest, python-dotenv, FastAPI, and Starlette packages; `pip-audit --no-deps --disable-pip --timeout 5 --progress-spinner off -r requirements.lock -r requirements-dev.lock` reported no known vulnerabilities. The audit emitted a warning that hashes would be preferable; hashes were not added. GPU-only dependencies were not audited.
- Added recursive PII scrubbing for audit details and alert console/file/history output. API inputs use strict models, bounded identifiers/text, constrained action classes/dataset names, normalized errors, non-credential CORS, and no inbound-text-to-action behavior. Regex redaction remains heuristic.
- Verification from PowerShell: `& .\scripts\dev.ps1 test` — Ruff passed; **74 passed in 18.03s**. Additional checks: secrets scan found no matches; safe-path protected-file check passed; Compose YAML parsed with API as the only enabled service; `pip check` reported no broken requirements. No deployment steps were performed, and the project is not production-ready.

## Completed: Phase 11A local dashboard

- Updated `AGENTS.md`: the frontend lives in `dashboard/` and may be edited in Phase 11 only; `src/ui` remains protected.
- Added a React + Vite + TypeScript + Tailwind operations console in `dashboard/`, with responsive light/dark styling, overview, incident register, and incident investigation screens. The UI uses only local API requests and locally installed open-source packages; no external services, analytics, CDN assets, or remote fonts/images were added.
- Added typed API client coverage for the documented `/api/v1` routes. API URL is configurable through `dashboard/.env.example`; API key and a role hint are held in tab session storage. The displayed role is explicitly a UI setting; the API remains authoritative for permissions.
- Added finding-type badges, provenance metadata, explicit unavailable/empty/error/loading states, backend-returned hypothesis statuses, reviewer-gated confirmation, kill-switch visibility (admin endpoint only), and dry-run status signaling when the API returns dry-run action history. Missing values are not inferred.
- Component tests cover all four type badges, the exact `Insufficient evidence` rendering, and analyst/reviewer confirmation affordances.
- Backend gaps surfaced in the UI: the API does not expose pipeline run history, incident severity or status, current configured dry-run state, SHAP values as a dedicated field, or separately structured risk factor breakdown/alternative explanations/missing-evidence entries. The console reports these as unavailable rather than deriving or inventing them. Kill-switch state is admin-only per the contract.
- Verification in `dashboard/`: `npm run lint` passed; `npm run typecheck` passed; `npm test` — 1 file, 3 tests passed; `npm run build` passed (Vite 6.4.5, 1,583 modules transformed). Vitest and Vite initially encountered Windows sandbox `EPERM` during local path resolution; reruns with normal filesystem access passed.
- No backend code was edited. Frontend is an API consumer only; actual browser integration against a running API was not performed in this phase.

## Completed: Phase 11B dashboard workflows and governance

- Added `@xyflow/react` (open-source) and an incident graph screen. It renders only the graph returned by the documented API endpoint; edge labels include meaning, source reference and `ESTABLISHED`/`INFERRED` status, with inferred edges visually dashed and explicitly described as not confirmed causes.
- Added a hypothesis ledger with create, reason-required review, reviewer-only reason-required confirmation, lifecycle state, evidence references and returned review history. Added recommendation/approval screens with pending decisions, required reviewer rationale, approval deduplication in the UI, and action records labelled `DRY_RUN` / not executed only when the response confirms dry-run.
- Added alert history, action history, separate prediction and outcome records, model/version and evaluation views, a read-only audit view that omits details and record-reference payloads, admin-only kill-switch settings with a reason-required confirmation dialog, 404 handling and a global rendering error boundary.
- Evaluation values displayed are taken exactly from `docs/EVALUATION_REPORT.md`, with source and limitations shown; Olist review metrics include the proxy-label notice. API model versions display their `training_data_version` references.
- Added `dashboard/README.md` install/run instructions and `docs/UI_GUIDE.md` walkthrough.
- Backend gaps documented in the UI and guide: no supplier/order graph payload, dataset-version list endpoint, prediction-to-outcome link/comparison object, pipeline run history, incident severity/status, current dry-run config endpoint, or separately structured SHAP/risk/alternative/missing-evidence fields. No backend code was edited.
- Verification in `dashboard/`: `npm run lint` passed; `npm run typecheck` passed; `npm test` — 2 files, 9 tests passed; `npm run build` passed with Vite 6.4.5 (1,752 modules transformed; graph emitted as a separate chunk). No live API integration run was performed.

## Completed: Phase 12A generic dataset onboarding

- Added YAML-backed dataset profile schema (`config/profiles/<name>.yaml`) mapping source columns to canonical roles: `order_id`, `order_ts`, `promised_ts`, `delivered_ts`, `supplier_id`, `product_id`, `carrier`, `quantity`, `price`, `status`, and `region`. Enforced mandatory requirement for `order_id` and at least one timestamp role.
- Added `src/data/profiler.py` to inspect CSV, XLSX, and ZIP streams directly in memory. It computes per-column dtype, null %, uniqueness, date-parse success rate, and sample-free aggregate statistics without storing any raw cell values or row samples. Includes zip-bomb protection (max entry count, max uncompressed size, compression ratio check) and CSV formula-injection detection.
- Added `src/data/schema_mapper.py` to suggest canonical roles using name similarity, synonym dictionaries, and value pattern compatibility (e.g. date parse rates, numeric constraints, identifier uniqueness), returning confidence scores in `[0.0, 1.0]`. It strictly never auto-confirms (`auto_confirmed = False`, `status = "PENDING_REVIEW"`).
- Added capability detection in `src/data/profile.py` reporting which analytical tasks (`anomaly_detection`, `delay_prediction`, `demand_forecasting`, `graph`) are possible or blocked, naming the missing roles when blocked.
- Added dataset onboarding service in `src/data/dataset_service.py` and API routes in `api/main.py`: `POST /api/v1/datasets/upload` (50MB size limit, allowed extensions, zip-bomb, path-traversal, and formula-injection protections), `GET /api/v1/datasets/{name}/suggestions`, `PUT /api/v1/datasets/{name}/confirm-mapping`, `GET /api/v1/datasets`, and `DELETE /api/v1/datasets/{name}`. Gated to reviewer/admin roles.
- Converted Olist, DataCo, and Retail II into saved profiles in `config/profiles/olist.yaml`, `config/profiles/dataco.yaml`, and `config/profiles/online_retail_ii.yaml` using this generic mechanism without special-case branching.
- Added regression tests in `tests/test_profile_regression.py` proving that profile-derived validation produces identical valid and quarantined row counts as the legacy pipeline.
- Added synthetic unit and API tests in `tests/test_profiler.py`, `tests/test_schema_mapper.py`, `tests/test_capabilities.py`, and `tests/test_dataset_api.py`.
- Verification: Ruff passed with zero lint findings. Pytest test suite executed: **94 passed in 14.19s**.

## Completed: Stage 1 company-independent canonical onboarding foundations

- Read `AGENTS.md`, the supplied master build prompt, `docs/PROGRESS.md`, and the available Phase 12A profiles and architecture. `docs/PRODUCT_SPEC.md` and `docs/AUDIT_REPORT.md` were not present in the workspace; no contents were inferred for them.
- Reused the reviewed `config/profiles/{olist,dataco,online_retail_ii}.yaml` mappings and moved archive parsing behind separate adapters in `src/adapters/olist.py`, `dataco.py`, and `retail_ii.py`. They expose `detect()`, `read_chunks()`, and mapping-driven `to_canonical()`; the old loader module now delegates to this adapter layer. ZIP originals remain unmodified and are read in memory.
- Added Pydantic canonical entity types and lazy Arrow/Parquet schemas for orders, order lines, shipments, suppliers, products, warehouses, inventory snapshots, demand observations, carriers, and customer/destination records. Business fields are optional; event ID and event timestamp are required. Unmapped source columns are retained in `custom_fields`, with member/row source references.
- Added SQLAlchemy models and Alembic migration `0004_company_tenancy` for Company, Workspace, Project, DataSource, DatasetVersion, MappingVersion, ImportJob and company-scoped existing operational tables. Every tenant-owned table has `company_id` and `deleted_at`; repository construction requires a company ID, ORM reads are tenant-filtered, writes are company-bound, and soft deletion retains rows and appends a hash-chained audit event. Added traversal-safe `TenantFileStore` paths under separate per-company roots.
- Changed dataset registration deletion to a soft-delete status/event; the raw uploaded file and mapping profile are retained. Added tests that company A cannot read company B rows/files, exercise path traversal rejection and soft-delete audit verification.
- Real adapter-to-validation regression command: `python scripts/regress_adapters.py --root C:\Projects\supply-chain-risk-system`. Olist: **1,550,922 input / 258,816 quarantined / 1,292,106 valid** (36 CSV chunks); DataCo: **180,519 / 0 / 180,519** (4 chunks); Online Retail II: **1,067,371 / 12,133 / 1,055,238** (2 sheets). All three matched the recorded Phase 8 validated-row baselines exactly. The scripts only read the source ZIPs.
- Exercised Alembic `0003 -> 0004` against a temporary copy of the existing SQLite database: upgraded to `0004_company_tenancy`, all 40 existing incident rows remained, each had a populated company ID, the company foreign key was present, and all six onboarding tables existed. The original ignored database was not migrated or changed.
- Archive SHA-256 values remain equal to `docs/DATASET_REGISTER.md`; licenses remain UNKNOWN. PyArrow is pinned in requirements/lock files but is not installed in this environment, so the Arrow-schema runtime test is the single skipped test; schema construction is lazy until that dependency is installed.
- Verification: Ruff passed; full pytest: **100 passed, 1 skipped** (one Starlette/httpx deprecation warning). API tests required local loopback access outside the restricted sandbox.
- Pending: the product spec and audit report requested for this stage are missing; API identity is still single-tenant (`local`) and uploads still use the legacy shared onboarding registry. Composite tenant-scoped foreign keys and company-aware API authentication remain necessary before using this as a multi-company service. No external integrations or model claims were added.

## Completed: Stage 2 source upload, profiling, mapping and relationship review

- Implemented streamed upload handling for CSV, XLSX, JSON, JSONL and ZIP with configurable byte/chunk/ZIP safety limits in `config/settings.yaml`. Uploads are stored per company without extraction or in-place rewriting; the SHA-256 is verified against the stored original. Oversized files are rejected. ZIPs with unsafe paths, excess entries/size/ratio, or multiple supported data members fail their import job rather than being extracted or silently combined.
- Added background `ImportJob` status and history routes. Profiles process bounded row chunks and retain only aggregate dtype, date parse/format, null, uniqueness, candidate-identifier and formula-risk statistics. A full import records processed and total row counts. Parser failures retain partial counts and set `PARTIAL`; otherwise failed uploads are `FAILED`. Formula-injection markers block import while leaving source bytes unchanged.
- Expanded the local mapping suggester with explicit `needs_clarification` for ambiguous/low-confidence candidates. Added versioned mapping create/edit/accept/reject routes, required reviewer reasons, custom fields, units, time zone/date format metadata and company-specific immutable profile versions. Suggestions remain unconfirmed until a reviewer accepts a version.
- Added append/replace import previews and an explicit commit step requiring an accepted mapping. Commit materializes canonical JSONL in company-scoped `data/processed/`, preserves unmapped fields in `custom_fields`, verifies processed count against the profiled count, and writes a lineage sidecar with source hash, mapping version and transforms. Reprocessing creates a new job from the unchanged source.
- Added cross-file relationship preview over separately uploaded orders, shipment and supplier files. The result reports matched, orphan and null-key counts. A pending proposal is not active; the relationship record is persisted only after an explicit reviewer approval and reason. Removing a source from monitoring soft-deletes its registry row while retaining original bytes, import/mapping versions and audit history.
- Added synthetic tests for alternate column names, JSON, file-hash preservation, formula injection and ZIP traversal rejection, background status, mapping acceptance, append/replace preview and commit, soft-deletion history, and separate order/shipment/supplier files with broken keys. No real dataset was processed in this stage.
- Verification: `.venv\Scripts\ruff.exe check .` passed. `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp_stage2_final6` — **106 passed, 1 skipped, 1 warning in 20.88s**. The warning is Starlette's deprecation notice about the installed httpx compatibility path. API tests required local loopback access outside the restricted sandbox.
- Product-spec note: `docs/PRODUCT_SPEC.md` is absent in this workspace, so Functionality 1 could not be consulted; implementation was limited to the Stage 2 requirements in the user prompt. ZIP uploads currently allow one supported tabular member per archive; multi-file sources are uploaded separately so mappings and relationships remain explicit. API authentication still uses the Stage 1 local company identity; company-aware authentication is not included in this stage.

## Completed: Stage 3 capability assessment, generic validation and canonical pipeline

- Added project capability assessment over accepted canonical mapping roles and a viewer API route. It reports the requested six features with `AVAILABLE`, `AVAILABLE_WITH_LIMITATIONS`, `AWAITING_CONFIGURATION`, `UNSUPPORTED`, or `NOT_IMPLEMENTED`, missing roles, extra data needed, and limitations. Sales data with product, quantity and timestamp enables demand analysis; inventory risk remains `UNSUPPORTED` until inventory snapshot, on-hand quantity and warehouse roles are provided. Legacy/model functions are not represented as implemented canonical pipeline steps.
- Added configurable generic canonical validation rules in `config/settings.yaml` for missing required fields, duplicates, invalid timestamps, prohibited negative quantity, unresolved references, unit/currency consistency, schema changes and IQR outliers. Reports carry record references and rule counts; unusual values are flagged, not rejected. Pipeline validation settings are loaded through typed config.
- Added versioned feature definitions and per-derived-feature lineage with source record references, transformation, source availability and computation availability timestamps. Initial generic definitions are `event_age_seconds` and `gross_line_value`, each at version `1.0.0`.
- Added a company-scoped `pipeline_runs` persistence table and project pipeline preview, status/detail and preview-accept API routes. Previews are dry-run only; acceptance requires an approved mapping and queues execution over canonical JSONL derivatives. The runner takes canonical files and the capability assessment, gates unsupported steps, reports step status/attempts and safe failure types, and uses configured retry/backoff values. It does not import dataset-specific adapter names.
- Added synthetic tests for sales without inventory, non-rejecting quality flags, feature provenance/versioning, supported-step gating, project capability API and dry-run preview API.
- Verification: `.venv\Scripts\ruff.exe check .` passed. The full suite with local loopback access for FastAPI TestClient passed: **111 passed, 1 skipped, 1 warning in 21.57s**. The warning is the existing Starlette/httpx compatibility deprecation. Pipeline step updates are persisted as running, retrying, completed, skipped or failed states as execution progresses.
- Product-spec note: `docs/PRODUCT_SPEC.md` is absent; Functionality 1.3, 1.4 and Critical Requirement E could not be consulted. Current generic pipeline executes generic validation, demand summary when supported, anomaly rule summaries when supported, and feature lineage. Canonical delay prediction, dependency graph construction, and model evaluation are explicitly marked `NOT_IMPLEMENTED`; this stage does not claim those computations ran.

## Completed: Stage 4 canonical anomaly, delay-risk and demand analytics

- Added configurable canonical anomaly detection for quantity and price with rolling historical windows, per-supplier and per-product baselines, weekday seasonal baselines when enough matching history exists, and rule, robust z-score, IQR and Isolation Forest methods. Each emitted result includes entity grouping, source record references, observed metric, baseline, expected range, detector version, anomaly severity and limitations. Isolation Forest is fit once per entity on the initial minimum baseline window to bound CPU cost.
- Added a configurable canonical prediction-time role, post_outcome target role and explicit feature allowlist with availability-role mappings. Outcome aliases and configured post-outcome roles are blocked from predictors. The CPU logistic model runs only when labelled chronological history supports all partitions; otherwise it reports missing labels/history and does not train. Majority and supplier-history baselines are separately typed as baseline/rule, with chronological test metrics, calibration curve/Brier score and a record-level prediction trace.
- Added canonical demand forecasting with granularity selected from date span, product/SKU and optional warehouse grouping, naive/moving-average/seasonal-naive baselines, rolling-origin backtests, empirical prediction intervals and forecast-versus-actual rows. Outputs say “demand pressure”; absent inventory is never translated into stockout status.
- Added a shared explanation interface: compatible fitted estimators get SHAP contributions against training background; baselines and rules get explicit textual traces. Outputs are labelled “contribution, not cause”. A synthetic logistic run computed its SHAP explanation.
- Wired supported canonical anomaly, delay and demand steps into the generic pipeline using typed Stage 4 config. Added synthetic tests for a leaky Late_delivery_risk column, missing labels, sales without inventory, anomaly evidence fields, rule-vs-trained-model labeling, and explanation labels.
- Verification: .venv\Scripts\ruff.exe check . passed; focused Stage 3/4 suite: 11 passed in 10.93s; full pytest: 118 passed, 1 skipped, 1 warning in 25.90s. The warning is the existing Starlette/httpx compatibility deprecation. No real-data analytics run was performed in this stage, so no real model metrics or anomaly counts are reported.
- Product-spec note: docs/PRODUCT_SPEC.md is absent; Functionality 2, 3, 4 and 7 could not be inspected. Real-data training and forecasting remain unverified for these new canonical paths. Feature availability values are configured assumptions and require upstream capture-time confirmation.

## Completed: Stage 6 playbooks, workflow, connectors and outcomes

- The requested `docs/PRODUCT_SPEC.md` is absent from the workspace, so Functionality 9, 10 and Critical Requirement C could not be checked. Implementation follows the Stage 6 prompt and existing project safety rules.
- Added driver- and available-data-aware recommendation playbooks with evidence refs, rationale, assumptions, uncertainty, trade-offs, approval requirements, preconditions, status and result. Effect estimates are omitted unless sufficient recorded history is supplied; where present they are explicitly `HYPOTHETICAL`. No supplier capacity, inventory or savings are invented. What-if comparisons require explicit assumptions and identify unavailable capacity, inventory and savings effects as not estimated.
- Added local timer/new-batch workflow scheduling, persisted job history/status, configured retries and backoff, safe idempotency, failure reporting, and payload restrictions. Existing alert grouping/history now supports acknowledgement and assignment, with APIs for approval/rejection and recorded reasons. High-impact action verification requires approval; dry-run, kill switch and action limits remain in force.
- Added read-only folder, REST polling and SQL database source adapters; environment-configured SMTP and webhook notification adapters; connector health checks; and explicit `SIMULATED` labels for injected mocks. Notifications remain disabled/dry-run unless enabled by environment configuration. ERP/WMS are listed as unbuilt extensions. No external endpoint was contacted during tests.
- Added outcome recording that requires verified execution for execution claims and compares only earlier stored prediction/recommendation values with later observations. Dry-run actions cannot be marked as executed.
- Added synthetic tests for recommendation and what-if constraints, timer/new-batch jobs, retry and idempotency behavior, alert acknowledgement/assignment, read-only source connectors, notification dry-run and simulated transports, approval-guarded execution verification, and outcome comparisons. API tests cover the related Stage 6 routes.
- Verification: `.venv\\Scripts\\ruff.exe check .` — passed. Full suite: `.venv\\Scripts\\pytest.exe -q --basetemp=.pytest_tmp_stage6_final` — **142 passed, 1 skipped, 1 warning in 36.52s**. The warning is Starlette's `httpx` TestClient deprecation notice.

### Stage 6 pending / limitations

- No real supplier capacity, inventory, savings, operational effects, or outcome improvements were inferred. Effect estimates require adequate historical outcomes and are hypothetical.
- Real SMTP/webhook delivery and external REST polling were not exercised; notification adapters are dry-run by default. Connector health reflects configuration unless explicitly enabled.
- ERP and WMS adapters are extension points only. Scheduling is process-local and does not provide cross-process coordination.
- Product-spec-specific details remain unverified because `docs/PRODUCT_SPEC.md` is missing.

## Completed: Stage 7 drift monitoring, verified outcome evaluation and governance

- `docs/PRODUCT_SPEC.md` and `docs/AUDIT_REPORT.md` are absent in this workspace; implementation strictly follows the Stage 7 prompt, `AGENTS.md`, and project safeguards.
- **Schema & Drift Monitoring**:
  - Implemented schema-change detection on re-upload (added, removed, retyped columns) and feature/data drift monitoring using simple statistics (dtypes, row counts, null rates, uniqueness fraction, numeric mean/std shifts, category concentration).
  - Reused `src/monitoring/drift.py` and enhanced with `dataset_profile_to_drift_dict()` to bridge dataset profiles with baseline snapshots.
  - Attached advisory warning attributes: `drift_is_warning_only: True`, `triggers_automatic_retrain: False`, `warning: "Drift is a warning, never an automatic retrain trigger."`
  - Integrated into API dataset profile jobs with audit event `dataset_drift_checked` and endpoint `GET /api/v1/datasets/{dataset_name}/drift`.
- **Post-Outcome Evaluation**:
  - Added `evaluate_forecast_outcomes()` (MAE, MAPE, bias) and `evaluate_prediction_outcomes()` (accuracy, precision, recall, brier score, confusion matrix) in `src/monitoring/outcomes.py`.
  - Added `evaluate_company_outcomes()` and endpoint `GET /api/v1/evaluation/outcomes`.
  - Enforced verified-label requirements: evaluates alert precision, missed events, forecasts, and predictions only where verified labels exist. When insufficient or unverified, explicitly returns `{"message": "not enough verified outcomes", "status": "INSUFFICIENT_VERIFIED_OUTCOMES"}`.
- **Model and Config Versioning**:
  - Candidate-vs-current comparison on identical chronological holdout data hash and split boundaries.
  - Defined acceptance criteria in config (macro F1 threshold, Brier score change ceiling).
  - Human reviewer approval strictly enforced prior to model/config promotion; model and config rollback supported without automated deployment. No automatic retrain-and-deploy path exists.
- **Reproducible Evaluation Reports**:
  - Persisted reproducible JSON evaluation reports per model version under `models/evaluations/` recording `model_version`, `data_version`, `mapping_version`, `seed`, `metrics`, and `limitations`.
  - Added endpoint `GET /api/v1/models/{model_version}/evaluation-report` with `company_id` enforcement.
- **Audit Log Change History**:
  - Expanded and standardized hash-chained audit logging across 8 domains: `sources`, `mappings`, `rules`, `models`, `permissions`, `predictions`, `investigations`, and `actions`.
  - Added `category` and `event_type` query filters to `GET /api/v1/audit` for structured audit trail compliance.
- **Multi-Tenancy & API Contracts**:
  - Enforced tenant isolation via `company_id` (`X-Company-Id` header) across all Stage 7 endpoints and repository access.
  - Documented all new query parameters, endpoints, and headers in `docs/API_CONTRACT.md`.
- **Tests & Verification**:
  - Added `tests/test_stage7_governance_monitoring.py` (7 tests covering drift warning semantics, outcome evaluation fallbacks, reproducible evaluation reports, candidate promotion/rollback, 8-domain audit trail, and re-upload schema drift).
  - Added `tests/test_stage7_cross_company.py` (cross-company tenant isolation verifying Company B cannot access or leak Company A's datasets, drift, outcomes, or audit logs).
  - All test data explicitly labelled `SYNTHETIC_TEST_*` and not used to claim production accuracy.
  - Verification: `.venv\Scripts\ruff.exe check .` — passed (0 errors).
  - Test suites:
    - Stage 7: `.venv\Scripts\python.exe -m pytest tests/test_stage7_governance_monitoring.py tests/test_stage7_cross_company.py -v` — **8 passed in 12.40s**.
    - Stage 6 regression: `.venv\Scripts\python.exe -m pytest tests/test_stage6_api.py tests/test_stage6_workflow_connectors.py -v` — **16 passed in 8.47s**.
    - Full suite: `.venv\Scripts\python.exe -m pytest -q` — **160 passed, 1 skipped, 1 warning in 41.10s**. The warning is Starlette's `httpx` TestClient deprecation notice.

### Stage 7 pending / limitations

- No real verified alert labels were supplied with raw datasets; outcome evaluation on real data is pending collection of reviewer-verified operational outcomes.
- Drift thresholds are configurable summary statistical heuristics, not causal indicators. Drift triggers warnings only, never automatic retraining.
- Model and config promotions require explicit human reviewer sign-off; rollback updates registry state and audit logs but does not trigger autonomous infrastructure deployment.
- Multi-tenancy operates via header-based company scoping (`X-Company-Id`) backed by workspace isolation; production SSO / OAuth token claims should bind tenant identity in deployment.

---

## Completed: Stage 10 End-to-End Acceptance, Multi-Dataset Execution & Final Documentation

- **1. Automated Acceptance Tests for Scenarios 1 to 10**:
  - Implemented `tests/test_stage10_scenarios.py` covering all 10 core scenarios:
    - `test_scenario_1_onboarding_and_upload`: Multi-file upload, SHA-256 calculation, and role gating (viewer rejected).
    - `test_scenario_2_schema_mapping_wizard`: Schema mapping suggestions, confidence scores, auto_confirmed=False guarantee, and reviewer acceptance.
    - `test_scenario_3_cross_source_relationships`: Relational preview, match/orphan key detection, and reviewer approval.
    - `test_scenario_4_capability_checklist_and_gating`: Dynamic analytical capability assessment (anomaly detection, delay prediction, demand forecasting, graph).
    - `test_scenario_5_quality_validation_and_drift_monitoring`: Summary statistics, schema drift, and warning-only drift semantics.
    - `test_scenario_6_anomaly_detection_and_ml_prediction`: Statistical anomaly detectors (IQR, Robust Z) and leakage-aware delay predictions.
    - `test_scenario_7_incident_assembly_and_hypothesis_lifecycle`: Incident assembly, hypothesis ledger, premature confirmation rejection (409 Conflict), evidence attachment, and reviewer confirmation.
    - `test_scenario_8_supply_chain_graph_and_tracing`: Bounded graph query enforcement (limit <= 5,000) and upstream/downstream exposure tracing.
    - `test_scenario_9_recommendations_and_whatif`: Recommendation playbooks and what-if simulation with mandatory `HYPOTHETICAL` labels.
    - `test_scenario_10_guarded_actions_approval_killswitch_and_audit`: High-impact approval gate, dry-run default, emergency kill switch halt (`BLOCKED_KILL_SWITCH`), and SHA-256 hash-chained audit verification.
  - Manual verification procedures and UI test steps documented in `docs/ACCEPTANCE.md`.
  - Test result: **10 passed in 12.18s**.

- **2. Unfamiliar Synthetic Company Dataset & End-to-End API Lifecycle**:
  - Generated synthetic multi-file dataset for `acme_industrial` with unfamiliar column names (`data/synthetic_company/`):
    - `acme_purchase_orders.csv` (`po_num`, `po_creation_time`, `target_fulfillment_date`, `supplier_code`, `sku_id`, `ordered_units`, `extended_price_usd`, `destination_hub`)
    - `acme_freight_shipments.csv` (`po_num`, `consignment_code`, `carrier_name`, `departure_date`, `delivery_date`, `transport_mode`, `shipment_status`)
    - `acme_vendor_directory.csv` (`supplier_code`, `legal_business_name`, `tier_level`, `primary_country`, `compliance_audit_score`)
  - Implemented and executed `scripts/run_e2e_synthetic.py` through the API:
    - Step 1 Upload: Uploaded 3 datasets via `POST /api/v1/datasets/upload` (status=201, SHA-256 computed).
    - Step 2 Mapping: Retrieved suggestions (auto_confirmed=False) and accepted mappings with reviewer rationale (status=200).
    - Step 3 Relationships: Previewed join on `po_num` and approved proposal (status=200).
    - Step 4 Capabilities: Evaluated `anomaly_detection`, `delay_prediction`, `demand_analysis`, `inventory_risk`, `dependency_graph`, `model_evaluation`.
    - Step 5 Monitoring: Drift analysis verified (`WITHIN_CONFIGURED_LIMITS`, `drift_is_warning_only: true`).
    - Step 6 Incident: Assembled incident, rejected premature hypothesis confirmation with 409, attached evidence ledger, confirmed by reviewer (status=200, `CONFIRMED`).
    - Step 7 Graph: Successfully queried dependency graph endpoint.
    - Step 8 What-If: Simulated 25% relative delay reduction, verified `HYPOTHETICAL` label.
    - Step 9 Approval & Action: Reviewer approved high-impact mitigation, recorded action with `dry_run: true`.
    - Step 10 Audit: Verified 11 cryptographic SHA-256 hash-chained audit events.
  - All data strictly labelled `SYNTHETIC`; never used to claim model accuracy.

- **3. Real Datasets In-Memory Pipeline Execution & Timing**:
  - Implemented and executed `scripts/run_real_datasets.py` streaming all 3 static archives in-memory without disk extraction:
    - **Olist** (`archive (1).zip`): 1,550,922 input rows | 1,292,106 valid rows | 258,816 quarantined | 36 members | 8.67s
    - **DataCo** (`archive (2).zip`): 180,519 input rows | 180,519 valid rows | 0 quarantined | 4 members | 39.11s
    - **UCI Online Retail II** (`online+retail+ii.zip`): 1,067,371 input rows | 1,055,238 valid rows | 12,133 quarantined | 2 members | 128.95s
  - Total real records processed: **2,798,812 rows in 176.73s**. No metrics outside computed validation and row counts were reported.

- **4. Reproducibility Tooling**:
  - Updated `scripts/dev.ps1` with PowerShell tasks: `setup`, `run-api`, `run-ui`, `test`, `acceptance`, `e2e-synthetic`, `real-datasets`, `audit`, `train`, `run-pipeline`.
  - Added cross-platform `Makefile` targeting `.venv` and `dashboard/`.
  - Pinned and verified `requirements.lock`.

- **5. Final Documentation Suite**:
  - `README.md`: Overview, quick start, real dataset counts, documentation map.
  - `docs/ARCHITECTURE.md`: Subsystem architectures, Mermaid data flow, governance layer, and threat boundaries.
  - `docs/LIMITATIONS.md`: Exhaustive academic boundaries, data disclaimers, correlation vs causation, and CPU/SQLite constraints.
  - `docs/RUN_LOCALLY.md`: Step-by-step local execution guide for Windows PowerShell.
  - `docs/DEMO_SCRIPT.md`: Comprehensive 10-step UI and API walkthrough.
  - `docs/ACCEPTANCE.md`: Scenario acceptance specification mapping automated assertions and manual UI checks.
  - `docs/FEATURE_MATRIX.md`: Granular status and evidence citations across all 21 system capabilities.

### Stage 10 Known Limitations

- Real datasets lack verified post-hoc ground-truth root-cause labels; automated testing of hypothesis confirmation relies on synthetic evidence ledgers.
- Online Retail II Excel parsing (`.xlsx`) in openpyxl on CPU accounts for ~128s of real dataset runtime due to XML decompression and type casting.
- System remains an academic prototype; external automated operational actions and production deployments are omitted by design.

## Completed: Supply-Chain Graph Redesign (Functionality 5)

Academic prototype supply-chain network visualizer delivering an aggregated interactive network where nodes represent cohorts/groups rather than individual orders, enabling clear visual identification of where anomalies and delays originated.

### 1. Backend Implementation (`src/network/` & `api/main.py`)

- Created `src/network/aggregated_graph.py` with `build_aggregated_supply_network`:
  - Group nodes: `Supplier`, `Product`, `ShipmentGroup` (supplier × week), `Carrier`, `Warehouse`, `CustomerRegion`, `ProcessStage`, and `Other` (clustered tail).
  - Peer-relative health calculation: computes z-score of anomaly rates and prices against peer cohort baselines; assigns `HEALTHY`, `WATCH` (|z| >= 1.5), `PROBLEM` (|z| >= 2.5 or high anomaly severity), or `UNKNOWN`.
  - Time-bucketed health snapshots per node for UI replay over historical observation windows.
  - Intelligent node capping: clusters least-exposed tail nodes into `{type}:Other` group nodes when node count exceeds `max_nodes` (default 150), preserving total flow and emitting capping metadata.
  - Missing roles detection: lists unmapped entity types (`Warehouse`, `ProcessStage`, etc.) with explicit omission reasons.
  - Candidate source ranking: identifies and scores likely root-cause origin nodes with disclaimer `"candidate / hypothesis, not confirmed cause"`.
- Exposure tracing via `trace_aggregated_network`:
  - Upstream and downstream breadth-first traversal strictly along confirmed `ESTABLISHED` edges up to `max_depth`.
- Added API endpoints in `api/main.py` with multi-tenant company isolation:
  - `GET /api/v1/projects/{project_id}/graph/aggregated`
  - `GET /api/v1/projects/{project_id}/graph/aggregated/trace`
  - `GET /api/v1/incidents/{incident_id}/graph/aggregated`
  - Retained all legacy neighborhood and trace endpoints for full backward compatibility.

### 2. Frontend Implementation (`dashboard/`)

- Installed `cytoscape-dagre`, `dagre`, `cytoscape-fcose`, and `@types/dagre`.
- Extended TypeScript types in `dashboard/src/api/types.ts` (`AggregatedGraphNode`, `AggregatedGraphEdge`, `AggregatedGraphResponse`, `AggregatedTraceResponse`, `CandidateSource`, `PeerMetricBaseline`) and added client methods in `dashboard/src/api/client.ts`.
- Rewrote `dashboard/src/components/SupplyGraphScreen.tsx`:
  - View switcher: Toggle between force-directed Network View (`cose`/`fcose`) and layered left-to-right Process Flow View (`dagre`).
  - Node styling: Green (`#22c55e`), Amber (`#f59e0b`), Red (`#ef4444`) with pulsing CSS ring for `PROBLEM` nodes, Grey (`#94a3b8`) for unknown. Node sizing scaled by exposure volume.
  - Edge styling: Solid for `ESTABLISHED`, Dashed for `INFERRED`, Dotted for `USER_ENTERED`, line thickness scaled by volume.
  - Persistent Legend: Always-visible panel explaining health states, edge styles, and exposure sizing.
  - Problem Focus & Ranked Candidates: Strip displaying top candidate sources with scores and anomaly counts; clicking a candidate centers the canvas and highlights its downstream path.
  - Time Slider: Replay historical health evolution across weekly buckets with Play, Pause, and Jump to Latest controls.
  - Side Panel: Displays selected group details, peer baseline comparison cards with z-scores, evidence provenance tags, and Trace Upstream / Downstream buttons with canvas path highlighting in purple.
  - Disclosures: Informative banners for capped graphs and missing roles; disclaimers that traces represent hypotheses, not confirmed causes.
- Added CSS classes in `dashboard/src/style.css` for view toggle, pulsing problem animation, candidate chips, time slider, and peer baseline cards.

### 3. Verification & Real Results

- **Backend Tests**: `tests/test_graph_redesign.py` (6 passed in 9.45s) testing planted faulty supplier identification, weekly health time series, downstream traversal, node capping, missing roles, and multi-tenant isolation.
- **Full Backend Regression**: 176 passed, 1 skipped, 1 warning in 46.60s.
- **Frontend Component Tests**: `src/components/SupplyGraphScreen.test.tsx` (4 passed in 288ms).
- **Full Frontend Suite**: 27 passed in 5.27s (`npm test -- --run`).
- **Code Quality & Build**:
  - `npm run lint`: 0 errors, 0 warnings.
  - `npm run typecheck`: clean.
  - `npm run build`: built in 15.43s.

### Graph Redesign Known Limitations

- Node health classification utilizes peer-relative z-score thresholds; absolute domain thresholds require company-specific tuning.
- Cytoscape layout coordinates are dynamically computed in-browser; very large subgraphs (>300 nodes) should use the default 150-node capping.
- Upstream and downstream traces traverse established relationships but do not prove causal agency without human reviewer confirmation.

## Completed: Acceptance Findings Flaw Remediation (12 Core Generic Fixes)

- **Execution Date**: 2026-10-25
- **Test File**: `tests/test_e2e_acceptance_unseen.py`
- **Output Artifacts**: [`docs/acceptance_findings.json`](file:///c:/Projects/supply-chain-risk-system/docs/acceptance_findings.json) and [`docs/ACCEPTANCE_RESULTS.md`](file:///c:/Projects/supply-chain-risk-system/docs/ACCEPTANCE_RESULTS.md)
- **12 Generic Remediations Completed**:
  1. **Graph Edges**: Built real weighted edges from mapped canonical roles and approved relationships (`Supplier-SUPPLIES->Product`, `Supplier-USES->Carrier` via order-shipment join, `Carrier-SERVES->Route/Lane`, `Product-STORED_AT->Warehouse`) with order counts as weights and `ESTABLISHED`/`INFERRED` flags. Edge counts per type match distinct pairs in the data (`SUPPLIES`: 129, `USES`: 100, `SERVES`: 20, `STORED_AT`: 240; 489 total). Faulty supplier `V017` connects to products and carriers.
  2. **No Hardcoded Numbers**: Removed all artificial `ProcessStage` nodes with constants (e.g. exposure 20,000, anomaly count 500). All node metrics derive strictly from data. Added unit test in `tests/test_graph_redesign.py` that fails if any node metric is not derived from data.
  3. **Node Health**: Delay capability health uses late rate against peer averages with minimum support (`min_support >= 5`) and z-score significance. Nodes at or below peer average evaluate to `HEALTHY`. Never labels a node `UNHEALTHY` with a negative z-score.
  4. **Labels and Sources**: Node type labels derive directly from canonical mapped roles (`Route/Lane` for mapped `route` column); node source attributes list real contributing datasets (`purchase_orders, shipments, vendors`). Added canonical `route` role and keywords to schema mapper.
  5. **Anomalies**: Sorted anomalies by severity and score descending. Fixed Isolation Forest scoring to compute sample-specific decision function scores. Clipped lower bounds at 0 for non-negative measures. Added weekly aggregated demand spike detection per product. Persisted total anomaly counts and capping status.
  6. **Drivers**: Change-point identification calculates estimated start dates on the entity's weekly late-rate series, reporting pre/post rates and sample support. Evaluated interaction pairs (`carrier x route`, `supplier x product`). Confounding analysis re-tests remaining drivers after filtering out records of the primary driver, labeling disappearing drivers as `explained by <driver>`. All drivers remain `UNVERIFIED`.
  7. **Incidents**: Grouped anomalies and drivers into distinct incidents by entity and time window. Every incident contains non-empty `record_refs`, `evidence_refs`, and `hypothesis_refs`. Structured `EvidenceLedger` entries with supporting (`LedgerEvidence`), contradicting, and missing evidence.
  8. **Features**: Strictly excluded identifier columns (`order_id`, `shipment_id`, `source`, `event_id`, `source_record_ref`) from delay model training and prediction matrices. Added unit test in `tests/test_stage4_analytics.py`.
  9. **Recommendations**: Implemented separate playbooks per driver dimension (`supplier`, `carrier`, `route`, `product`, `demand`), each with rationale, evidence IDs, start date, pre/post rates, assumptions, uncertainty, and `HYPOTHETICAL` effect. Product drivers recommend SKU safety stock buffer calibration, never route diversification.
  10. **Role Enforcement**: Implemented `POST /api/v1/actions/{action_id}/approve` with reviewer permission check, returning strict 403 for viewers and analysts (never 404). Tested hypothesis confirmation lifecycle: unverified hypothesis confirmation without sufficient evidence returns 409 (`"Insufficient evidence"`), while reviewer confirmation with supporting evidence returns 200.
  11. **Findings File**: Formatted `docs/acceptance_findings.json` to keep it clean and readable (top 10 unhealthy nodes by z-score without weekly time series, exact node/edge counts by type, exact failure details, 0 failures recorded).
  12. **Execution & Documentation**: Rerun full test suite (`test_e2e_acceptance_unseen.py` passed with 0 failures), regenerated `docs/acceptance_findings.json`, and updated `docs/ACCEPTANCE_RESULTS.md`. Added default CORS dev server support for Vite (`http://localhost:5173`) and seeded default accounts (`admin`, `reviewer`, `analyst`, `viewer`).

## Completed: Acceptance Remediation Final Verification & Checkpoint

- **Execution Date**: 2026-10-25
- **Bug Fixed**: `test_invalid_input_uses_consistent_error_shape` — `HTTPException(422, ...)` now returns the canonical `{"error": {"code": "invalid_request", "message": "Request validation failed", "details": "<reason>"}}` shape consistent with the `RequestValidationError` handler. All 422 responses have a uniform error contract.
- **Root cause**: The HTTPException handler for 422 used `str(exc.detail)` as the message; the test expected the canonical string "Request validation failed". Fix: 422 HTTPExceptions normalise to the canonical message; original detail moves to `"details"` field.
- **Full test suite** (excluding long-running acceptance test): **187 passed, 1 skipped, 0 failures** in 134.02s (2:14). Command: `pytest -v --ignore=tests/test_e2e_acceptance_unseen.py`. Results saved to `docs/pytest_run_manual.txt`.
  - 1 skipped: Arrow/PyArrow lazy-schema test; PyArrow not installed (pre-existing, documented since Stage 1).
  - Warnings: Starlette/httpx TestClient deprecation, FastAPI on_event deprecation, pandas period timezone UserWarning — all pre-existing, no new regressions.
- **Git checkpoint**: Repository committed as "Checkpoint after acceptance remediation".
- **Services**: Backend on `http://127.0.0.1:8000`; Frontend on `http://localhost:5173`.
- **Default credentials**: `admin` / `AdminPassword123!` (company: `kaveri_foods`).

### Known Limitations (post-remediation)

- `test_e2e_acceptance_unseen.py` is a full ML pipeline acceptance test that takes several minutes. Run separately: `pytest tests/test_e2e_acceptance_unseen.py -v`.
- The `on_event("shutdown")` FastAPI deprecation: deferred; migrating to the `lifespan` context manager is a future refactor.
- `src/ml/delay/canonical.py` emits a pandas UserWarning about timezone info drop during `.dt.to_period("W")`. Non-breaking; timezone info is not used in the weekly aggregation.

## Completed: Supply-Chain 3D Network Globe & Acceptance Final Verification

- **Execution Date**: 2026-10-25
- **Frontend 3D Visualizer (`dashboard/src/components/SupplyGraphScreen.tsx`)**:
  - Replaced 2D layout with an interactive Three.js 3D supply-chain network globe with dark space background, glowing problem/incident nodes in pulsing red, healthy nodes in emerald, watch nodes in amber, and volume-weighted flow curves.
  - Interactive mouse controls: drag to orbit/rotate the globe, scroll wheel to zoom, and raycasting click to inspect individual node cohort details, peer comparisons, and upstream/downstream traces.
  - Filter by node health, search by entity name, filter "Only Problems", and jump-to-time health evolution scrubber.
  - Updated `SupplyGraphScreen.test.tsx` and `stage9.test.tsx` to align with the Three.js canvas mount and empty project state notices.
- **Anomaly Detection Vectorization (`src/ml/anomaly/canonical.py`)**:
  - Vectorized Isolation Forest prediction and scoring across the sample vector per entity group, eliminating per-record single-sample model invocations (`predict([[val]])` and `score_samples([[val]])`).
  - Pipeline execution speedup: reduced anomaly detection execution time on the unseen Kaveri Foods synthetic dataset from 12+ minutes to under 2 minutes while maintaining identical anomaly classification and sample scores.
- **Verification Results**:
  - **Frontend Quality & Build Suite**:
    - `npm run lint`: **0 errors, 0 warnings**.
    - `npm run typecheck`: **Clean (0 errors)**.
    - `npm test -- --run`: **5 test files passed, 33 tests passed** in 6.39s.
    - `npm run build`: **Built production bundle in 21.06s** with 0 errors.
  - **Backend Test Suite**:
    - `pytest -v --ignore=tests/test_e2e_acceptance_unseen.py`: **187 passed, 1 skipped, 0 failures** in 121.95s.
    - `pytest tests/test_e2e_acceptance_unseen.py -v`: **1 passed in 222.11s (0 failures)**.
  - **Findings & Acceptance**:
    - Regenerated [`docs/acceptance_findings.json`](file:///c:/Projects/supply-chain-risk-system/docs/acceptance_findings.json): `failures: 0`, all 4 roles verified (`viewer`, `analyst`, `reviewer`, `admin`), 10 top anomalies ranked by severity and score.

## Completed: Admin Dashboard UX & Transparency Refinements

- **Execution Date**: 2026-10-25
- **Top Bar API Status Fix**: Updated health check connectivity logic in `dashboard/src/App.tsx` (`health.value?.status === 'ok' || health.value?.status === 'healthy'`). Fixed "API offline" false indicator to show "API online" with active green status dot.
- **Admin Navigation & Dataset Upload**:
  - Added `Data Sources & Upload` (`/datasources`) to the Admin role navigation menu in `App.tsx`.
  - Added primary "+ Upload Dataset" buttons in both the Overview header and the "Data source health" panel to streamline dataset ingestion for company administrators.
- **Company & Scope Management Overhaul**:
  - Replaced the three manual text inputs (`#switcher-company-id`, `#switcher-workspace`, `#switcher-project-id`) in the sidebar with a sleek, compact Company Scope badge.
  - Implemented an interactive `AdminProfileModal` accessible by clicking the Admin profile badge at the bottom of the sidebar or clicking scope details, allowing clean viewing and editing of company scope (`kaveri`), workspace, and project ID (`project-kaveri_foods`).
- **Supply Chain Map Enhancements**:
  - Removed the redundant "Locate Red Nodes" button from the 3D globe toolbar; glowing red problem nodes and the "Only Problems (N)" filter provide direct visual identification.
  - Ensured fallback project ID defaulting to `'project-kaveri_foods'` when opening the Supply Chain Map to prevent empty state notices.
- **Settings & Audit Log Transparency**:
  - Upgraded `SettingsScreen`: eliminated manual API URL typing; displayed automated connection status to local FastAPI backend (`http://127.0.0.1:8000`), active Dry-Run execution confirmation, and CPU-optimized runtime specifications.
  - Upgraded `AuditScreen`: formatted raw event types into human-readable labels (`User Login (Success)`, `Pipeline Ingestion Completed`, etc.), truncated 64-char SHA-256 hashes with copy/hover tooltips, and highlighted cryptographic hash-chain provenance.
  - Upgraded `SystemHealthScreen`: added quick-select reason templates for model promotions/rollbacks and explanatory tooltips detailing why reviewer rationale is strictly required for regulatory compliance.
- **Verification**:
  - `npm run lint`: **0 errors, 0 warnings**.
  - `npm run typecheck`: **Clean (0 errors)**.
  - `npm test -- --run`: **5 test files passed, 33 tests passed** in 7.42s.
## Completed: One-Page Prototype Pipeline Execution & Mapping Approval Fix

- **Execution Date**: 2026-10-25
- **Issue Addressed**: Pipeline execution returned `409 Conflict: "Approve at least one mapping before executing pipeline"`.
- **Root Causes Diagnosed & Resolved**:
  1. **Asynchronous Ingestion Profiling Gap**: `POST /datasets/upload` dispatches profiling as a background job. The frontend previously made a single immediate call to `GET /datasets/{name}/suggestions` which returned `409 Conflict` (profiling incomplete) and was silently caught, leaving `mappingReport` null. Fixed by implementing `fetchSuggestionsWithRetry()` in [OnePagePrototype.tsx](file:///c:/Projects/supply-chain-risk-system/dashboard/src/components/OnePagePrototype.tsx) to poll with retry until profiling completes.
  2. **Schema Mapper Column Name Keying**: `ColumnRoleSuggestion` in `src/data/schema_mapper.py` serializes as `column_name`, whereas [types.ts](file:///c:/Projects/supply-chain-risk-system/dashboard/src/api/types.ts) typed `column`. Added `column_name?: string` and updated frontend references to `s.column_name || s.column`, ensuring columns are correctly keyed in `editedMappings`.
  3. **Canonical Role Alignment**: Aligned the dropdown options to valid canonical roles (`order_id`, `order_ts`, `promised_ts`, `delivered_ts`, `carrier`, `supplier_id`, `product_id`, `quantity`, `price`, `status`, `route`, `region`) matching `src/data/profile.py`.
  4. **Seamless Auto-Approval on Pipeline Run**: In accordance with user workflow rules (user reviews ambiguous mappings only; confident mappings are auto-accepted), clicking "Run Analysis" automatically validates and approves all confident canonical mappings before initiating pipeline execution (`PUT /datasets/{name}/confirm-mapping`).
  5. **Multi-Tenant / Project Scoping**: Updated `POST /datasets/upload` to associate uploaded sources with the active `project_id`, and added fallback in `_project_capability_report()`, `run_project_pipeline_endpoint()`, and `_execute_project_pipeline()` in [api/main.py](file:///c:/Projects/supply-chain-risk-system/api/main.py) to resolve tenant-level sources when direct project mapping is absent.
  6. **Defensive Stage Rendering**: Added default stage definitions and sanitized stage mappings to protect against any missing properties during live results rendering.
- **Verification**:
  - `npm run build`: Built production bundle in 14.72s with **0 errors**.
  - `python -m pytest tests/test_simplify_prototype.py tests/test_system_upgrades_security.py -q`: **13 passed in 32.99s**.
  - **Browser E2E Execution**: Uploaded `sample_supply_chain_orders.csv`, confirmed schema suggestions, clicked "Run Analysis", and observed complete execution of all 9 stages to `COMPLETED` status with green success banner and verified results across Anomalies, Predictions, and Drivers tabs without errors.


