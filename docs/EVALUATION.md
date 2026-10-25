# Autonomous Supply-Chain Risk Monitoring & Response System: Evaluation Report

**Evaluation Date**: 2026-10-25  
**Hardware Profile**: Intel CPU-only, 16 GB RAM  
**Repository State**: One-Page ML Prototype Implemented (`a1a7ec9` -> current)  
**Verification Level**: All reported metrics were produced by live, non-mocked execution. Synthetic benchmarks are explicitly labelled as synthetic and are never used to claim real-world operational accuracy.

---

## 1. Executive Summary & Verification Highlights

| Assessment Dimension | Evaluated Component | Real Execution Result | Status |
|---|---|---|:---:|
| **One-Page ML Prototype** | Ingestion, 9-Stage Orchestration, Reviewer Controls | Browser validated on `http://localhost:5173` | **VERIFIED** |
| **Backend Test Regression** | Full Pytest Suite (`tests/`) | **193 passed, 1 skipped, 0 failures** (122.34s) | **VERIFIED** |
| **Frontend Test Suite** | Vitest Component Tests (`dashboard/`) | **5 test files, 33 tests passed** (6.76s) | **VERIFIED** |
| **Frontend Production Build** | TypeScript compiler & Vite (`tsc -b && vite build`) | Zero errors, bundle created cleanly | **VERIFIED** |
| **Real Datasets Validation** | Olist, DataCo, Online Retail II in-memory streaming | **2,798,812 total rows** validated across 3 archives | **VERIFIED** |
| **Planted Fault Anomaly Detection** | Canonical Anomaly Detector (IQR, Robust Z, IsoForest) | **Recall: 1.0000, Detection Delay: 0 days** | **VERIFIED** |
| **Demand Forecasting Metrics** | Rolling-origin backtest on canonical panel | **MAE & sMAPE reported** (candidate vs naive baseline) | **VERIFIED** |
| **NLP Fact-Checking Integrity** | `stage_explainer` verification engine | Hallucination rejection, template fallback | **VERIFIED** |
| **Reviewer Permission Gate** | Hypothesis confirmation & action approval | Role enforcement: non-reviewer returns **403 Forbidden** | **VERIFIED** |

---

## 2. In-Memory Validation & Benchmark Execution on Real Datasets

Executed in-memory directly from dataset archives without extracting, committing, or altering raw archive files (`archive (1).zip`, `archive (2).zip`, `online+retail+ii.zip`):

| Dataset Archive | Total Input Rows | Valid Clean Rows | Quarantined Rows | Archive Members | Execution Runtime |
|---|---:|---:|---:|---:|---:|
| **Olist** (`archive (1).zip`) | 1,550,922 | 1,292,106 | 258,816 | 36 | 10.33s |
| **DataCo** (`archive (2).zip`) | 180,519 | 180,519 | 0 | 4 | 48.96s |
| **Online Retail II** (`online+retail+ii.zip`) | 1,067,371 | 1,055,238 | 12,133 | 2 | 221.18s |
| **Total Real Data Processed** | **2,798,812** | **2,527,863** | **270,949** | **42** | **280.47s** |

### Data Quality & Quarantine Observations:
- **Olist**: 258,816 rows quarantined due to missing timestamps on unfulfilled/canceled orders and null product metadata. Delays are computed only for delivered orders with observed delivery timestamps.
- **DataCo**: Validated cleanly against schema with 0 quarantined rows under the canonical feature allowlist. Target leakage fields (`Delivery Status`, actual shipping duration) are quarantined/excluded from feature inputs.
- **Online Retail II**: 12,133 rows quarantined due to cancelled transactions (negative quantities prefixed with `'C'`) and customer ID nulls.

---

## 3. Planted Fault Anomaly Detection Evaluation (Controlled Synthetic Test)

> [!NOTE]  
> **DISCLAIMER**: The following evaluation was conducted on a controlled synthetic time-series benchmark (`N=100` steps, 10-step fault planted from day 40 to 49) to measure detector mechanics. This synthetic data is NOT used to claim real-world operational accuracy.

### Planted Fault Results:
- **Fault Start**: Day 40
- **Earliest Detection**: Day 40
- **Detection Delay**: **0 days** (immediate detection on onset)
- **True Positives (TP)**: 10 / 10
- **False Positives (FP)**: 20
- **False Negatives (FN)**: 0
- **Empirical Recall**: **1.0000 (100.0%)**
- **Empirical Precision**: **0.3333 (33.3%)**
- **Deduplication**: Multi-detector canonical deduplication consolidated overlapping IQR, Robust Z-score, and Isolation Forest triggers into a single unified record anomaly with all triggering detector badges (`iqr`, `robust_zscore`, `isolation_forest`).

---

## 4. Demand Forecasting Error Metrics (Candidate vs. Naive Baseline)

Rolling-origin backtest comparison of candidate forecasting algorithms against the naive baseline, reporting both **Mean Absolute Error (MAE)** and **Symmetric Mean Absolute Percentage Error (sMAPE)**:

| Forecasting Model | Backtest Folds | Backtest Horizon | MAE | sMAPE (%) | Relative to Baseline |
|---|:---:|:---:|---:|---:|:---:|
| **Naive Baseline** ($y_{t+h} = y_t$) | 3 folds | 4 periods | 26.00 | 7.73% | *Reference* |
| **Moving Average** ($k=4$) | 3 folds | 4 periods | 26.00 | 7.72% | **-0.01% sMAPE** |
| **Seasonal Naive** ($s=52$) | 0 folds | 4 periods | N/A | N/A | *Skipped (history < 52 weeks)* |

### Methodological Notes:
- Forecasts strictly evaluate transaction demand pressure; inventory levels and stockouts are never inferred.
- Symmetric MAPE is calculated as:
  $$\text{sMAPE} = \frac{200\%}{n} \sum_{t=1}^n \frac{|y_t - \hat{y}_t|}{|y_t| + |\hat{y}_t| + \epsilon}$$
  preventing division by zero while treating under- and over-predictions symmetrically.

---

## 5. NLP Stage Explainer & Factual Integrity Verification

The NLP Stage Explainer (`src/nlp/stage_explainer.py`) provides automated natural language explanations for all 9 pipeline stages:
1. Every candidate explanation is parsed for numbers and entity references.
2. Extracted facts are cross-verified against the immutable structured pipeline logs (`logged_facts`).
3. If an unverified number or hallucinated entity is detected, or if the model fails, the system automatically falls back to a deterministic factual template.
4. Explanations carry a verified status badge in the UI:
   - `VERIFIED (from structured logs)`: When text facts strictly align with pipeline execution logs.
   - `DETERMINISTIC FALLBACK`: When LLM output failed verification or service was unreachable.

---

## 6. Known Gaps & System Limitations

1. **Transactional Demand Only**: Online Retail II transaction history reflects purchase demand only; inventory holding levels, warehouse reorder thresholds, and stockout occurrences are not present in the dataset and are not fabricated.
2. **DataCo Temporal Leakage Hazard**: `Late_delivery_risk` in DataCo is susceptible to leakage if combined with actual shipping duration. Strict feature allowlists in `config/settings.yaml` prevent downstream target leakage.
3. **Hypothesis Confirmation Gate**: Hypotheses are generated in `UNVERIFIED` state. Only users authenticated with the `reviewer` or `admin` role can transition a hypothesis to `CONFIRMED`, and strictly when at least 2 independent supporting evidence items exist in the `EvidenceLedger`. Non-reviewers attempting confirmation receive an explicit `403 Forbidden` response.
4. **Action Guardrails**: All automated actions default to `DRY_RUN`. High-impact operational actions require explicit human reviewer sign-off and an auditable rationale before execution.
