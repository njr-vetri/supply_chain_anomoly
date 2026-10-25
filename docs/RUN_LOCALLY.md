# Local Execution & Verification Guide

This guide provides reproducible step-by-step instructions for running, testing, and demonstrating the Autonomous, Transparent Supply-Chain Risk Monitoring & Response System locally on Windows PowerShell.

---

## 1. Prerequisites

- **Operating System**: Windows 10/11 (or Linux / macOS with equivalent POSIX shell / Makefile)
- **Python**: Version 3.13 (64-bit)
- **Node.js**: Version 18+ and `npm` (for the React/Vite dashboard)
- **Memory**: 16 GB RAM recommended (CPU-only execution)

---

## 2. Environment Setup

Run the unified setup command from PowerShell in the repository root:

```powershell
.\scripts\dev.ps1 setup
```

This automated task:
1. Creates the `.venv` virtual environment if not present.
2. Upgrades `pip` and installs pinned, locked dependencies from `requirements.lock`.
3. Copies `.env.example` to `.env` if `.env` does not exist.
4. Navigates into `dashboard/` and runs `npm install` for frontend dependencies.

### Manual Alternative
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
if (-not (Test-Path ".env")) { Copy-Item .env.example .env }
cd dashboard; npm install; cd ..
```

---

## 3. Running Services

### A. Start the Backend REST API
In a PowerShell terminal:

```powershell
.\scripts\dev.ps1 run-api
```
- **Service URL**: `http://127.0.0.1:8000`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`
- **OpenAPI Schema**: `http://127.0.0.1:8000/openapi.json`

### B. Start the React/Vite Frontend Dashboard
In a second PowerShell terminal:

```powershell
.\scripts\dev.ps1 run-ui
```
- **Dashboard URL**: `http://localhost:5173`
- Modern dark-mode UI with screens for Overview, Data Sources, Quality & Drift Monitoring, Predictions, Incident Investigations, Dependency Graph, Recommendations, Approvals, and Hash-Chained Audit Trail.

---

## 4. Testing & Verification

### A. Run Full Test Suite (Backend & Frontend)
```powershell
.\scripts\dev.ps1 test
```
Runs:
1. Backend test suite (`pytest -q`) across all modules.
2. Frontend component & navigation test suite (`vitest run` in `dashboard/`).

### B. Run Stage 10 Acceptance Test Suite (Scenarios 1 to 10)
```powershell
.\scripts\dev.ps1 acceptance
```
Executes `tests/test_stage10_scenarios.py` verifying all 10 core product scenarios:
- **Scenario 1**: New Company Onboarding & Upload
- **Scenario 2**: Schema Mapping Wizard & Suggestions
- **Scenario 3**: Cross-Source Relationships & Orphan Detection
- **Scenario 4**: Capability Checklist & Gating
- **Scenario 5**: Quality Validation & Drift Monitoring
- **Scenario 6**: Anomaly Detection & ML Delay Prediction
- **Scenario 7**: Incident Assembly & Hypothesis Review Lifecycle
- **Scenario 8**: Supply-Chain Dependency Graph & Upstream/Downstream Tracing
- **Scenario 9**: Recommendation Playbooks & What-If Simulations
- **Scenario 10**: Guarded Actions, Approval Queue, Kill Switch & Hash-Chained Audit

### C. Run End-to-End Synthetic Company Lifecycle
```powershell
.\scripts\dev.ps1 e2e-synthetic
```
Generates unfamiliar company data (`acme_industrial`) and executes the complete 10-step API lifecycle (upload, mapping, relationships, capabilities, monitoring, incident, graph, what-if, approval, dry-run action, audit verification).

### D. Run Real Datasets In-Memory Pipeline & Timing
```powershell
.\scripts\dev.ps1 real-datasets
```
Validates the three real static archives (Olist, DataCo, and UCI Online Retail II) in chunked memory buffers without unpacking or modifying original raw files, reporting real counts and wall-clock execution times.

---

## 5. Security, Roles & Headers

When querying the API directly via HTTP or curl:
- **Authentication**: Pass API Key via `X-API-Key` or JWT bearer token via `Authorization: Bearer <token>`.
- **Tenant Scoping**: Pass company tenant ID via `X-Company-Id`.
- **Role Hierarchy**:
  - `viewer`: Read-only access to datasets, profiles, metrics, and graphs.
  - `analyst`: Can assemble incidents, create hypotheses, and propose playbooks.
  - `reviewer`: Required to accept schema mappings, approve relationships, and confirm hypotheses.
  - `admin`: Can toggle the emergency kill switch and view system-wide audit logs.
