"""Synthetic fixtures for Phase 10 security helpers."""
import json

from src.alerts.channels import FileChannel
from src.core.privacy import sanitize_for_log
from scripts.check_protected_files import is_protected_path
from scripts.security_scan import findings


def test_log_sanitizer_redacts_sensitive_fields_and_common_pii():
    cleaned = sanitize_for_log({"customer_email": "synthetic@example.test",
        "message": "Call +1 (555) 123-4567", "shipping_days": 4, "safe": "synthetic incident"})
    assert cleaned["customer_email"] == "[REDACTED]"
    assert "synthetic@example.test" not in str(cleaned)
    assert "123-4567" not in str(cleaned)
    assert cleaned["safe"] == "synthetic incident"
    assert cleaned["shipping_days"] == 4


def test_file_alert_channel_writes_redacted_values(tmp_path):
    target = tmp_path / "alerts.jsonl"
    FileChannel(target).send({"source": "synthetic", "customer_name": "Synthetic Person",
                              "note": "synthetic@example.test"})
    contents = target.read_text(encoding="utf-8")
    assert "Synthetic Person" not in contents
    assert "synthetic@example.test" not in contents
    assert json.loads(contents)["source"] == "synthetic"


def test_commit_guard_blocks_dataset_artifacts_and_all_data_models_paths():
    assert is_protected_path("archive.ZIP")
    assert is_protected_path("nested/data/raw/file.json")
    assert is_protected_path("models/bert/model.safetensors")
    assert is_protected_path("exports/table.csv")
    assert is_protected_path("db/local.sqlite3")
    assert is_protected_path("db/local.sqlite3-wal")
    assert not is_protected_path("docs/EVALUATION_REPORT.md")
    assert not is_protected_path("src/core/pipeline.py")


def test_secrets_scanner_reports_path_and_rule_without_value(tmp_path):
    secret_sample = "synthetic" + "-secret-value-123"
    credential_name = "pass" + "word"
    (tmp_path / "source.py").write_text(f'{credential_name} = "{secret_sample}"\n', encoding="utf-8")
    result = findings(tmp_path)
    assert result == [("source.py:1", "credential-assignment")]
    assert "synthetic-secret-value-123" not in str(result)
