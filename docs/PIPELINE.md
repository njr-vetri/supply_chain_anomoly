# Phase 8 pipeline and storage

The default repository is a local SQLite file at `data/processed/supply_chain.db`; that path is ignored by Git. `config/settings.yaml:storage.url` is the only backend selection point. SQLAlchemy is used behind `Repository`, so a PostgreSQL SQLAlchemy URL can be selected later after installing the appropriate driver. No external database service is used by default.

Apply schema migrations with `alembic upgrade head`. Tables are created by the migration from the shared SQLAlchemy metadata. The repository also creates missing tables for a fresh local run.

Run one end-to-end pass with `python -m src.core.pipeline --root .`. Add `--dataset olist` (repeatable) to limit datasets, `--retry` for configured bounded retries, or `--interval-seconds N` to run periodically. `--database-url` can override the configured URL for a local test database. Runs are source-separated. ZIP archives are read in memory and never extracted or modified.

The pipeline records validation reports and quarantine counts before features are built. Quarantine manifests retain only archive hash, source member, chunk/row locator, and rejection reason; they do not copy row contents. Dated tables report source freshness against the configured age limit. It records anomaly flags (with configured per-run storage caps), predictions only when a saved classifier is available, source-referenced investigations and hypotheses, factor breakdowns, recommendations, and locally routed dry-run alerts. Model probabilities are explicitly marked uncalibrated and are excluded from calibrated-probability risk weighting. User text remains inert data. No business action is executed by this pipeline.

Data quality drift compares row count and per-column null rates to the prior snapshot for the same source member. Thresholds live in `config/settings.yaml`; this small statistical check is sufficient for the current audited CSV/workbook sources. Evidently is not needed for these checks.

The daily summary is generated from persisted SQLite rows at `docs/DAILY_SUMMARY.md`. The audit count also includes append-only JSONL history imported from prior executions; each current run has a JSON report in ignored `data/processed/pipeline_runs/`. Dataset licenses remain `UNKNOWN`; confirm publisher terms, attribution and redistribution conditions before sharing data-derived artifacts.
