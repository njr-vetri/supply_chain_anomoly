# Autonomous, Transparent Supply-Chain Risk Monitoring & Response System

An academic, local-first Python and React project that profiles separate supply-chain datasets, builds leakage-aware features, detects unusual records, evaluates delay and demand baselines, and stores evidence-linked investigations in SQLite. The FastAPI backend and React/Vite dashboard expose stored results, interactive dependency graphs, what-if simulations, and role-gated review workflows. It is not production-ready and does not perform external operational actions.

---

## Core Principles & Hard Data Boundaries

- **Separate Sources**: Olist (delivery timelines/delays), DataCo (delay classification with leakage-prone features), and UCI Online Retail II (transaction demand forecasting only; no stockout or inventory labels). No fake cross-source joins or record linkages.
- **Read-Only Archives**: Raw dataset archives (`archive (1).zip`, `archive (2).zip`, `online+retail+ii.zip`) are strictly read-only and processed via in-memory chunked streaming without disk extraction.
- **Unknown Licenses**: Dataset licenses remain `UNKNOWN` pending verified redistribution terms.
- **Explainable Evidence**: Hypothesis lifecycle progresses strictly from `UNVERIFIED` to `SUPPORTED` to `CONFIRMED`. Only human reviewers can confirm root causes.
- **Guarded Action Policy**: All mitigation actions strictly default to `dry_run: true` and are governed by an emergency kill switch and SHA-256 cryptographic hash-chained audit logging.
- **Result Integrity**: Real results only. Synthetic data (`acme_industrial`) is used strictly for unit and acceptance testing of API contracts, never to claim model accuracy.

---

## Quick Start (Windows PowerShell)

```powershell
# 1. Automated environment setup (Python venv + locked dependencies + dashboard npm)
.\scripts\dev.ps1 setup

# 2. Run full test suite (backend pytest + frontend vitest)
.\scripts\dev.ps1 test

# 3. Run Stage 10 acceptance suite (Scenarios 1 to 10)
.\scripts\dev.ps1 acceptance

# 4. Start backend API (http://127.0.0.1:8000)
.\scripts\dev.ps1 run-api

# 5. Start frontend UI (http://localhost:5173)
.\scripts\dev.ps1 run-ui
```

Cross-platform `Makefile` targets (`make setup`, `make test`, `make acceptance`, `make run-api`, `make run-ui`) are also provided.

---

## Real Datasets & Synthetic Verification

- **Unfamiliar Synthetic Lifecycle**: Run `.\scripts\dev.ps1 e2e-synthetic` to generate unfamiliar company data (`data/synthetic_company/`) and execute the complete 10-step API lifecycle (upload, mapping wizard, relationship approval, capability checklist, monitoring, incident assembly, graph query, what-if simulation, approval queue, dry-run action, and audit verification).
- **Real Datasets Validation**: Run `.\scripts\dev.ps1 real-datasets` to stream all 3 real datasets through the in-memory validation pipeline:
  - **Olist**: 1,550,922 input rows | 1,292,106 valid rows | 258,816 quarantined | 8.67s runtime
  - **DataCo**: 180,519 input rows | 180,519 valid rows | 0 quarantined | 39.11s runtime
  - **UCI Online Retail II**: 1,067,371 input rows | 1,055,238 valid rows | 12,133 quarantined | 128.95s runtime

---

## Documentation Suite

- [What's New: Upgraded Features & Capabilities](docs/WHATS_NEW.md)
- [Architecture & Data Flow](docs/ARCHITECTURE.md)
- [Feature Matrix & Status](docs/FEATURE_MATRIX.md)
- [Acceptance Testing Specification](docs/ACCEPTANCE.md)
- [Known Limitations & Scope Boundaries](docs/LIMITATIONS.md)
- [Local Execution Guide](docs/RUN_LOCALLY.md)
- [Demonstration Script & Walkthrough](docs/DEMO_SCRIPT.md)
- [API Contract Specification](docs/API_CONTRACT.md)
- [Progress Tracking](docs/PROGRESS.md)

---

## What's New: Company-Independent Upgrade

The system has been upgraded from fixed dataset scripts to a generic, company-independent risk monitoring platform:

- **Generic Data Onboarding**: Streamed multipart uploads (CSV, TSV, JSON, JSONL, XLSX, single-table ZIP) with in-memory profiling, heuristic mapping suggestions, immutable versioned mappings, and multi-file join orphan analysis.
- **Dynamic Capabilities & Pipelines**: Features (anomaly monitoring, delay prediction, demand forecasting, supply graph, incident assembly) automatically activate based on accepted canonical schema mappings.
- **Aggregated Supply-Chain Network**: Interactive network visualizer grouping entities into meaningful cohorts (suppliers, product categories, shipment groups, carriers) with peer $z$-score baselines, weekly time replay, and exposure tracing along established relationships.
- **Governance & Tenant Safety**: Multi-tenant database and storage isolation (`company_id`), role-based access control, human-only root-cause confirmation, guarded dry-run actions, emergency kill switch, and tamper-evident SHA-256 hash-chained audit logging.

For complete feature specifications, API paths, UI navigation steps, honest limitations, and verified test evidence across all 10 feature groups, see the detailed reference in [docs/WHATS_NEW.md](docs/WHATS_NEW.md).
