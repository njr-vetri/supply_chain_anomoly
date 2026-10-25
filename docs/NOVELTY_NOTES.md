# Novelty notes

## Integration contribution

The project's contribution is an integration of existing methods and safety controls into one source-separated local workflow:

- archive-level profiling and validation with quarantine and lineage;
- temporally constrained delivery, shipping, and transaction-demand features;
- rule/statistical/Isolation Forest anomaly signals kept separate from severity;
- baseline comparisons for delay classification and demand forecasting;
- evidence-linked incidents, explicit alternative explanations and limitations;
- reviewer-gated hypothesis lifecycle, factor-by-factor risk prioritization, and constrained recommendations;
- relationship graphs labelled established or inferred, human approval records, dry-run actions, local alerts, SQLite persistence, and hash-chained audit events;
- API access that exposes traceable records while retaining dry-run and role boundaries.

This is an integration contribution. It does **not** claim a novel algorithm, model, feature engineering method, risk score, or causal inference method.

## Literature review still required

- Review supply-chain disruption monitoring and early-warning system architectures against this integration.
- Compare incident/evidence provenance and human-in-the-loop root-cause workflows with established decision-support systems.
- Review anomaly detection methods and threshold selection for sparse, heterogeneous logistics data.
- Review temporal leakage prevention and delay label definitions in public logistics datasets.
- Review calibration-aware risk prioritization and uncertainty/missingness handling.
- Review graph exposure analysis and the boundary between network propagation and causal claims.
- Review privacy and explainability limits for review-text processing and SHAP interpretation.
- Verify dataset terms and any methodological assumptions with authoritative source documentation.

Until that review is completed, novelty is limited to the stated system integration and has not been established relative to prior literature.
