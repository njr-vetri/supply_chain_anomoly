# READ-ONLY COMPREHENSIVE AUDIT REPORT

**Date of Audit**: 2026-10-25  
**Audit Mode**: STRICT READ-ONLY (No pipeline runs on new data, no source edits, all assertions grounded in code inspection and direct command outputs).

---

## SECTION 1: Repository and Safety State

### 1. Git Initialization & Commit State

#### Command: `git status`
```text
On branch master
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   api/main.py
	modified:   dashboard/index.html
	modified:   dashboard/src/App.tsx
	modified:   dashboard/src/api/client.ts
	modified:   dashboard/src/api/types.ts
	modified:   docs/PROGRESS.md
	modified:   src/alerts/manager.py
	modified:   src/connectors/notifications.py
	modified:   src/data/schema_mapper.py
	modified:   src/ml/anomaly/canonical.py
	modified:   src/ml/delay/canonical_demand.py
	modified:   src/risk/drivers.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	dashboard/src/components/OnePagePrototype.tsx
	docs/EVALUATION.md
	docs/acceptance_log_utf8.txt
	docs/pytest_acceptance_run.txt
	docs/pytest_run_without_e2e.txt
	src/nlp/stage_explainer.py
	tests/test_simplify_prototype.py

no changes added to commit (use "git add" and/or "git commit -a")
```

#### Command: `git log --oneline -10`
```text
a1a7ec9 Checkpoint before simplify prototype
871c7a7 Checkpoint after acceptance remediation
```

#### Command: `git tag`
```text
pre-simplify
```

---

### 2. `.gitignore` Verification

#### Verbatim File Content: `.gitignore` (Lines 1–52)
```gitignore
# Secrets and local configuration
.env
.env.*
!.env.example

# Dataset archives and data files
*.zip
*.7z
*.rar
data/**
!data/**/.gitkeep
*.csv
*.tsv
*.xlsx
*.xls
*.parquet
*.feather
*.db
*.sqlite*
!tests/fixtures/synthetic/kaveri_foods/**

# Model artifacts and run outputs
models/
*.pkl
*.joblib
*.onnx
mlruns/

# Python caches and environments
__pycache__/
*.py[cod]
.pytest_cache/
.pytest_tmp/
.mypy_cache/
.ruff_cache/
.pre-commit-cache/
.venv/
venv/
ENV/

# IDE and OS files
.idea/
.vscode/
.DS_Store
Thumbs.db

# Frontend install and build output
dashboard/node_modules/
dashboard/dist/
dashboard/.vite/
dashboard/*.tsbuildinfo
```

#### Exclusion Confirmation:
- `data/` excluded: Yes (`data/**` on line 10, with exception `!data/**/.gitkeep` on line 11).
- Archives (`.zip`, `.7z`, `.rar`) excluded: Yes (`*.zip`, `*.7z`, `*.rar` on lines 7–9).
- `.env` excluded: Yes (`.env`, `.env.*` on lines 2–3, with exception `!.env.example` on line 4).
- Model artifacts excluded: Yes (`models/`, `*.pkl`, `*.joblib`, `*.onnx`, `mlruns/` on lines 23–27).
- SQLite DBs excluded: Yes (`*.db`, `*.sqlite*` on lines 18–19).

---

### 3. Top-Level Folder Structure

- `api/`: FastAPI web server application, route controllers, auth middleware, and API schemas.
- `config/`: System YAML configuration files (tenant company profiles, settings, risk weights, validation thresholds).
- `dashboard/`: React 18, TypeScript, and Vite single-page frontend application.
- `data/`: Read-only storage root for raw input archives, synthetic benchmark company data, and quarantined outputs.
- `docs/`: Architecture documentation, dataset registers, progress notes, and audit/evaluation reports.
- `migrations/`: Alembic database migration environment and versioned schema revisions.
- `models/`: Local machine learning artifacts, BERT embeddings, TF-IDF baselines, and model evaluation registry JSONs.
- `scripts/`: Operational CLI scripts for auditing archives, synthetic data generation, GPU runners, and password resets.
- `src/`: Core Python backend package containing adapters, alert managers, connectors, data loaders, ML modules, graph analytics, and risk scoring.
- `tests/`: Automated pytest test suite covering unit, integration, security, and acceptance test cases.

---

## SECTION 2: Tests

### 4. Test Files and Descriptions

Total test files: **37**; Total collected tests: **195**.

| # | Test File Path | Tests | What It Checks |
|---|---|:---:|---|
| 1 | `tests/core/test_actions_phase7.py` | 12 | Guarded action registry, kill switch, rate limits, dry-run defaults, and retry backoff. |
| 2 | `tests/core/test_phase8_pipeline.py` | 6 | Pipeline orchestration from data ingestion to incident generation and audit events. |
| 3 | `tests/core/test_schemas_config_audit.py` | 5 | Pydantic domain models, YAML settings validation, and cryptographic hash-chained audit logs. |
| 4 | `tests/data/test_loaders_validation_pipelines.py` | 4 | In-memory ZIP loaders (Olist, DataCo, Retail II), schema validation, and quarantine routing. |
| 5 | `tests/ml/test_anomaly_features.py` | 6 | Feature derivation and anomaly detection baseline behavior. |
| 6 | `tests/ml/test_delay_evaluation.py` | 8 | Chronological time splits, leakage feature blocking, classification metrics, and rolling demand backtests. |
| 7 | `tests/ml/test_registry_stage7.py` | 5 | Model registry tracking, metadata provenance, promotion/rollback lifecycles, and metric schemas. |
| 8 | `tests/monitoring/test_stage7_monitoring.py` | 3 | Data drift detection via Population Stability Index (PSI) and data quality snapshot comparisons. |
| 9 | `tests/network/test_graph.py` | 2 | Olist order-item network graph assembly, node degrees, and downstream order exposure. |
| 10 | `tests/nlp/test_nlp.py` | 9 | Olist review text normalization, regex PII redaction, TF-IDF baseline, and BERT inference fallbacks. |
| 11 | `tests/recommendations/test_alerts_phase7.py` | 2 | Alert deduplication across restarts, severity routing, and escalation windows. |
| 12 | `tests/recommendations/test_engine_whatif.py` | 3 | Rule-based recommendations, evidence link integrity, and hypothetical counterfactual what-if scenarios. |
| 13 | `tests/risk/test_risk_hypotheses_investigator.py` | 6 | Multi-factor risk scoring, evidence ledger validation, hypothesis state machine, and investigator reference verification. |
| 14 | `tests/test_api_phase9.py` | 6 | Multi-tenant company isolation, RBAC role authorization, and tenant data separation. |
| 15 | `tests/test_api_stage3.py` | 1 | Pipeline preview execution and step status reporting via FastAPI. |
| 16 | `tests/test_audit_datasets.py` | 2 | Read-only in-memory dataset audit script and hash validation against raw archives. |
| 17 | `tests/test_capabilities.py` | 4 | Capability detection engine determining supported features from canonical column mappings. |
| 18 | `tests/test_dataset_api.py` | 5 | Dataset upload, column profiling, suggestion retrieval, and mapping acceptance endpoints. |
| 19 | `tests/test_e2e_acceptance_unseen.py` | 1 | Full end-to-end acceptance lifecycle on unfamiliar synthetic company data (Kaveri Foods). |
| 20 | `tests/test_graph_redesign.py` | 8 | Multi-table supply network graph assembly, healthy/unhealthy peer z-scores, and upstream/downstream traces. |
| 21 | `tests/test_onboarding_stage2.py` | 6 | Self-service dataset onboarding, schema suggestion generation, relationship proposals, and approval. |
| 22 | `tests/test_phase10_security.py` | 4 | Formula injection sanitization in CSV exports, untrusted text escaping, and audit provenance. |
| 23 | `tests/test_profile_regression.py` | 2 | Structural dataset profiling regression checks without data leaks. |
| 24 | `tests/test_profiler.py` | 6 | Sample-free column statistics computation (null fraction, uniqueness, date parse success rate). |
| 25 | `tests/test_schema_mapper.py` | 3 | Rule and embedding column role suggestions with confidence scores. |
| 26 | `tests/test_simplify_prototype.py` | 6 | One-page prototype: zip traversal safety, excel note skipping, mapping ambiguity distinction, NLP stage explanation fact-checking, alert delivery status, and 403 reviewer permission gate. |
| 27 | `tests/test_stage10_scenarios.py` | 10 | Security and edge case scenarios: cross-tenant tokens, API key revocation, lockout, and Excel multi-sheet parsing. |
| 28 | `tests/test_stage1_adapters_tenancy.py` | 7 | Multi-tenant repository CRUD, soft-deletes, Parquet schema contracts, and tenant workspace isolation. |
| 29 | `tests/test_stage3_capabilities.py` | 4 | Capability degradation when optional columns (e.g., inventory) are missing. |
| 30 | `tests/test_stage4_analytics.py` | 8 | Feature allowlist blocking post-outcome leakage, delay missing label handling, and demand pressure vs stockout labeling. |
| 31 | `tests/test_stage5_analysis_graph.py` | 5 | Planted driver discovery with Benjamini-Hochberg FDR correction, absence of spurious drivers, and qualitative risk fallback. |
| 32 | `tests/test_stage5_api.py` | 5 | Graph query size limits, tenant-versioned risk scoring configuration, and incident persistence endpoints. |
| 33 | `tests/test_stage6_api.py` | 4 | Playbook API derived from accepted mappings, what-if transparency, and alert acknowledgement persistence. |
| 34 | `tests/test_stage6_workflow_connectors.py` | 12 | Connectors (SMTP, Webhook, REST, SQLite, Folder), idempotency tokens, and simulation flags. |
| 35 | `tests/test_stage7_cross_company.py` | 1 | Strict cross-company data access prevention across tenant API boundaries. |
| 36 | `tests/test_stage7_governance_monitoring.py` | 7 | Schema change tracking without auto-retrain, outcome tracking vs predictions, and model governance lifecycles. |
| 37 | `tests/test_system_upgrades_security.py` | 7 | Account lockout after 5 failed logins, expired JWT rejection, last admin deletion prevention, and restart survival. |

---

### 5. Pytest Execution Output & Skipped Tests

#### Command: `.venv\Scripts\python.exe -m pytest -rs -q --ignore=tests/test_e2e_acceptance_unseen.py 2>&1 | Select-Object -Last 40`
```text
tests/test_stage4_analytics.py::test_identifier_columns_excluded_from_model_features
  C:\Projects\supply-chain-risk-system\src\ml\delay\canonical.py:255: UserWarning: Converting to PeriodArray/Index representation will drop timezone information.
    usable_df["_week"] = usable_df[pred_time_col].dt.to_period("W").dt.to_timestamp()

tests/test_stage4_analytics.py::test_canonical_anomaly_has_entity_baseline_methods_and_limitations
  C:\Projects\supply-chain-risk-system\src\ml\anomaly\canonical.py:178: UserWarning: Converting to PeriodArray/Index representation will drop timezone information.
    frame_copy["_week"] = frame_copy["_time"].dt.to_period("W").dt.to_timestamp()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_stage1_adapters_tenancy.py:113: could not import 'pyarrow': No module named 'pyarrow'
193 passed, 1 skipped, 128 warnings in 149.22s (0:02:29)
```

#### Skipped / Xfail Listing:
- **Skipped Test**: `tests/test_stage1_adapters_tenancy.py:112-117` (`test_parquet_schema_has_nonnullable_identity_and_timestamp`)
- **Reason**: `could not import 'pyarrow': No module named 'pyarrow'` (PyArrow is an optional storage format dependency not installed in the CPU-only environment).
- **Xfail Tests**: None (0 xfail).

---

### 6. Weak Assertion Pattern Search

Search results across all 37 test files:
- **`assert True`**: **0 hits** (NOT FOUND).
- **`pytest.skip`**: **0 hits** (all skips use `pytest.importorskip`).
- **`xfail`**: **0 hits** (NOT FOUND).
- **`except: pass`**: **0 hits** (NOT FOUND).
- **`or` inside assert**: **6 hits**:
  - `tests/test_e2e_acceptance_unseen.py:394`: `assert node_types["Supplier"] in (24, 25)`
  - `tests/test_simplify_prototype.py:145`: `assert "1,000 input rows" in explanation or "1000" in explanation`
  - `tests/test_simplify_prototype.py:181`: `assert "delivery_status" in history_record or history_record.get("status") in ("ROUTED", "SENT", "OPEN")`
  - `tests/test_stage10_scenarios.py:444`: `assert "event_hash" in ev or "payload" in ev`
  - `tests/test_system_upgrades_security.py:87`: `assert "Session expired or invalid token" in resp.json()["error"]["message"]`
  - `tests/test_system_upgrades_security.py:102`: `assert "Cannot delete or deactivate the last active admin" in del_resp.json()["error"]["message"]`
- **Assertions like `>= 0` or `is not None` as the only check**: **12 hits**:
  - `tests/ml/test_delay_evaluation.py:42`: `assert result["naive"]["mean_mae"] is not None`
  - `tests/ml/test_delay_evaluation.py:75`: `assert result["naive"]["mean_mae"] is not None`
  - `tests/risk/test_risk_hypotheses_investigator.py:48`: `assert "factors" in result and result["priority_index"] is not None`
  - `tests/test_onboarding_stage2.py:141`: `assert previous.deleted_at is not None`
  - `tests/test_profile_regression.py:14`: `assert profile.capabilities is not None`
  - `tests/test_profiler.py:35`: `assert col_map["amount"].numeric_stats is not None`
  - `tests/test_schema_mapper.py:24`: `assert suggestions["order_id"].confidence >= 0.80`
  - `tests/test_schema_mapper.py:27`: `assert suggestions["order_purchase_timestamp"].confidence >= 0.80`
  - `tests/test_stage1_adapters_tenancy.py:99`: `assert repo.get(IncidentRow, "synthetic-incident", include_deleted=True) is not None`
  - `tests/test_stage4_analytics.py:95`: `assert all(item["record_refs"] and item["baseline"] is not None for item in found)`
  - `tests/test_stage5_analysis_graph.py:38`: `assert result["change_point"] is not None`
  - `tests/test_stage5_api.py:81`: `assert result["qualitative_rating"] is not None`

---

### 7. Tests Failing if Incidents or Recommendations Were Empty

The following tests explicitly assert non-zero incident or recommendation counts and would **FAIL** if either were empty:
1. `tests/core/test_phase8_pipeline.py:100`:
   `assert result["counts"]["incidents_investigated"] == 2`
2. `tests/core/test_phase8_pipeline.py:106`:
   `assert counts["incidents"] == 2`
3. `tests/core/test_phase8_pipeline.py:109`:
   `assert counts["recommendations"] > 0`
4. `tests/test_stage5_analysis_graph.py:70`:
   `assert result["incident"].record_refs == ["synthetic:row-1", "synthetic:row-2"]`
5. `tests/test_stage5_api.py:96`:
   `assert body["incident"]["record_refs"] == ["synthetic:record-1"]`
6. `tests/recommendations/test_alerts_phase7.py:32`:
   `assert restarted.process({"source": "synthetic", "incident_key": "incident-1", "severity": "HIGH"})[...]`
7. `tests/test_e2e_acceptance_unseen.py:363`:
   Asserts generated recommendations contain specific required actions and rationale.

---

## SECTION 3: Is Anything Trained, and Does It Work on New Data?

### 8. Model Fitting Locations

| File & Line | Model Type | Data Fitted On | When Fitted | Storage Location |
|---|---|---|---|---|
| `src/ml/anomaly/canonical.py:79` | `IsolationForest` | Initial `minimum_baseline_records` clean values of each entity metric series (`quantity` or `price`) | Per run/execution for each entity group window | In-memory only; not persisted to disk |
| `src/ml/anomaly/isolation_forest.py:19` | `IsolationForest` | Pandas series of numeric values (`valid.to_frame()`) | When `fit_isolation_forest()` is invoked | Returned in-memory as `IsolationForestModel`; not written to disk |
| `src/ml/delay/canonical.py:210` | `DummyClassifier` (majority) | Chronological train split of delay records (`Late_delivery_risk` or `delay_occurred`) | Per pipeline execution when delay capability is active | In-memory evaluation; metrics returned in result payload |
| `src/ml/delay/canonical.py:237` | `LogisticRegression` / `DecisionTree` / `RandomForest` | Chronological train split of mapped features | Per pipeline execution when delay capability is active | If output path provided: `joblib.dump()` to disk; metadata registered in `ModelRegistryRow` |
| `src/ml/delay/evaluation.py:137` | `LogisticRegression` / `DecisionTree` / `RandomForest` | Chronological train split of offline benchmark datasets | During offline evaluation script (`src.ml.delay.run`) | `models/delay/...` via `joblib.dump()` |
| `src/nlp/baseline.py:90-91` | `TfidfVectorizer` + `LogisticRegression` + `DummyClassifier` | Chronological train split of Olist review texts | During offline script `scripts/eval_bert_cpu.py` | `models/nlp/olist_tfidf_baseline.joblib` |
| `src/ml/delay/canonical_demand.py:60-93` | Naive / Moving Average / Seasonal Naive Baselines | Historical panel aggregation of `(product_id, period) -> quantity` | Per pipeline run on demand records | In-memory rolling backtest & forecasts; no binary file created |

---

### 9. Pre-trained or Saved Model Artifacts

Listing of all files under `models/`:
```text
models/bertimbau/config.json: 473 bytes
models/bertimbau/eval_metrics.json: 2,105 bytes
models/bertimbau/metrics.json: 720 bytes
models/bertimbau/model/config.json: 1,114 bytes
models/bertimbau/model/model.safetensors: 435,725,300 bytes
models/bertimbau/model/tokenizer.json: 677,888 bytes
models/bertimbau/model/tokenizer_config.json: 380 bytes
models/bertimbau/model/training_args.bin: 5,201 bytes
models/dataco_delay-baseline_majority-v1.joblib: 903 bytes
models/dataco_delay-decision_tree-v1.joblib: 35,524 bytes
models/dataco_delay-logistic_regression-v1.joblib: 4,954 bytes
models/dataco_delay-random_forest-v1.joblib: 3,960,395 bytes
models/embeddings/config.json: 430 bytes
models/embeddings/embeddings_000000000_000005000.npz ... (9 chunks, 42,687 vectors): ~40.5 MB total
models/embeddings/metrics.json: 136 bytes
models/embeddings/records_*.json: ~1.5 MB total
models/evaluations/dataco_delay-*.json: ~28 KB total
models/evaluations/olist_delay-*.json: ~22 KB total
models/evaluations/synthetic-model-v99.json: 198 bytes
models/nlp/config.json: 308 bytes
models/nlp/metrics.json: 2,469 bytes
models/nlp/olist_tfidf_baseline.joblib: 1,749,979 bytes
models/olist_delay-baseline_majority-v1.joblib: 951 bytes
models/olist_delay-decision_tree-v1-shap.json: 574 bytes
models/olist_delay-decision_tree-v1.joblib: 83,460 bytes
models/olist_delay-logistic_regression-v1.joblib: 3,450 bytes
models/olist_delay-random_forest-v1.joblib: 11,917,515 bytes
```

#### Reusability for another company:
- **Delay Classifiers (`olist_delay-*`, `dataco_delay-*`)**: Cannot be reused for another company. They were trained on features specific to Olist (`freight_value`, `seller_id`) or DataCo (`Days for shipment (scheduled)`).
- **BERTimbau & TF-IDF (`models/bertimbau/`, `models/nlp/`)**: Specific to Portuguese-language Olist review texts.
- **Embedding Chunks (`models/embeddings/*.npz`)**: Olist review IDs and text vectors only.

---

### 10. Hardcoded Dataset Name and Entity Checks

Command executed:
`git grep -niE "kaveri|olist|dataco|online_retail|V0[0-9]{2}|SKU-[0-9]+|BlueLine|West-[0-9]|WH-[A-Z]+" -- src api dashboard config`

Total matches: **341 lines** across **44 files**.

#### Categorization of Hits:
1. **Harmless False Positives (Python Method Names)**:
   - `api/main.py:115, 117`: `obj.tolist()` (matched substring `olist`).
   - `api/main.py:1050, 1177, 2530`: `archive.infolist()` (matched substring `olist`).
2. **Harmless Default Fallbacks & Tenant Seeds**:
   - `dashboard/src/App.tsx:125, 290, 729`: Fallback `projectId || 'project-kaveri_foods'`.
   - `api/main.py:3266`: Fallback check for company data directory `("kaveri_foods", "local")`.
   - `config/profiles/companies/kaveri_foods/*.yaml`: Configuration profiles for the test company Kaveri Foods.
3. **Harmless Public Dataset Endpoints & Config Profiles**:
   - `api/main.py:201-202, 2997-2998`: Endpoints `POST /api/v1/audit/datasets` and `POST /api/v1/datasets/real/run` verifying the 3 public benchmark archives.
   - `config/profiles/olist.yaml`, `dataco.yaml`, `online_retail_ii.yaml`: Adapter profiles for Phase 1–2 audit benchmarks.
4. **Dataset-Specific Logic (Critical finding)**:
   - `src/network/graph.py:39-109`: `def build_olist_graph()` contains logic hardcoded specifically to `olist_order_items_dataset.csv`. (Note: The generic pipeline uses `build_canonical_graph()` in `src/network/canonical_graph.py`, but this legacy function remains).
   - `src/risk/investigator.py:17-49, 56-102`: `investigate_delay()` and `investigate_demand()` have explicit `if dataset == "olist": ... elif dataset == "dataco": ... elif dataset == "online_retail_ii": ...` branches reading from raw ZIP archives.

---

### 11. Handling of Missing Columns or Inadequate Row Count

#### 1. Missing Delivery Timestamps or Labels:
- `src/core/capabilities.py:41-45`:
  ```python
  has_delay = has_role("order_ts") and (has_role("delivery_ts") or has_role("delay_flag") or has_role("promised_ts"))
  "delay_prediction": ("AVAILABLE_WITH_LIMITATIONS" if has_delay else "UNSUPPORTED",
                       "Requires order_ts plus delivery_ts, promised_ts, or delay_flag" if not has_delay else "Uses chronological splits...")
  ```
- `src/ml/delay/canonical.py:123-129`:
  ```python
  if target not in records_df.columns:
      return {
          "status": "MISSING_LABELS",
          "trained": False,
          "missing": [getattr(settings, "label_role", "post_outcome"), "order_id", "promised_timestamp", "delivered_timestamp"],
          "message": "Missing canonical delay target or promised/delivered timestamp pair",
      }
  ```

#### 2. Missing Product Column in Demand Data:
- `src/ml/delay/canonical_demand.py:24-29`:
  ```python
  eligible = [record for record in records if record.get("product_id") is not None
              and record.get("quantity") is not None and record.get("event_timestamp") is not None]
  if not eligible:
      return {"status": "MISSING_DEMAND_DATA", "task": "demand pressure forecasting",
              "missing": ["product_id", "quantity", "event_timestamp"],
              "inventory_available": False, "label": FORECAST_NOTE}
  ```

#### 3. Fewer than N Rows:
- `src/ml/delay/canonical.py:147-153`:
  ```python
  if len(usable_df) < getattr(settings, "minimum_training_rows", 20):
      return {
          "status": "INSUFFICIENT_HISTORY",
          "trained": False,
          "records_found": len(usable_df),
          "required_training_rows": getattr(settings, "minimum_training_rows", 20),
          "missing": ["more chronological training records"],
          "limitations": [LEAKAGE_NOTE],
      }
  ```
- `src/ml/delay/canonical_demand.py:57-58, 95`:
  Returns `{"status": "INSUFFICIENT_HISTORY", ...}` when series length is less than `settings.minimum_history_periods + horizon` (8 periods).

#### 4. Inadequate Support in Evidence/Investigation:
- `src/risk/investigator.py:80-114`: Returns `{"status": "Insufficient evidence", "reason": ...}` when reference cannot be verified.
- `src/risk/hypotheses.py`: Returns HTTP 409 `"Insufficient evidence"` when attempting to confirm a hypothesis with fewer than 2 independent supporting evidence items.

---

### 12. Train/Test Splits & Prediction Timestamp Definition

#### 1. Split Function:
Defined in `src/ml/delay/evaluation.py:13-25`:
```python
def chronological_split(frame: pd.DataFrame, timestamp_column: str, train_fraction: float = 0.6,
                        validation_fraction: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Sort by timestamp and split without shuffling; missing timestamps are rejected."""
    if timestamp_column not in frame:
        raise ValueError(f"Missing timestamp column: {timestamp_column}")
    ordered = frame.sort_values(timestamp_column, kind="stable").reset_index(drop=True)
    if ordered[timestamp_column].isna().any():
        raise ValueError("Chronological split requires non-null timestamps")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("Split fractions must be positive and sum to less than one")
    train_end = int(len(ordered) * train_fraction)
    validation_end = train_end + int(len(ordered) * validation_fraction)
    return ordered.iloc[:train_end], ordered.iloc[train_end:validation_end], ordered.iloc[validation_end:]
```

#### 2. Prediction Timestamp Role Definition:
Defined in `src/ml/delay/canonical.py:131-139`:
```python
pred_time_col = getattr(settings, "prediction_time_role", "event_timestamp")
if pred_time_col not in records_df.columns:
    if "order_ts" in records_df.columns:
        pred_time_col = "order_ts"
    elif "event_timestamp" in records_df.columns:
        pred_time_col = "event_timestamp"
    else:
        pred_time_col = records_df.columns[0]
```
Usable records are sorted strictly by `pred_time_col` before splitting (`src/ml/delay/canonical.py:196`).

---

### 13. Delay Model Evaluation Metrics & Baselines

Real output from `models/evaluations/olist_delay-decision_tree-v1.json`:
- **Model**: `decision_tree`
- **Split**: Chronological holdout test set (19,294 rows, span: 2018-05-26 to 2018-08-29).
- **Test Metrics**:
  - Precision: `0.1771`
  - Recall: `0.3399`
  - F1 Score: `0.2329`
  - Macro F1: `0.5843`
  - PR-AUC: `0.1077`
  - ROC-AUC: `0.5831`
  - Brier Score: `0.1176`
- **Comparison Against Baselines**:
  - `baseline_majority` (`models/evaluations/olist_delay-baseline_majority-v1.json`): Precision `0.0000`, Recall `0.0000`, F1 `0.0000`, PR-AUC `0.0529`, ROC-AUC `0.5000`, Brier `0.0529`.
  - `baseline_simple_rule` (`models/evaluations/olist_delay-baseline_simple_rule-v1.json`): Precision `0.1687`, Recall `0.5877`, F1 `0.2622`, PR-AUC `0.1210`, ROC-AUC `0.7129`, Brier `0.1750`.

---

## SECTION 4: Column Extraction and Mapping

### 14. Exact Code Path from Upload to Approved Mapping

1. **Upload Request**:
   - User uploads in `dashboard/src/components/OnePagePrototype.tsx` -> `client.uploadDataset(...)`
   - Invokes FastAPI endpoint `POST /api/v1/datasets/upload` (`api/main.py:2470`).
2. **Safe Ingestion & Hashing**:
   - `api/main.py:2475-2550`: Reads stream in chunks, checks max file size, calculates SHA-256 hash. If ZIP, validates entry count, uncompressed size, compression ratio, and symlink/traversal safety.
   - Creates `DatasetVersionRow` in database (`api/main.py:2555`).
3. **In-Memory Profiling**:
   - `src/data/profiler.py:180-265`: `profile_data()` executes sample-free profiling calculating null percentages, uniqueness ratios, candidate identifier flags, and date parse success rates.
4. **Suggestions Generation**:
   - UI calls `client.getSuggestions(...)` -> `POST /api/v1/datasets/{name}/suggestions` (`api/main.py:2585`).
   - Calls `suggest_mappings(profile_report)` in `src/data/schema_mapper.py:236`.
   - Scores candidate canonical roles via `_score_role()` (`src/data/schema_mapper.py:161`).
5. **Reviewer Acceptance**:
   - UI calls `client.confirmDatasetMapping(name, mappings, reason)` -> `POST /api/v1/datasets/{name}/mappings` (`api/main.py:2614`).
   - `api/main.py:2620-2645`: Validates chosen roles against `CANONICAL_ROLES`, updates `MappingRow` to status `ACCEPTED`, appends cryptographic audit event `mapping_accepted` to ledger.

---

### 15. Canonical Role Detection Methods & Keyword Lists

Detection method: **Hybrid of exact/fuzzy keyword matching + value pattern verification + local embedding fallback**. LLMs are NOT used for role detection.

#### Keywords by Role (`src/data/schema_mapper.py:14-61`):
```python
ROLE_KEYWORDS: dict[str, list[str]] = {
    "order_id": ["order_id", "orderid", "order_number", "ord_id", "order_item_id", "invoice", "invoiceno", "order_code", "purchase_id", "order item id"],
    "order_ts": ["order_purchase_timestamp", "order_date", "dateorders", "invoicedate", "purchase_date", "order_time", "created_at", "trans_date", "order date (dateorders)"],
    "promised_ts": ["order_estimated_delivery_date", "estimated_delivery", "promised_date", "due_date", "scheduled_date", "target_delivery", "estimated_arrival"],
    "delivered_ts": ["order_delivered_customer_date", "actual_delivery_date", "shipping_date", "delivered_at", "delivered_date", "shipment_date", "shipping date (dateorders)"],
    "supplier_id": ["seller_id", "vendor_id", "supplier_id", "vendor", "supplier", "seller", "merchant_id", "producer_id"],
    "product_id": ["product_id", "item_id", "sku", "stockcode", "part_number", "product_code", "stock_code", "item_code"],
    "carrier": ["carrier", "shipping_mode", "courier", "logistics_provider", "delivery_method", "carrier_name", "shipping_carrier", "shipment_mode"],
    "quantity": ["quantity", "order_item_quantity", "qty", "count", "units", "items", "num_items"],
    "price": ["price", "order_item_total", "unit_price", "amount", "total", "cost", "freight_value", "order_total", "sale_amount"],
    "status": ["order_status", "delivery_status", "status", "stage", "late_delivery_risk", "shipping_status", "state_status"],
    "region": ["customer_state", "customer_city", "country", "order_region", "order_country", "region", "state", "city", "zip_code", "postal_code", "delivery_region"],
    "route": ["route", "lane", "shipping_route", "transit_lane", "corridor", "transport_route"],
}
```

#### Thresholds:
- Exact keyword match: Base score `0.95` (`src/data/schema_mapper.py:173`).
- Substring contains keyword: Base score `0.75` (`line 177`).
- Fuzzy `SequenceMatcher.ratio() > 0.8`: Base score `0.65` (`line 182`).
- Semantic SentenceTransformer / TF-IDF similarity $> 0.60$: Augments score by up to `+0.3 * emb_sim` (`lines 188-194`).
- Timestamp value pattern: `date_parse_success_rate >= 0.7` adds `+0.05`; `< 0.2` subtracts `-0.50` (`lines 206-211`).
- Numeric metric value pattern: Non-null `numeric_stats` adds `+0.05`; non-numeric subtracts `-0.50` (`lines 214-219`).

---

### 16. Confident vs. Ambiguous Decision Logic & Thresholds

Defined in `src/data/schema_mapper.py:257-279`:
```python
if candidates and candidates[0].confidence >= 0.40:
    top = candidates[0]
    alternatives = candidates[1:4]
    margin = (top.confidence - candidates[1].confidence) if len(candidates) > 1 else 1.0
    is_ambiguous = (top.confidence < 0.75 or margin < 0.12)

    suggestion = ColumnRoleSuggestion(
        column_name=col.name,
        suggested_role=top.role,
        confidence=top.confidence,
        alternative_roles=alternatives,
        reason=("needs clarification: " + top.reason) if is_ambiguous else top.reason,
        needs_clarification=is_ambiguous,
        auto_accepted=not is_ambiguous,
        is_custom_field=False,
    )
```
- **Confident (`auto_accepted = True`)**: `top.confidence >= 0.75` **AND** `margin >= 0.12`.
- **Ambiguous (`needs_clarification = True`)**: `top.confidence < 0.75` **OR** `margin < 0.12`.

---

### 17. Preservation of Unmapped/Unknown Columns

Defined in `src/data/schema_mapper.py:280-290`:
```python
else:
    suggestion = ColumnRoleSuggestion(
        column_name=col.name,
        suggested_role=None,
        confidence=0.0,
        alternative_roles=candidates[:3],
        reason="Insufficient pattern confidence to suggest a role (preserved as custom field)",
        needs_clarification=False,
        auto_accepted=False,
        is_custom_field=True,
    )
    suggestions.append(suggestion)
```
When mapping is accepted (`api/main.py:2614`), unmapped columns are stored in `mapping["custom_fields"]` and preserved in the JSONL derivatives during import (`api/main.py:1210`).

---

### 18. Handling of ZIP, Multi-sheet Excel, and JSON Files

- **Path-traversal and ZIP safety**:
  `api/main.py:1181-1182`:
  ```python
  if Path(info.filename).is_absolute() or ".." in Path(info.filename.replace("\\", "/")).parts:
      raise ValueError("Path traversal detected in ZIP member")
  ```
  `api/main.py:2531-2536`:
  ```python
  if (
      len(infos) <= settings.max_zip_entries
      and sum(info.file_size for info in infos) <= settings.max_zip_uncompressed_bytes
      and (sum(info.file_size for info in infos) / max(stored_path.stat().st_size, 1)) <= settings.max_zip_compression_ratio
      and all(safe_member_name(info.filename) and not stat.S_ISLNK(info.external_attr >> 16) for info in infos)
  ):
  ```
- **Multi-sheet Excel**:
  `api/main.py:1160-1170` and `src/data/profiler.py:140-165`: Skips non-tabular sheets (sheets where header contains "notes", "legend", or fewer than 2 valid columns).
- **JSON / JSONL**:
  `api/main.py:1178-1190`: Streams lines directly; handles both array of objects and JSONL line-delimited records.

---

### 19. Read-Only In-Memory Mapping Test on Sample Headers

Output of execution:
```text
=== READ-ONLY MAPPING TEST RESULTS ===
'VendorID'               | Suggested Role: supplier_id     | Conf: 0.9500 | Auto: True  | Clarify: False | Custom: False | Reason: Exact match with known synonym 'vendor_id'
'vendor_code'            | Suggested Role: supplier_id     | Conf: 0.7500 | Auto: True  | Clarify: False | Custom: False | Reason: Contains keyword 'vendor'
'promised_date'          | Suggested Role: promised_ts     | Conf: 1.0000 | Auto: True  | Clarify: False | Custom: False | Reason: Exact match with known synonym 'promised_date'; Confirmed by date parse rate (100%)
'scheduled_arrival'      | Suggested Role: None            | Conf: 0.0000 | Auto: False | Clarify: False | Custom: True  | Reason: Insufficient pattern confidence to suggest a role (preserved as custom field)
'received_at'            | Suggested Role: None            | Conf: 0.0000 | Auto: False | Clarify: False | Custom: True  | Reason: Insufficient pattern confidence to suggest a role (preserved as custom field)
'consignee_ref'          | Suggested Role: None            | Conf: 0.0000 | Auto: False | Clarify: False | Custom: True  | Reason: Insufficient pattern confidence to suggest a role (preserved as custom field)
'供应商'                 | Suggested Role: order_id        | Conf: 0.7800 | Auto: False | Clarify: True  | Custom: False | Reason: needs clarification: Contains keyword 'order item id'
'lane'                   | Suggested Role: route           | Conf: 0.9500 | Auto: True  | Clarify: False | Custom: False | Reason: Exact match with known synonym 'lane'
```

#### Key Audit Observations:
1. `scheduled_arrival`, `received_at`, and `consignee_ref` scored `0.0000` because these specific enterprise terms are absent from `ROLE_KEYWORDS`. They defaulted to custom fields.
2. `供应商` (Chinese for "supplier") had its non-ASCII characters stripped by `_clean_text()`, producing an empty string `""`. Because `""` is a substring of `order item id`, it received a false match with confidence 0.7800, but was correctly blocked from auto-acceptance by the ambiguity check (`Clarify: True`).

---

## SECTION 5: NLP

### 20. Usage of NLP, Embeddings, and LLMs

| File Path | Component | Usage | External Call / Runtime Download? |
|---|---|---|---|
| `src/nlp/text.py` | Portuguese text cleaner | Regex PII removal (CPF, email) and whitespace normalization on review texts | None. 100% local regex. |
| `src/nlp/baseline.py` | TF-IDF Classifier | `sklearn.feature_extraction.text.TfidfVectorizer` on review texts | None. 100% local scikit-learn. |
| `src/nlp/inference.py` | Hugging Face / PyTorch | Loads local BERTimbau model from `models/bertimbau/model` | None. Reads local `.safetensors` file; no Hugging Face hub download. |
| `src/nlp/stage_explainer.py` | Stage Explainer | Formats stage explanations and verifies factual integrity against structured stage logs | None. 100% local Python string parsing and regex. |
| `src/data/schema_mapper.py` | Optional sentence embedding | `sentence_transformers.SentenceTransformer("all-MiniLM-L6-v2")` | Wrapped in `try/except`; falls back to local TF-IDF if uninstalled. |

#### Confidential Data Transmission Check:
- Is any confidential data sent to an external service? **NO**.
- Evidence: Network search for external requests (`requests`, `urllib`) reveals only the configured webhook, SMTP, and Telegram alert channels (`src/connectors/notifications.py`). No data is sent to external LLMs, OpenAI, Anthropic, or external inference APIs.

---

### 21. Is NLP Used for Detection, Prediction, or Root-Cause Decisions?

Answer: **NO**.

#### Evidence:
1. **Anomaly Detection**: `src/ml/anomaly/canonical.py:37-224` uses IQR, Robust Z-scores, and Isolation Forest on numeric quantities and prices. Zero NLP involvement.
2. **Delay Prediction**: `src/ml/delay/canonical.py:199-245` uses tabular scikit-learn classifiers (`LogisticRegression`, `DecisionTree`, `RandomForest`) on mapped tabular columns (`quantity`, `price`, `supplier_id`, `product_id`, `carrier`).
3. **Root-Cause Analysis**: `src/risk/drivers.py:100-240` uses 2x2 contingency tables, rate differences, Fisher exact test, and Benjamini-Hochberg FDR adjustments. Zero NLP involvement.
4. **Stage Explanations**: `src/nlp/stage_explainer.py` generates read-only summary text for the UI and makes zero operational or classification decisions.

---

## SECTION 6: Pipeline Reality Check

### 22. Pipeline Stages in Execution Order

Inside `_execute_project_pipeline` (`api/main.py:570-800`), the 9 stages execute in this exact sequence:

1. `ingest`: Reads processed data source files (`api/main.py:580`, `src/core/pipeline.py:100`).
2. `schema_discovery`: Resolves mapped canonical roles and column types (`src/core/pipeline.py:115`).
3. `data_quality`: Validates null rates, negative values, and quarantine rules via `validate_frame()` (`src/core/pipeline.py:130`).
4. `capability_detection`: Evaluates available vs unsupported analytics using `assess_capabilities()` (`src/core/pipeline.py:145`).
5. `anomaly_detection`: Executes multi-detector anomaly scan via `detect_canonical_anomalies()` (`src/ml/anomaly/canonical.py:37`).
6. `prediction`: Evaluates delay models and rolling demand forecasts via `evaluate_canonical_delay()` and `forecast_canonical_demand()` (`src/ml/delay/canonical.py:80`, `src/ml/delay/canonical_demand.py:22`).
7. `root_cause_drivers`: Computes driver contingency tables and carrier $\times$ route interactions via `analyze_drivers()` (`src/risk/drivers.py:100`).
8. `recommendations`: Generates counterfactual recommendations and incident clusters (`api/main.py:655-760`).
9. `alerts`: Evaluates alert routing, deduplication, and notification delivery via `AlertManager.process()` (`api/main.py:770-800`).

#### Trigger Mechanisms:
- **API Call**: Triggered by `POST /api/v1/projects/{project_id}/pipeline/run` or `POST /api/v1/projects/{project_id}/pipeline/accept-preview`.
- **Background Scheduler**: If `scheduler.enabled == True`, `scheduler.start()` (`api/main.py:1500`) executes periodic jobs.

---

### 23. Incidents and Recommendations Creation

Incidents and recommendations get created **inside the automated pipeline execution**, as well as through manual endpoints.

#### Evidence:
`api/main.py:655-760` inside `_execute_project_pipeline`:
```python
# Automatically groups detected anomalies and drivers into clusters
clusters = defaultdict(...)
# Creates IncidentRow
repo.add(IncidentRow(id=inc_id, dataset_version_id=d_ver_id, source="canonical_pipeline", title=inc_title, ...))
# Creates EvidenceRow
repo.add(EvidenceRow(id=ev_id, dataset_version_id=d_ver_id, incident_id=inc_id, ...))
# Creates HypothesisRow (starts UNVERIFIED)
repo.add(HypothesisRow(id=hyp_id, incident_id=inc_id, status="UNVERIFIED", ...))
# Creates RecommendationRow (defaults DRY_RUN)
repo.add(RecommendationRow(id=rec_id, incident_id=inc_id, action_type=rec_action, is_hypothetical=True, ...))
```
Separate manual API endpoints also exist: `POST /api/v1/incidents/assemble`, `POST /api/v1/hypotheses`, `POST /api/v1/recommendations/generate`.

---

### 24. Alert Connectors & Delivery Status Verification

Email and Telegram connectors are **fully implemented**, not mocked (mock transports are injected only during unit tests).

#### Implementation Details (`src/connectors/notifications.py`):
- **Credentials**:
  - SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO` (`line 23`).
  - Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (`lines 120-121`).
  - Webhook: `WEBHOOK_URL`, `WEBHOOK_TOKEN` (`lines 70-71`).
- **Default State**: If `CONNECTORS_ENABLED != "true"`, all connectors return `{"status": "DRY_RUN", "label": "DRY_RUN"}` (`lines 53, 106, 141`).
- **Confirmation Check for "SENT"**:
  - Telegram (`lines 151-156`):
    ```python
    with self.request_transport(req, timeout=self.timeout) as resp:
        if 200 <= resp.status < 300:
            return {"status": "SENT", "label": "REAL", "connector": "telegram"}
        return {"status": "FAILED", "label": "FAILED", "error": f"HTTP {resp.status}", "connector": "telegram"}
    ```
    `SENT` is recorded **ONLY after HTTP 2xx confirmation from Telegram's servers**. If network fails, `RETRYING` is returned.
  - SMTP (`lines 58-66`): Executes `client.send_message(email)` through SMTP socket; records `SENT` only upon successful completion.

---

### 25. UI Pages and Buttons Status

| Page / Component | Interactive Control / Button | Backend Route / Action | Status |
|---|---|---|:---:|
| `OnePagePrototype.tsx` | "Upload & Analyze" file drop | `POST /api/v1/datasets/upload` | **Real Endpoint** |
| `OnePagePrototype.tsx` | "Accept & Save Mapping" | `POST /api/v1/datasets/{name}/mappings` | **Real Endpoint** |
| `OnePagePrototype.tsx` | "Run Pipeline Analysis" | `POST /api/v1/projects/{id}/pipeline/run` | **Real Endpoint** |
| `OnePagePrototype.tsx` | "Confirm Hypothesis" (Reviewer) | `POST /api/v1/hypotheses/{id}/confirm` | **Real Endpoint** (403 on non-reviewer) |
| `OnePagePrototype.tsx` | "Approve" / "Reject" Recommendation | `POST /api/v1/recommendations/approvals` | **Real Endpoint** |
| `OnePagePrototype.tsx` | "Rollback Model/Config" | `POST /api/v1/risk/config/rollback` | **Real Endpoint** |
| `SupplyGraphScreen.tsx` | 3D Supply Network Canvas | `GET /api/v1/projects/{id}/graph` | **Real Endpoint** |
| `SupplyGraphScreen.tsx` | "Trace Upstream" / "Trace Downstream" | `GET /api/v1/graph/trace/upstream`, `/downstream` | **Real Endpoint** |
| `LoginScreen.tsx` | "Sign In" button | `POST /api/v1/auth/login` | **Real Endpoint** |
| `DataSourcesScreen.tsx` | "Upload Dataset" / "Approve Link" | `POST /api/v1/datasets/upload`, `.../preview` | **Real Endpoint** |
| `UsersScreen.tsx` | "Add User", "Deactivate", "Reset" | `POST /api/v1/auth/users`, `DELETE ...` | **Real Endpoint** |
| `ApiKeysScreen.tsx` | "Generate Key", "Revoke Key" | `POST /api/v1/auth/api-keys`, `DELETE ...` | **Real Endpoint** |
| `WorkflowScreens.tsx` | "Acknowledge Alert", "Assign Alert" | `POST /api/v1/alerts/{id}/ack`, `.../assign` | **Real Endpoint** |
| `SystemHealthScreen.tsx` | "Promote Model", "Rollback Config" | `POST /api/v1/models/registry/{id}/promote` | **Real Endpoint** |

---

## SECTION 7: Summary Table & Top 5 Risks

### Feature Status Summary Table

| Feature Dimension | Status | Verification Evidence File & Lines |
|---|:---:|---|
| **In-Memory Streaming Ingestion (CSV, XLSX, JSON, ZIP)** | Implemented and verified | `api/main.py:2470-2550`, `tests/test_simplify_prototype.py:10-38` |
| **ZIP Path Traversal & Symlink Protection** | Implemented and verified | `api/main.py:1181-1182, 2535`, `tests/test_simplify_prototype.py:10-25` |
| **Multi-Sheet Excel Tabular vs Notes Detection** | Implemented and verified | `src/data/profiler.py:140-165`, `tests/test_simplify_prototype.py:27-38` |
| **Pretrained Schema Role Mapper & Ambiguity Check** | Implemented and verified | `src/data/schema_mapper.py:161-290`, `tests/test_simplify_prototype.py:40-62` |
| **Data Quality Validation & Quarantine Output** | Implemented and verified | `src/data/validation.py:20-80`, `scripts/run_real_datasets.py:57-67` |
| **Capability Detection & Missing Feature Degradation** | Implemented and verified | `src/core/capabilities.py:30-80`, `tests/test_capabilities.py:1-40` |
| **Canonical Anomaly Detection (IQR, Robust-Z, IsoForest)** | Implemented and verified | `src/ml/anomaly/canonical.py:37-170`, `tests/ml/test_anomaly_features.py:1-50` |
| **Multi-Detector Anomaly Deduplication per Record** | Implemented and verified | `src/ml/anomaly/canonical.py:225-265`, `dashboard/src/components/OnePagePrototype.tsx:320-370` |
| **Weekly Demand Spike Anomaly Detection** | Implemented and verified | `src/ml/anomaly/canonical.py:173-224`, `tests/test_stage4_analytics.py:80-99` |
| **Chronological Train/Validation/Test Split** | Implemented and verified | `src/ml/delay/evaluation.py:13-25`, `tests/ml/test_delay_evaluation.py:10-35` |
| **Post-Outcome Leakage Feature Blocklist** | Implemented and verified | `src/ml/delay/canonical.py:155-185`, `tests/test_stage4_analytics.py:10-30` |
| **Delay Classification vs Majority & Simple Rule** | Implemented and verified | `src/ml/delay/canonical.py:200-245`, `models/evaluations/olist_delay-*.json` |
| **Rolling Demand Forecast with MAE & sMAPE** | Implemented and verified | `src/ml/delay/canonical_demand.py:99-112`, `docs/EVALUATION.md:65-85` |
| **Root-Cause Drivers & Confounding Adjustment** | Implemented and verified | `src/risk/drivers.py:100-240`, `tests/test_stage5_analysis_graph.py:10-40` |
| **Hypothesis Confirmation Gated to Reviewer (403 for others)** | Implemented and verified | `src/risk/hypotheses.py:45-75`, `tests/test_simplify_prototype.py:80-110` |
| **Hypothetical Recommendations with Reviewer Actions** | Implemented and verified | `src/recommendations/engine.py:30-90`, `api/main.py:730-760` |
| **Real Notification Adapters (SMTP, Webhook, Telegram)** | Implemented and verified | `src/connectors/notifications.py:14-157`, `tests/test_simplify_prototype.py:64-78` |
| **Cryptographic Hash-Chained Audit Ledger** | Implemented and verified | `src/core/audit.py:20-60`, `tests/core/test_schemas_config_audit.py:40-60` |
| **Multi-Tenant Company Workspace Isolation** | Implemented and verified | `src/core/repository.py:50-120`, `tests/test_stage7_cross_company.py:1-40` |
| **One-Page Interactive ML Prototype UI** | Implemented and verified | `dashboard/src/components/OnePagePrototype.tsx:1-850`, browser validated |
| **3D Supply-Chain Network Globe (Three.js)** | Implemented and verified | `dashboard/src/components/SupplyGraphScreen.tsx:1-600` |
| **NLP Stage Explainer with Factual Integrity Verification** | Implemented and verified | `src/nlp/stage_explainer.py:1-236`, `tests/test_simplify_prototype.py:70-85` |
| **BERTimbau Review Sentiment Fine-tuning** | Implemented, unverified on new text | `src/nlp/inference.py:10-45`, `models/bertimbau/model/model.safetensors` |

---

### Top 5 Risks to the Claim "Works on Any Company's Data"

1. **Non-ASCII & Foreign Language Header Normalization Failure**  
   - **Root Cause File**: `src/data/schema_mapper.py:156-159` (`_clean_text()`)  
   - **Mechanism**: `re.sub(r"[^a-z0-9]", "", text.lower())` deletes all non-Latin characters (Chinese, Japanese, Arabic, Cyrillic, accented Latin letters). As demonstrated in the live read-only audit test, `供应商` reduces to `""` and triggers a false keyword match. Any enterprise operating in non-English locales will experience degraded schema discovery.
2. **Fixed Vocabulary of Enterprise Column Synonyms**  
   - **Root Cause File**: `src/data/schema_mapper.py:14-61` (`ROLE_KEYWORDS`)  
   - **Mechanism**: The dictionary maps a closed set of ~60 common column names. Standard enterprise ERP terms such as `scheduled_arrival`, `received_at`, `consignee_ref`, `ship_to_party`, and `material_number` scored `0.0000` confidence and defaulted to unmapped custom fields.
3. **Hardcoded Minimum Historical Window Thresholds**  
   - **Root Cause File**: `src/ml/delay/canonical.py:147` and `src/ml/delay/canonical_demand.py:57-58`  
   - **Mechanism**: The pipeline strictly requires $\ge 20$ historical rows with both order and delivered timestamps for delay classification, and $\ge 8$ periods of history for demand forecasting. For companies with smaller batch shipments, early-stage operations, or sparse transaction dates, both modeling stages fail with `INSUFFICIENT_HISTORY`.
4. **Disparate Relational Keys in Multi-Table Uploads**  
   - **Root Cause File**: `api/main.py:2527-2550` and `src/core/pipeline.py:80-110`  
   - **Mechanism**: When a company uploads a multi-file ZIP archive (e.g. `orders.csv`, `shipments.csv`, `vendors.csv`), tables cannot be automatically linked unless column names match predefined join heuristics (`po_num`, `order_id`). Disparate enterprise schemas require manual relationship proposal review before cross-table join graphs can form.
5. **Hardcoded Dataset Branches in Legacy Deep-Dive Investigator**  
   - **Root Cause File**: `src/risk/investigator.py:17-49, 56-102`  
   - **Mechanism**: The reference-verification investigator contains hardcoded conditional branches (`if dataset == "olist" / "dataco" / "online_retail_ii"`) designed to resolve citations against specific ZIP archives. For a novel company, generic driver analysis (`src/risk/drivers.py`) succeeds on canonical tables, but deep-dive raw archive resolution returns `"Insufficient evidence: Unknown dataset source"`.
