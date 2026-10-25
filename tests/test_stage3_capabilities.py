"""Stage 3 capability, validation, lineage and generic pipeline tests (synthetic only)."""
from datetime import datetime, timezone

from src.core.capabilities import assess_capabilities
from src.core.generic_pipeline import preview_pipeline, run_canonical_pipeline
from src.core.lineage import derive_with_lineage
from src.data.generic_validation import RuleConfig, validate_canonical_records


def test_sales_without_inventory_supports_demand_but_not_inventory_risk():
    report = assess_capabilities([{"name": "sales", "status": "ACCEPTED", "mapping": {
        "mappings": {"sku": "product_id", "units_sold": "quantity", "sold_at": "event_timestamp"}}}])
    assert report["features"]["demand_analysis"]["status"] == "AVAILABLE"
    assert report["features"]["inventory_risk"]["status"] == "UNSUPPORTED"
    assert "inventory_snapshot" in report["features"]["inventory_risk"]["missing_roles"]


def test_generic_quality_flags_unusual_records_without_rejecting_them():
    records = [
        {"event_id": "a", "event_timestamp": "2026-01-01T00:00:00Z", "quantity": 1},
        {"event_id": "a", "event_timestamp": "bad-date", "quantity": -2},
    ]
    report = validate_canonical_records(records, rules=RuleConfig(outliers=False))
    assert report.total_records == 2
    assert report.flagged_records == 1
    found = set(report.record_flags[0]["rules"])
    assert "duplicate_event_id" in found
    assert "invalid_date" in found
    assert "negative_quantity" in found
    assert report.unusual_values_rejected is False


def test_feature_lineage_has_definition_version_provenance_and_availability():
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    record = {"event_id": "synthetic-1", "source_record_ref": "fixture:1",
              "event_timestamp": "2026-01-01T00:00:00+00:00", "quantity": 3, "price": 4}
    derived = derive_with_lineage(record, computed_at=timestamp)
    assert {item.feature_name for item in derived} == {"event_age_seconds", "gross_line_value"}
    assert all(item.feature_version == "1.0.0" for item in derived)
    assert all(item.source_records == ["fixture:1"] for item in derived)
    assert all(item.available_at == timestamp for item in derived)


def test_generic_pipeline_skips_unsupported_steps_and_previews_without_execution(tmp_path):
    report = assess_capabilities([{"name": "sales", "status": "ACCEPTED", "mapping": {
        "mappings": {"sku": "product_id", "units_sold": "quantity", "sold_at": "event_timestamp"}}}])
    preview = preview_pipeline(report)
    assert preview["dry_run"] is True
    assert preview["message"].startswith("Preview only")
    canonical_file = tmp_path / "canonical.jsonl"
    canonical_file.write_text(
        '{"event_id":"synthetic-1","event_timestamp":"2026-01-01T00:00:00Z",'
        '"product_id":"sku-1","quantity":2,"source_record_ref":"fixture:1"}\n', encoding="utf-8")
    step_updates = []
    result = run_canonical_pipeline(canonical_files=[canonical_file], capabilities=report,
                                    retry_attempts=1, on_step=step_updates.append)
    statuses = {step["name"]: step["status"] for step in result["steps"]}
    assert result["status"] == "COMPLETED"
    assert statuses["demand_analysis"] == "COMPLETED"
    assert statuses["inventory_risk"] == "SKIPPED"
    assert result["records_read"] == 1
    assert any(step["name"] == "validation" and step["status"] == "RUNNING" for step in step_updates)
