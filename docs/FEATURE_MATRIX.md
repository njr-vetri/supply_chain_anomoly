# Feature Matrix

Comprehensive evaluation and verification matrix for the Autonomous, Transparent Supply-Chain Risk Monitoring & Response System. Every row includes status, source implementation evidence, automated test references, and architectural limitations.

## Status Legend

- **`IMPLEMENTED_AND_TESTED`**: Full backend and/or frontend implementation backed by automated unit, integration, or scenario tests.
- **`PARTIAL`**: Core functional logic exists and is tested, but specific secondary capabilities or workflows are limited.
- **`NOT_ADEQUATELY_TESTED`**: Implementation exists in code, but automated test coverage is incomplete or relies on manual verification.
- **`UI_ONLY_OR_MOCKED`**: Visual UI interface present in `dashboard/`, but backend endpoint is stubbed, synthetic, or read-only.
- **`NOT_IMPLEMENTED`**: Explicitly out of scope or deferred per academic design boundaries.
- **`BLOCKED`**: Architectural constraint (e.g., CPU-only, read-only data archive policy) prevents implementation.

---

## Detailed Feature Matrix

| Feature / Capability | Status | Implementation Evidence | Test / Verification Evidence | Limitations & Boundaries |
| :--- | :--- | :--- | :--- | :--- |
| **Multi-Source Read-Only Ingestion** | `IMPLEMENTED_AND_TESTED` | `src/adapters/olist.py`<br>`src/adapters/dataco.py`<br>`src/adapters/retail_ii.py`<br>`src/data/validation.py` | `tests/test_adapters.py`<br>`tests/test_stage10_scenarios.py::test_scenario_1` | Raw zip archives are strictly read-only; in-memory streaming with chunking. Never extracts or commits raw files. |
| **Schema Profiling & Mapping Suggestions** | `IMPLEMENTED_AND_TESTED` | `src/data/profile.py`<br>`src/data/schema_mapper.py`<br>`api/main.py` | `tests/test_schema_mapper.py`<br>`tests/test_stage10_scenarios.py::test_scenario_2` | Suggestions are heuristic rules and synonym matches; requires explicit reviewer role acceptance. |
| **Cross-Source Entity Relationships** | `IMPLEMENTED_AND_TESTED` | `api/main.py` (`/relationships/preview`, `/approve`)<br>`src/core/repository.py` | `tests/test_stage10_scenarios.py::test_scenario_3` | Only allowed within tenant workspace. Strict prevention of cross-dataset fake merges. |
| **Capability Assessment & Gating** | `IMPLEMENTED_AND_TESTED` | `src/core/capabilities.py`<br>`src/data/profile.py` | `tests/test_capabilities.py`<br>`tests/test_stage10_scenarios.py::test_scenario_4` | Mapped roles indicate potential capability; does not prove or establish model quality. |
| **Data Quality & Schema Drift Monitoring** | `IMPLEMENTED_AND_TESTED` | `src/monitoring/drift.py`<br>`api/main.py` (`/quality`, `/drift`) | `tests/test_drift.py`<br>`tests/test_stage10_scenarios.py::test_scenario_5` | Drift is an operational warning only. Never triggers automatic model retraining. |
| **Statistical Anomaly Detection** | `IMPLEMENTED_AND_TESTED` | `src/ml/anomaly/statistical.py`<br>`src/ml/anomaly/isolation_forest.py` | `tests/test_anomaly.py`<br>`tests/test_stage10_scenarios.py::test_scenario_6` | CPU-friendly detectors (IQR, Robust Z-score, Scikit-Learn IsolationForest); flags outliers, not causation. |
| **Leakage-Aware Delay Classification** | `IMPLEMENTED_AND_TESTED` | `src/ml/delay/model.py`<br>`src/adapters/features.py` | `tests/test_models.py`<br>`tests/test_stage10_scenarios.py::test_scenario_6` | Excludes post-outcome leakage features (`Delivery Status`, actual delivery dates). Strict temporal train/test split. |
| **Demand Forecasting Baseline** | `IMPLEMENTED_AND_TESTED` | `src/ml/demand/`<br>`src/adapters/retail_ii.py` | `tests/test_demand.py`<br>`tests/test_stage10_scenarios.py::test_scenario_4` | Rolling mean baseline on UCI Online Retail II. Transaction demand only; no stockout or inventory labels exist. |
| **Incident Assembly & Missing-Evidence Checklist** | `IMPLEMENTED_AND_TESTED` | `api/main.py` (`/incidents/assemble`)<br>`src/risk/hypotheses.py` | `tests/test_stage10_scenarios.py::test_scenario_7` | Assembles multi-anomaly & prediction clusters; tracks missing evidence checklist items. |
| **Hypothesis Ledger & Review Lifecycle** | `IMPLEMENTED_AND_TESTED` | `src/risk/hypotheses.py`<br>`api/main.py` (`/hypotheses`) | `tests/test_hypotheses.py`<br>`tests/test_stage10_scenarios.py::test_scenario_7` | Strict lifecycle: `UNVERIFIED` -> `SUPPORTED` -> `CONFIRMED`. Only human reviewers can confirm; insufficient evidence rejected with 409. |
| **Dependency Graph & Exposure Tracing** | `IMPLEMENTED_AND_TESTED` | `src/graph/`<br>`api/main.py` (`/projects/{id}/graph`) | `tests/test_graph.py`<br>`tests/test_stage10_scenarios.py::test_scenario_8` | Bounded queries (max 5,000 nodes); traces structural exposure, never claims physical causality. |
| **Recommendation Playbooks & What-If Simulations** | `IMPLEMENTED_AND_TESTED` | `api/main.py` (`/recommendations/what-if`, `/playbooks`) | `tests/test_stage10_scenarios.py::test_scenario_9` | All what-if scenario simulations are explicitly labelled `HYPOTHETICAL` with documented relative reduction assumptions. |
| **Guarded Mitigation Actions & Approval Queue** | `IMPLEMENTED_AND_TESTED` | `api/main.py` (`/actions`, `/approvals`)<br>`src/core/repository.py` | `tests/test_stage10_scenarios.py::test_scenario_10` | High-impact actions require reviewer approval; execution strictly defaults to `dry_run: true`. |
| **Emergency Kill Switch** | `IMPLEMENTED_AND_TESTED` | `api/main.py` (`/admin/kill-switch`)<br>`src/core/repository.py` | `tests/test_stage10_scenarios.py::test_scenario_10` | Admin-only toggle; immediately blocks all mitigation actions with `BLOCKED_KILL_SWITCH`. |
| **Cryptographic Hash-Chained Audit Trail** | `IMPLEMENTED_AND_TESTED` | `src/audit/`<br>`api/main.py` (`/audit`)<br>`src/core/repository.py` | `tests/test_audit.py`<br>`tests/test_stage10_scenarios.py::test_scenario_10` | SHA-256 hash chaining over sequential audit events; tamper-evident log inspection. |
| **Multi-Tenant RBAC Authentication** | `IMPLEMENTED_AND_TESTED` | `src/auth/`<br>`api/main.py` (`/auth/login`, `_require`) | `tests/test_auth.py`<br>`tests/test_stage8_scenarios.py` | Passwords hashed with bcrypt; signed expiring JWT bearer tokens; role-gated access (`viewer`, `analyst`, `reviewer`, `admin`). |
| **React/Vite Frontend Dashboard** | `IMPLEMENTED_AND_TESTED` | `dashboard/src/`<br>`dashboard/src/App.tsx`<br>`dashboard/src/screens/` | `dashboard/src/test/`<br>(23 Vitest automated frontend tests passing) | Responsive SPA UI connecting to FastAPI endpoints with dark-mode aesthetic and capability indicators. |
| **Causal DAG / Structural Causal Inference** | `NOT_IMPLEMENTED` | N/A | Documented in `docs/LIMITATIONS.md` | Academic scope boundary: correlations and exposure graphs are not confounded causal estimates. |
| **Cross-Dataset Record Linkage** | `NOT_IMPLEMENTED` | N/A | Hard rule in `AGENTS.md` | Never invent links between distinct datasets (Olist, DataCo, Retail II). Sources are strictly separate. |
| **External Automated Operational Remediation** | `NOT_IMPLEMENTED` | N/A | Hard rule in `AGENTS.md` | Academic project; no live ERP/logistics webhook dispatch. Actions are dry-run simulations. |
| **GPU-Accelerated Deep Learning** | `BLOCKED` | N/A | Hardware constraint | CPU-only environment (16 GB RAM). Tabular ML models use Scikit-Learn baselines. |

---

## Verification Summary

- **Total Backend Tests**: 10 Stage 10 end-to-end scenario tests + comprehensive unit suites across ML, data adapters, repository, graph, and API.
- **Total Frontend Tests**: 23 Vitest component and navigation tests passing cleanly.
- **Accuracy Claim Policy**: Zero fabricated or uncomputed metrics. All reported performance values reflect actual code execution on explicit evaluation splits.
