# System Architecture

## Overview

The Autonomous, Transparent Supply-Chain Risk Monitoring & Response System is a modular, local-first academic platform designed for explainable risk detection, gated human review, and traceable operational response. The architecture prioritizes:
1. **Multi-Source Isolation**: Strict dataset boundaries between independent sources (Olist, DataCo, UCI Online Retail II, and synthetic company data) without cross-source record joins.
2. **Explainable AI & Baseline Comparison**: Leakage-aware delay classification and demand forecasting compared against simple moving baselines with temporal splits.
3. **Evidence-Led Human Review**: Gated lifecycle (`UNVERIFIED` -> `SUPPORTED` -> `CONFIRMED`) where only authenticated human reviewers can confirm root causes.
4. **Guarded Mitigations & Dry-Run Enforcement**: All remediation actions default to `dry_run: true`, supported by an emergency kill switch and cryptographic hash-chained audit logging.
5. **Multi-Tenant Security**: Tenant-scoped storage (`tenants/<company_id>/`), bcrypt-hashed passwords, signed expiring JWT bearer tokens, and role-based access control.

---

## Architectural Data Flow

```mermaid
flowchart TD
    subgraph Data Layer [Data Ingestion & Quarantine]
        RawArchives[Read-Only Zip Archives: Olist / DataCo / Retail II] --> Adapters[Source Adapters & Chunked Streamers]
        Uploads[Tenant File Uploads: CSV / XLSX / JSON] --> TenantStorage[TenantFileStore / Path Isolation]
        Adapters --> SchemaMapper[Schema Profiler & Mapping Wizard]
        TenantStorage --> SchemaMapper
        SchemaMapper --> Canonical[Canonical Records: PyArrow / Typed Schemas]
        Canonical --> Validator[Data Validator & Quarantine Ledger]
    end

    subgraph Analytics Layer [ML & Monitoring Engines]
        Validator --> QualityDrift[Quality Snapshots & Drift Monitor]
        Validator --> AnomalyEng[Statistical IQR / Robust Z / Isolation Forest]
        Validator --> DelayModel[Leakage-Aware Delay Classifier]
        Validator --> DemandModel[Demand Forecasting Baseline]
        Validator --> DepGraph[NetworkX Dependency Graph Engine]
    end

    subgraph Risk Layer [Evidence & Investigation]
        AnomalyEng --> IncidentAssembler[Incident Assembler]
        DelayModel --> IncidentAssembler
        IncidentAssembler --> HypothesisService[Hypothesis Ledger & Evidence Assessor]
        HypothesisService --> PlaybookGen[Recommendation Playbook Generator]
        PlaybookGen --> WhatIfSim[What-If Hypothetical Simulator]
    end

    subgraph Governance Layer [Security, Approval & Audit]
        WhatIfSim --> ApprovalQueue[Reviewer Approval Queue]
        ApprovalQueue --> ActionEngine[Guarded Action Engine (Dry-Run Default)]
        KillSwitch[Emergency Kill Switch] -.-> ActionEngine
        ActionEngine --> AuditChain[Cryptographic SHA-256 Hash Chained Audit Log]
    end

    subgraph Presentation Layer [FastAPI & React Dashboard]
        API[FastAPI v1 REST API]
        UI[React / Vite / TypeScript Dashboard]
        API <--> UI
        API --> SQLite[(Tenant-Scoped SQLite / Repository)]
    end
```

---

## Core System Subsystems

### 1. Ingestion, Adapters & Canonical Profiling (`src/adapters/`, `src/data/`)
- **Read-Only Adapters**: Accesses raw dataset archives in streaming chunks using in-memory byte buffers (`BytesIO`). Original zip archives are strictly read-only and never unpacked or modified.
- **Canonical Schemas (`src/adapters/canonical.py`)**: Standardizes orders, shipments, items, products, and suppliers into typed PyArrow schemas with flexible `custom_fields`.
- **Heuristic Schema Mapper (`src/data/schema_mapper.py`)**: Computes field name similarities and statistical distributions to propose canonical mappings. All suggestions are marked `auto_confirmed: false` and require explicit reviewer acceptance.
- **Validation & Quarantine (`src/data/validation.py`)**: Checks null constraints, date formats, and numeric bounds. Failing rows are partitioned into quarantine tables with exact row offsets and rejection reasons.

### 2. Machine Learning & Drift Detection (`src/ml/`, `src/monitoring/`)
- **Anomaly Detectors (`src/ml/anomaly/`)**: CPU-efficient detectors including Interquartile Range (IQR), Robust Median Absolute Deviation (MAD / Robust Z-score), and Scikit-Learn `IsolationForest`.
- **Leakage-Safe Delay Classification (`src/ml/delay/`)**: Excludes post-event leakage attributes (`Delivery Status`, actual shipping timestamps). Uses strict temporal train/test holdouts and evaluates against dummy majority-class baselines.
- **Demand Forecasting (`src/ml/demand/`)**: Predicts product transaction volumes on UCI Online Retail II using rolling temporal windows. Does not invent inventory or stockout labels.
- **Distribution Drift (`src/monitoring/drift.py`)**: Computes summary statistics (mean shifts, null rate changes, schema modifications). Drift flags are treated strictly as operational warnings, never triggering automated retraining.

### 3. Risk Reasoning, Dependency Graph & Hypotheses (`src/risk/`, `src/graph/`)
- **Incident Assembly**: Clusters correlated anomalies and delay predictions into unified incident cases with missing-evidence checklists.
- **Hypothesis Evidence Ledger (`src/risk/hypotheses.py`)**: Enforces state transitions (`UNVERIFIED` -> `SUPPORTED` -> `CONFIRMED`). A hypothesis cannot be confirmed without meeting the minimum supporting evidence count and strength threshold, and confirmation requires the `reviewer` role.
- **Supply-Chain Dependency Graph (`src/graph/`)**: Builds directed multi-entity graphs (suppliers, products, orders, transport hubs) with degree and centrality metrics. Limits queries to 5,000 nodes to preserve interactive browser performance.
- **What-If Simulation (`src/recommendations/`)**: Evaluates hypothetical risk mitigations (e.g. secondary carrier allocation) using parameterized probability reductions, explicitly tagged with the `HYPOTHETICAL` banner.

### 4. Tenancy, Governance & Audit (`src/auth/`, `src/core/`, `src/audit/`)
- **Multi-Tenant Scoping (`src/core/repository.py`, `src/core/tenant_files.py`)**: All database queries and file storage paths are partitioned by `company_id`. File access enforces path-traversal safeguards preventing `..` escapes.
- **Authentication & RBAC (`src/auth/`)**: Users authenticate via bcrypt password verification and receive signed, expiring JWT bearer tokens. Roles (`viewer`, `analyst`, `reviewer`, `admin`) gate access across all endpoints.
- **Approval Queue & Guarded Actions (`src/core/repository.py`, `api/main.py`)**: High-impact recommendations require reviewer approval. Action execution defaults strictly to `dry_run: true`.
- **Emergency Kill Switch (`src/core/repository.py`)**: Process-level kill switch instantly blocks execution of all non-read-only actions.
- **Cryptographic Audit Trail (`src/audit/`)**: Every state-changing operational event is recorded with an incremental sequence, timestamp, actor identity, payload digest, and previous SHA-256 hash.

### 5. Frontend Dashboard (`dashboard/`)
- **Technology Stack**: React 18, TypeScript, Vite, Vanilla CSS design tokens.
- **Modern Dark Aesthetics**: Premium slate/indigo palette, glassmorphic cards, responsive status badges, and dynamic SVG icons.
- **Screens**:
  - `Overview`: High-level risk scorecards, active alerts, recent incidents, system health.
  - `Data Sources`: Ingestion upload, schema mapping wizard, relationship preview, capability checklist.
  - `Monitoring`: Quality metrics, schema drift alerts, null rate comparisons.
  - `Predictions`: Delay classification and demand forecasting results with SHAP explanations.
  - `Incidents`: Case details, evidence ledger, hypothesis review controls, missing evidence check.
  - `Supply Graph`: Interactive NetworkX/Cytoscape visualization with neighborhood tracing.
  - `Recommendations`: Playbooks, what-if simulation calculator, and approval triggers.
  - `Approvals`: Reviewer queue for high-impact mitigation sign-offs.
  - `Audit Log`: Tamper-evident hash-chained log viewer with cryptographic verification.
  - `Admin Settings`: Tenancy status and emergency kill switch controls.

---

## Hardware & Deployment Constraints

- **Execution Environment**: Windows PowerShell / Cross-Platform POSIX.
- **Compute Budget**: CPU-only execution (16 GB RAM baseline). No GPU acceleration is assumed or required.
- **Persistence Store**: Local SQLite database at `data/processed/supply_chain.db`.
