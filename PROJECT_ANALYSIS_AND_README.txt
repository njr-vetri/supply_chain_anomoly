================================================================================
AUTONOMOUS, TRANSPARENT SUPPLY-CHAIN RISK MONITORING & RESPONSE SYSTEM
COMPLETE SYSTEM ANALYSIS, ARCHITECTURE, WORKFLOWS & README SPECIFICATION
================================================================================

TABLE OF CONTENTS:
1. Executive Summary & Core Philosophy
2. Complete System Capabilities & Features
   - What the system does automatically
   - What strictly requires human review (governance)
3. End-to-End System Architecture & Data Flow
4. Data Inputs & Dataset Compatibility
   - Current default datasets
   - Does it work ONLY with default datasets?
   - Step-by-step guide to plug in custom data
5. Roadmap to Evolve into a Production User-Friendly Product
6. Ready-to-Use Master README & Setup Guide
7. Command Cheatsheet & Operational Troubleshooting

================================================================================
1. EXECUTIVE SUMMARY & CORE PHILOSOPHY
================================================================================

This project is an Autonomous, Transparent Supply-Chain Risk Monitoring and
Response System. It solves a central dilemma in enterprise AI: how to automate
supply-chain risk triage without creating an unpredictable, unaccountable
"black-box" algorithm.

CORE DESIGN PRINCIPLES:
1. EVIDENCE-LINKED TRANSPARENCY:
   The system never computes arbitrary risk scores without evidence. Every alert,
   prediction, incident, and recommendation points directly to audit-verified
   facts, source file locators, specific record references, and model versions.

2. STRICT SEPARATION OF CONCERNS:
   In database models and API schemas, the system rigorously enforces boundaries
   between:
   - FACTS: Verified raw historical observations.
   - PREDICTIONS: Statistical and machine learning model outputs.
   - HYPOTHESES: Explanations of proposed root causes.
   - RECOMMENDATIONS: Suggested operational mitigations.
   - ACTIONS & OUTCOMES: Recorded decisions and their real-world outcomes.

3. GUARDED AUTONOMY & HUMAN-IN-THE-LOOP:
   Low-risk routines are dry-run by default. High-impact operational changes
   strictly require authenticated human reviewer approval. An emergency Global
   Kill Switch, sliding-window rate limiting, and circuit breakers prevent
   runaway operations.

4. LOCAL-FIRST & CPU-FRIENDLY:
   The entire pipeline is built to execute locally on standard workstation
   hardware (16 GB RAM, CPU-only), utilizing SQLite and local files, with zero
   mandatory cloud subscriptions or external API dependencies.


================================================================================
2. COMPLETE SYSTEM CAPABILITIES & FEATURES
================================================================================

--------------------------------------------------------------------------------
A. WHAT THE SYSTEM DOES AUTOMATICALLY (Without Human Intervention)
--------------------------------------------------------------------------------
1. In-Memory Streaming & Validation:
   - Reads compressed ZIP archives directly in RAM without extracting raw files
     to disk (preserving raw data immutability).
   - Validates column datatypes, date ordering, null thresholds, and duplicates.

2. Automated Data Quarantine:
   - Isolates corrupted, incomplete, or malformed records.
   - Automatically writes privacy-preserving JSONL manifests recording the
     exact row offset, archive SHA-256 hash, and quarantine reason.

3. Data Drift Monitoring:
   - Compares incoming batches against historical baseline snapshots.
   - Detects and flags anomalous shifts in total row counts and per-column null
     fractions.

4. Multi-Method Anomaly Detection:
   - Rule-based checks: Domain rule violations (e.g., negative transit days,
     unrealistic delivery durations).
   - Statistical thresholding: Interquartile Range (IQR) and Robust Z-scores
     (Median Absolute Deviation).
   - Unsupervised Machine Learning: scikit-learn Isolation Forest detecting
     subtle multi-dimensional feature deviations.

5. Predictive Modeling & Explainability:
   - Delay classification: Decision Trees, Random Forests, and Logistic
     Regression with leakage-aware chronological train/val/test splits.
   - Explainable AI: Computes SHAP (SHapley Additive exPlanations) values to
     attribute exact percentage impacts of features to a delay prediction.
   - Demand forecasting: Time-series lag baselines (naive, moving-average).

6. Customer Review Sentiment NLP:
   - Normalizes text, performs heuristic language detection, and applies regex
     redaction to scrub PII (emails, phone numbers).
   - Uses TF-IDF + Logistic Regression (and optional BERTimbau transformer
     weights) to classify review complaints and customer delivery sentiment.

7. Incident Clustering & Graph Synthesis:
   - Aggregates related anomalies, model predictions, and order facts into
     discrete Incident objects.
   - Constructs a NetworkX relationship graph establishing connections between
     Orders, Suppliers, Carriers, and Products.

8. Risk Prioritization Scoring:
   - Normalizes and balances a multi-factor risk index:
     [Delay Probability + Order Volume Impact + Supplier Exposure +
      Evidence Freshness + Historical Recurrence + Uncertainty Penalty].

9. Recommendation Engine:
   - Generates actionable operational suggestions (e.g., "Supplier capacity
     audit", "Carrier status verification", "Monitoring alert").
   - Explicitly records underlying assumptions, constraints, and uncertainties.

10. Alert Routing & Cryptographic Audit Trail:
    - Suppresses duplicate alerts across restarts.
    - Routes urgent notices to console and file logs.
    - Appends every pipeline execution, decision, and hypothesis update to a
      tamper-evident JSONL log chained with cryptographic SHA-256 hashes.

--------------------------------------------------------------------------------
B. WHAT STRICTLY REQUIRES HUMAN REVIEW (Gated Governance)
--------------------------------------------------------------------------------
1. Hypothesis Confirmation:
   - Automated hypotheses enter as "UNVERIFIED" and may become "SUPPORTED" if
     evidence thresholds pass.
   - ONLY an authenticated user with the "reviewer" or "admin" role can promote
     a hypothesis to "CONFIRMED" or "REJECTED", requiring mandatory written
     rationale.

2. High-Impact Operational Actions:
   - Any operational action categorized as "HIGH_IMPACT" is blocked until a
     human reviewer signs off on an approval record.

3. Emergency Kill Switch:
   - Administrators can manually toggle the system-wide Kill Switch to halt
     all action executions instantly.


================================================================================
3. END-TO-END SYSTEM ARCHITECTURE & DATA FLOW
================================================================================

1. INGESTION & QUALITY (src/data/loaders.py, src/data/validation.py):
   ZIP archives -> In-Memory Stream -> Schema & Null Validation ->
   Quarantine Bad Rows -> Quality Snapshot (Drift Checks)

2. FEATURE EXTRACTION (src/data/features/):
   Computes delivery transit deltas, seller historical performance, shipping
   mode categorizations, and weekly SKU demand aggregations.

3. ANOMALY & ML INFERENCE (src/ml/anomaly/, src/ml/delay/):
   Features -> Statistical (IQR, Robust Z) + ML (Isolation Forest, Delay Tree)
   -> Anomaly Flags & Predictions -> SHAP Feature Attribution

4. REASONING & INCIDENT ASSEMBLY (src/risk/, src/network/):
   Anomalies & Predictions -> Incident Synthesis -> Evidence Ledger ->
   Hypothesis Generation -> Multi-Factor Risk Prioritization -> Graph Edges

5. GOVERNANCE & ACTION RECOMMENDATIONS (src/recommendations/, src/alerts/):
   Prioritized Incidents -> Mitigation Recommendations -> Alert Routing ->
   Dry-Run Action Logging -> SHA-256 Append-Only Audit Trail

6. PRESENTATION & HUMAN DECISION (api/main.py, dashboard/):
   FastAPI (/api/v1/) -> Session Storage Key -> React + Tailwind Console ->
   Interactive Graph View -> Reviewer Approval / Confirmation Dialogs


================================================================================
4. DATA INPUTS & DATASET COMPATIBILITY
================================================================================

CURRENT DEFAULT DATASETS:
1. Olist E-Commerce (archive (1).zip):
   - Scope: Brazilian e-commerce orders, delivery milestones, seller IDs,
     freight costs, customer review scores, and review comments.
   - Purpose: Real delivery delays, seller exposure, customer sentiment NLP.

2. DataCo Supply Chain (archive (2).zip):
   - Scope: Global supply chain shipping records, shipping modes, scheduled vs
     actual days, and late delivery risk flags.
   - Purpose: Delay risk classification, carrier routing benchmarks.

3. UCI Online Retail II (online+retail+ii.zip):
   - Scope: Non-store transactional retail invoices, stock codes, quantities,
     unit prices, customer identifiers.
   - Purpose: Product-week demand forecasting and volume anomaly detection.

--------------------------------------------------------------------------------
DOES IT WORK ONLY WITH THE DEFAULT DATASETS?
--------------------------------------------------------------------------------
ANSWER: NO, but the raw loaders and feature extractors are currently tailored
to the specific column schemas of those 3 datasets.

The internal reasoning engine (Incidents, Evidence, Hypotheses, Recommendations,
Risk Prioritizer, Alerts, Audit Ledger, and UI Dashboard) is completely
GENERIC. It only cares about universal concepts:
- Timestamps (order date, promised delivery date, actual delivery date)
- Identifiers (order ID, item ID, seller/supplier ID, SKU)
- Categoricals (carrier, shipping mode, status)
- Numerics (price, quantity, transit days)

--------------------------------------------------------------------------------
HOW TO PLUG IN YOUR OWN CUSTOM DATASET (e.g. ERP / Shopify / SAP CSVs):
--------------------------------------------------------------------------------
To use your own company or project data:

OPTION 1: COLUMN MAPPING ADAPTER (Fastest):
Export your custom data to CSV and rename/alias your columns to match the
canonical schema:
  Your Order ID       -> order_id
  Your Order Date     -> order_purchase_timestamp
  Your Delivery Date  -> order_delivered_customer_date
  Your Promised Date  -> order_estimated_delivery_date
  Your Vendor ID      -> seller_id
Compress the CSV into a ZIP file and place it in the workspace root.

OPTION 2: CREATE A DEDICATED LOADER (Cleanest):
1. Add a loader function in `src/data/loaders.py` (e.g., `load_custom_erp`).
2. Add column validation rules in `src/core/pipeline.py:_quality`.
3. Create feature logic in `src/data/features/custom.py`.
4. Register the step in `src/core/pipeline.py`.


================================================================================
5. ROADMAP TO EVOLVE INTO A PRODUCTION USER-FRIENDLY PRODUCT
================================================================================

To convert this academic prototype into an enterprise-ready SaaS application:

1. IN-APP DATA IMPORT & SCHEMA MAPPER:
   - Current: Files must be manually zipped and placed in the project root.
   - Enhancement: Add a "Data Connections" screen in the UI with drag-and-drop
     CSV/Excel file upload and an interactive wizard to map columns visually.

2. LIVE PIPELINE TRIGGER & REAL-TIME PROGRESS:
   - Current: Pipeline is executed manually via PowerShell.
   - Enhancement: Add a "Run Risk Scan" button in the dashboard that triggers a
     Celery or RQ background worker, updating progress via WebSockets.

3. ENTERPRISE DATABASE MIGRATION:
   - Current: Single-machine SQLite file (`supply_chain.db`).
   - Enhancement: The codebase is already built on SQLAlchemy 2.0 with Alembic!
     Simply update `storage.url` in `config/settings.yaml` to point to a
     production PostgreSQL cluster (`postgresql+psycopg2://...`).

4. AUTHENTICATION & MULTI-TENANCY:
   - Current: Static API keys in `.env` entered in browser session storage.
   - Enhancement: Replace with JWT tokens, OAuth2 (Google/Azure AD/Okta SSO),
     and company/team workspace multi-tenancy.

5. OUTBOUND WEBHOOKS & REAL-WORLD ACTIONS:
   - Current: Actions are strictly recorded as DRY_RUN in local SQLite.
   - Enhancement: Connect approved actions to real systems:
     - Real-time Slack, Microsoft Teams, and PagerDuty alert notifications.
     - Webhook triggers to ERPs (SAP, NetSuite) to place supplier holds.


================================================================================
6. READY-TO-USE MASTER README & SETUP GUIDE
================================================================================

--------------------------------------------------------------------------------
PREREQUISITES:
--------------------------------------------------------------------------------
- Operating System: Windows 10/11, macOS, or Linux
- Python: Version 3.13 (recommended)
- Node.js: Version 18+ and npm
- Memory: Minimum 8 GB RAM (16 GB recommended)

--------------------------------------------------------------------------------
STEP 1: BACKEND INSTALLATION & LAUNCH
--------------------------------------------------------------------------------
Open PowerShell in `C:\Projects\supply-chain-risk-system`:

1. Run automated setup (creates virtual environment, installs locked packages):
   .\scripts\dev.ps1 setup

2. Verify environment configuration:
   Ensure `C:\Projects\supply-chain-risk-system\.env` exists with:
     DRY_RUN=true
     KILL_SWITCH=false
     API_KEYS_JSON='{"admin123":"admin"}'
     CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000

3. Start the FastAPI backend:
   .\scripts\dev.ps1 run-api

   * Backend URL: http://127.0.0.1:8000
   * Interactive Swagger API Docs: http://127.0.0.1:8000/docs
   * ReDoc API Documentation: http://127.0.0.1:8000/redoc

--------------------------------------------------------------------------------
STEP 2: FRONTEND INSTALLATION & LAUNCH
--------------------------------------------------------------------------------
Open a second PowerShell window:

1. Navigate to the dashboard directory:
   cd C:\Projects\supply-chain-risk-system\dashboard

2. Install dependencies (first time only):
   npm install

3. Start the Vite development server:
   npm run dev

   * Frontend URL: http://localhost:5173

--------------------------------------------------------------------------------
STEP 3: AUTHENTICATING IN THE DASHBOARD
--------------------------------------------------------------------------------
1. Navigate to http://localhost:5173 in your browser.
2. Click "Session credentials" in the left sidebar menu (gear icon).
3. In the slide-out drawer:
   - API base URL: http://localhost:8000
   - API key: admin123
   - Role setting: admin
4. Click "Save session settings". The dashboard will refresh and load data.

--------------------------------------------------------------------------------
STEP 4: RUNNING THE END-TO-END PIPELINE & TESTS
--------------------------------------------------------------------------------
- To run automated tests & linter:
  .\scripts\dev.ps1 test

- To audit dataset archive integrity:
  .\scripts\dev.ps1 audit

- To execute the full risk analysis pipeline on local archives:
  .\scripts\dev.ps1 run-pipeline


================================================================================
7. COMMAND CHEATSHEET & OPERATIONAL TROUBLESHOOTING
================================================================================

COMMAND CHEATSHEET:
--------------------------------------------------------------------------------
| Action                             | PowerShell Command                      |
|------------------------------------|-----------------------------------------|
| Setup Virtualenv & Dependencies    | .\scripts\dev.ps1 setup                 |
| Run Unit Tests & Ruff Lint         | .\scripts\dev.ps1 test                  |
| Run Dataset Archive Audit          | .\scripts\dev.ps1 audit                 |
| Train & Evaluate Baseline Models   | .\scripts\dev.ps1 train                 |
| Run Full Local Pipeline            | .\scripts\dev.ps1 run-pipeline          |
| Start Backend FastAPI Server       | .\scripts\dev.ps1 run-api               |
| Start Frontend React Dashboard     | cd dashboard; npm run dev               |
| Run Frontend Tests                 | cd dashboard; npm test                  |
| Build Frontend for Production      | cd dashboard; npm run build             |

COMMON ISSUES & RESOLUTIONS:
--------------------------------------------------------------------------------
1. Error: "Could not read package.json (ENOENT)"
   Reason: `npm run dev` was run from the project root instead of `dashboard/`.
   Fix: Run `cd C:\Projects\supply-chain-risk-system\dashboard` before npm.

2. Error: "OPTIONS /api/v1/... 400 Bad Request"
   Reason: Browser CORS check failed because port 5173 was missing from CORS_ORIGINS.
   Fix: Add `http://localhost:5173,http://127.0.0.1:5173` to `CORS_ORIGINS` in `.env`
   and restart the backend.

3. Error: "GET /api/v1/... 401 Unauthorized"
   Reason: Dashboard session has not stored the API key yet.
   Fix: Click "Session credentials" in the dashboard and save `admin123`.

4. Error: "[WinError 10054] An existing connection was forcibly closed"
   Reason: Windows asyncio logs this when a browser terminates a rejected CORS request.
   Fix: Resolved automatically once CORS_ORIGINS includes the frontend port.
================================================================================
