// Values transcribed exactly from docs/EVALUATION_REPORT.md.
// This is the computed report snapshot, not a live API response.
export const evaluationSource = 'docs/EVALUATION_REPORT.md'

export const delayEvaluation = [
  { dataset: 'olist', model: 'baseline_majority', precision: 0.0, recall: 0.0, f1: 0.0, pr_auc: 0.05291800559759511, roc_auc: 0.5, brier: 0.05291800559759511 },
  { dataset: 'olist', model: 'baseline_simple_rule', precision: 0.1687289088863892, recall: 0.5876591576885406, f1: 0.26218046755516716, pr_auc: 0.12097534347543688, roc_auc: 0.7129452139342938, brier: 0.1750285062713797 },
  { dataset: 'olist', model: 'logistic_regression', precision: 0.0, recall: 0.0, f1: 0.0, pr_auc: 0.07258112644112336, roc_auc: 0.6201039056516487, brier: 0.05153097754671182 },
  { dataset: 'olist', model: 'decision_tree', precision: 0.17713118938233793, recall: 0.33986287952987265, f1: 0.23288590604026846, pr_auc: 0.10773915154682995, roc_auc: 0.5830824453563226, brier: 0.11759362702156763 },
  { dataset: 'olist', model: 'random_forest', precision: 0.04904559915164369, recall: 0.1811949069539667, f1: 0.0771959107031087, pr_auc: 0.053212703344567285, roc_auc: 0.4906639066979197, brier: 0.1749001652843584 },
  { dataset: 'dataco', model: 'baseline_majority', precision: 0.546572496884088, recall: 1.0, f1: 0.706817815505292, pr_auc: 0.546572496884088, roc_auc: 0.5, brier: 0.4534275031159119 },
  { dataset: 'dataco', model: 'baseline_simple_rule', precision: 0.7965635738831615, recall: 0.5873112394851525, f1: 0.6761171391902928, pr_auc: 0.693395066176642, roc_auc: 0.7032518569913698, brier: 0.30754743110372523 },
  { dataset: 'dataco', model: 'logistic_regression', precision: 0.8421094432531173, recall: 0.5372960372960373, f1: 0.6560247486465584, pr_auc: 0.7906064896183613, roc_auc: 0.7279537892452298, brier: 0.19763461592206613 },
  { dataset: 'dataco', model: 'decision_tree', precision: 0.8263017863930064, recall: 0.5508259856085943, f1: 0.6610112803672961, pr_auc: 0.7833790967641993, roc_auc: 0.7212518797359969, brier: 0.19923746714705529 },
  { dataset: 'dataco', model: 'random_forest', precision: 0.8397607429560837, recall: 0.5406911928651059, f1: 0.657829839704069, pr_auc: 0.7883454343167225, roc_auc: 0.7247030193405412, brier: 0.19978844696131234 },
]

export const reviewEvaluation = [
  { model: 'BERTimbau (CPU re-evaluation)', macro_precision: 0.6868517447613883, macro_recall: 0.6774773825527044, macro_f1: 0.6774153223722116, accuracy: 0.8825251815413446 },
  { model: 'TF-IDF + Logistic Regression', macro_precision: 0.6555131043868735, macro_recall: 0.7004034388053769, macro_f1: 0.6705198260559485, accuracy: 0.8292340126493324 },
  { model: 'Majority baseline', macro_precision: 0.24135238541422657, macro_recall: 0.3333333333333333, macro_f1: 0.27998188405797103, accuracy: 0.7240571562426797 },
]

export const evaluationLimitations = [
  'Olist review labels are proxy score bands, not human-verified complaint or sentiment labels.',
  'Review classifier point metrics use one chronological holdout and do not establish future performance.',
  'No confidence interval or statistical significance test was computed for the BERT vs TF-IDF difference.',
  'Delay metrics describe target labels and do not establish delay causes.',
  'Online Retail II demand forecasting was not computed: 54 weeks were available; configured CV required more than 64.',
]
