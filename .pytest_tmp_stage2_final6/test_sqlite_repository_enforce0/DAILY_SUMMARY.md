# Daily pipeline summary

Counts are computed from persisted SQLite rows. The audit count includes the append-only JSONL history imported into SQLite; per-run JSON under `data/processed/pipeline_runs/` distinguishes current executions.

```json
{
  "period_start": "2026-10-23T00:00:00+00:00",
  "period_end": "2026-10-24T00:00:00+00:00",
  "dataset_versions_by_dataset": {
    "synthetic": 1
  },
  "audit_events": 0,
  "event_types": {},
  "rows_created_today": {
    "dataset_versions": 1,
    "model_versions": 0,
    "predictions": 0,
    "anomalies": 0,
    "incidents": 0,
    "evidence": 0,
    "hypotheses": 0,
    "recommendations": 0,
    "approvals": 0,
    "actions": 0,
    "outcomes": 0,
    "audit_events": 0,
    "quality_snapshots": 0
  },
  "entity_counts_by_source": {},
  "total_rows_stored": {
    "workspaces": 0,
    "projects": 0,
    "data_sources": 0,
    "mapping_versions": 0,
    "import_jobs": 0,
    "dataset_versions": 1,
    "model_versions": 0,
    "predictions": 0,
    "anomalies": 0,
    "incidents": 0,
    "evidence": 0,
    "hypotheses": 0,
    "recommendations": 0,
    "approvals": 0,
    "actions": 0,
    "outcomes": 0,
    "audit_events": 0
  }
}
```
