# Known Limitations & Academic Scope Boundaries

This system is an academic research prototype designed to investigate autonomous, transparent risk monitoring and gated human response workflows. It is **not production-ready** and must not be operated against live enterprise supply chains or physical logistics networks without addressing the architectural and operational limitations detailed below.

---

## 1. Data Integrity, Archives & Labels

- **Static Historical Datasets**: Olist (2016–2018), DataCo, and UCI Online Retail II (2009–2011) are static, historical snapshots rather than live event streams. Timestamp freshness monitors intentionally report these sources as stale.
- **Dataset License Status**: In compliance with provenance rules, all dataset licenses remain classified as `UNKNOWN` until formal commercial redistribution agreements are reviewed by counsel.
- **Strict Data Isolation**: No synthetic or heuristic record linkage is performed across the separate datasets. Olist, DataCo, and UCI Online Retail II are isolated operational islands.
- **Delay Label Proxies**: Olist delay labels are calculated as `delivered_customer_date > estimated_delivery_date`. These are historical observations, not verified operational causes.
- **Target Leakage in DataCo**: DataCo contains numerous fields that encode outcomes (e.g., `Delivery Status`, `Late_delivery_risk`). While our allowlist filters known post-outcome columns, unobserved temporal leakage may still exist in unmapped attributes.
- **Demand Forecasting Boundaries**: UCI Online Retail II contains sales transaction invoices only. It does not record warehouse inventory levels, safety stock, backorders, or stockouts. It must never be used to claim inventory replenishment accuracy.
- **Synthetic Test Data**: Synthetic company data (`acme_industrial`) is generated solely for unit and acceptance testing of API contracts. It is explicitly labelled `SYNTHETIC` and must never be used to claim model accuracy or operational performance.

---

## 2. Machine Learning, Causality & Explanations

- **Correlation vs. Causation**: Statistical anomaly scores (IQR, Robust Z-score, Isolation Forest), feature associations, and SHAP attribution values identify statistical correlations and exposure patterns. They do **not** establish causal mechanisms or root-cause ground truth.
- **Causal Inference**: Structural causal models, DAG back-door adjustments, and instrumental variable analyses are not implemented. Root-cause confirmation is reserved exclusively for authenticated human reviewers.
- **Model Evaluation Holdouts**: Models are evaluated on single chronological holdout splits against simple baselines (majority class or rolling mean). No claims of generalization across future temporal distributions or other supply networks can be made.
- **Drift as Warning Only**: Distribution drift detection (mean shifts, null rate expansion) emits informational warnings to human analysts. It never triggers automated retraining pipelines.

---

## 3. Operations, Mitigations & What-If Simulations

- **Dry-Run Enforcement**: All remediation actions default strictly to `dry_run: true`. The system does not interface with physical ERPs, warehouse management systems (WMS), or freight booking APIs.
- **What-If Simulations**: Scenario calculators evaluate hypothetical relative risk reductions based on user-supplied assumptions. All simulation outputs are explicitly branded with the `HYPOTHETICAL` warning badge.
- **Process-Local Kill Switch**: The emergency kill switch operates in application memory. In multi-worker or distributed deployments, a centralized distributed state store (e.g. Redis) would be required.
- **Approval Gatekeeping**: High-impact recommendations require reviewer approval. While enforced by RBAC, emergency bypass procedures for life-safety or legal exceptions are not implemented.

---

## 4. Multi-Tenancy, Security & Persistence

- **Local SQLite Store**: Persistence uses SQLite (`data/processed/supply_chain.db`). While WAL mode is enabled, SQLite is designed for single-node development and does not support distributed multi-region high availability or horizontal scale.
- **Audit Hash Chaining**: SHA-256 hash chaining detects post-hoc database record tampering but cannot prevent root-level operating system deletion or filesystem rewriting.
- **PII Redaction Limitations**: Log redaction relies on heuristic regular expressions and common attribute names (`customer_name`, `email`, `phone`). Unconventional PII strings or numeric identifiers may not be masked.
- **Authentication**: JWT bearer tokens and bcrypt password hashing are implemented with expiring validity. Enterprise single sign-on (SAML / OAuth2 / OIDC) and hardware-backed MFA are not implemented.

---

## 5. Compute & Hardware Constraints

- **CPU-Only Execution**: The system is designed and tested on a CPU-only architecture with 16 GB RAM. GPU-accelerated deep learning (e.g., large transformer embeddings, graph neural networks) is omitted in favor of CPU-friendly Scikit-Learn models.
- **Bounded Query Execution**: Dependency graph queries are capped at 5,000 nodes and 500 neighborhood hops to prevent memory exhaustion and browser UI freezing.
