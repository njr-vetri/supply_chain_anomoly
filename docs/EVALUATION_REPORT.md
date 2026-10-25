# Evaluation report

Only executed results are shown. No accuracy claim is made.

Fixed random seed: `42`

## Delay classification

### olist

Chronological split: train 57,882, validation 19,294, test 19,294.

| Model | Test precision | Recall | F1 | PR-AUC | ROC-AUC | Brier |
|---|---:|---:|---:|---:|---:|---:|
| baseline_majority | 0.0000 | 0.0000 | 0.0000 | 0.0529 | 0.5 | 0.0529 |
| baseline_simple_rule | 0.1687 | 0.5877 | 0.2622 | 0.1210 | 0.7129452139342938 | 0.1750 |
| logistic_regression | 0.0000 | 0.0000 | 0.0000 | 0.0726 | 0.6201039056516487 | 0.0515 |
| decision_tree | 0.1771 | 0.3399 | 0.2329 | 0.1077 | 0.5830824453563226 | 0.1176 |
| random_forest | 0.0490 | 0.1812 | 0.0772 | 0.0532 | 0.4906639066979197 | 0.1749 |

### dataco

Chronological split: train 108,311, validation 36,103, test 36,105.

| Model | Test precision | Recall | F1 | PR-AUC | ROC-AUC | Brier |
|---|---:|---:|---:|---:|---:|---:|
| baseline_majority | 0.5466 | 1.0000 | 0.7068 | 0.5466 | 0.5 | 0.4534 |
| baseline_simple_rule | 0.7966 | 0.5873 | 0.6761 | 0.6934 | 0.7032518569913698 | 0.3075 |
| logistic_regression | 0.8421 | 0.5373 | 0.6560 | 0.7906 | 0.7279537892452298 | 0.1976 |
| decision_tree | 0.8263 | 0.5508 | 0.6610 | 0.7834 | 0.7212518797359969 | 0.1992 |
| random_forest | 0.8398 | 0.5407 | 0.6578 | 0.7883 | 0.7247030193405412 | 0.1998 |

## Demand forecasting

Online Retail II transaction demand forecast; not stockout prediction. Metric: MAE.

### online_retail_II.xlsx [Year 2009-2010]

| Baseline | Mean rolling-origin MAE | Status |
|---|---:|---|
| naive | 44.1954 | RUN |
| moving_average | 37.7374 | RUN |
| seasonal_naive | N/A | SKIPPED |

Skipped baselines:
- **seasonal_naive**: Insufficient history for seasonal period: 54 weeks <= 52 + 4 window

### online_retail_II.xlsx [Year 2010-2011]

| Baseline | Mean rolling-origin MAE | Status |
|---|---:|---|
| naive | 42.5899 | RUN |
| moving_average | 37.6359 | RUN |
| seasonal_naive | N/A | SKIPPED |

Skipped baselines:
- **seasonal_naive**: Insufficient history for seasonal period: 54 weeks <= 52 + 4 window

## Limitations

DataCo target construction is not independently verified; leakage-prone outcome fields are excluded by documented feature allowlist.
Olist labels require observed delivery and estimated dates, so undelivered/canceled records are excluded.
Retail II contains transactions only; no inventory or stockout labels are available.
Metrics are omitted for any dataset/model run that could not execute in the active environment.
