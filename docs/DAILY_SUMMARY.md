# Daily pipeline summary

Counts are computed from persisted SQLite rows. The audit count includes the append-only JSONL history imported into SQLite; per-run JSON under `data/processed/pipeline_runs/` distinguishes current executions.

```json
{
  "period_start": "2026-10-23T00:00:00+00:00",
  "period_end": "2026-10-24T00:00:00+00:00",
  "dataset_versions_by_dataset": {
    "dataco": 1,
    "olist": 1,
    "online_retail_ii": 1
  },
  "audit_events": 22,
  "event_types": {
    "pipeline_alert_dry_run": 11,
    "pipeline_run_completed": 11
  },
  "rows_created_today": {
    "dataset_versions": 3,
    "model_versions": 3,
    "predictions": 3000,
    "anomalies": 2000,
    "incidents": 40,
    "evidence": 40,
    "hypotheses": 40,
    "recommendations": 60,
    "approvals": 0,
    "actions": 0,
    "outcomes": 0,
    "audit_events": 22,
    "quality_snapshots": 42
  },
  "entity_counts_by_source": {
    "dataco": {
      "predictions": 1000
    },
    "olist": {
      "predictions": 1000,
      "anomalies": 1000,
      "incidents": 20,
      "evidence": 20,
      "recommendations": 40
    },
    "online_retail_ii": {
      "predictions": 1000,
      "anomalies": 1000,
      "incidents": 20,
      "evidence": 20,
      "recommendations": 20
    }
  },
  "total_rows_stored": {
    "dataset_versions": 3,
    "model_versions": 3,
    "predictions": 3000,
    "anomalies": 2000,
    "incidents": 40,
    "evidence": 40,
    "hypotheses": 40,
    "recommendations": 60,
    "approvals": 0,
    "actions": 0,
    "outcomes": 0,
    "audit_events": 22
  }
}
```
