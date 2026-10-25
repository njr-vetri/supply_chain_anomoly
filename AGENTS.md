# PROJECT: Autonomous, Transparent Supply-Chain Risk Monitoring & Response System

Academic project. Python, CPU-only (16 GB RAM). Beginner owner: keep code simple, modular, commented, typed.

PRIORITIES: (1) Novelty via integration, never claim an algorithm is novel. (2) Automation with human approval for high-impact actions, dry-run by default. (3) Transparency: every decision traceable to evidence, provenance, model version, limitations, history.

DATASETS (separate sources, never merge or invent links between them):

- Olist: orders, delivery timelines, delays, reviews
- DataCo: delay classification, leakage-prone, check carefully
- UCI Online Retail II: demand/forecasting only. Not inventory, no stockout labels.

HARD RULES

- Never modify, move, delete or commit dataset archives or raw data. Raw is read-only.
- Never invent metrics, results, evidence, labels or license details. Unknown = "UNKNOWN".
- Synthetic data only for unit tests, clearly labelled synthetic. Never use it to claim accuracy.
- Do not use the old 2,000-row dataset.
- No secrets in code. Use .env (git-ignored) and .env.example.
- Root causes: UNVERIFIED -> SUPPORTED -> CONFIRMED (or REJECTED/CLOSED). Only a human reviewer can set CONFIRMED.
- Return "Insufficient evidence" when support is inadequate.
- Keep facts, predictions, hypotheses, recommendations separate in every schema.
- Prevent temporal and target leakage. Compare every model against a simple baseline. Time-based splits.
- All actions default to dry-run. Kill switch, rate limit and audit log before any action.
- Add a dependency only when the phase needs it, and add it to requirements.txt.
- The frontend lives in `dashboard/`; it may be edited in Phase 11 only. Do not touch `src/ui`.
- Do not run git init or push unless told.

WORKFLOW PER PHASE

1. Inspect existing files first. Never overwrite blindly; merge.
2. Implement only the requested phase.
3. Write pytest tests. Run them. Report the actual commands and real results.
4. Update docs/PROGRESS.md (what was done, what's pending, known limitations).
5. Never claim a check passed unless you ran it. Stop at the end of the phase.
