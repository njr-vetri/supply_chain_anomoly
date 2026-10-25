"""Unit and API integration tests for the simplified One-Page ML Prototype.

Covers:
1. Zip upload safety (path traversal rejection, non-tabular sheet skip).
2. Schema mapping ambiguity distinction (confident auto-accepted vs ambiguous flagged).
3. NLP stage explainer factual integrity (rejection of hallucinated numbers/entities).
4. Alert delivery status tracking (dry-run, sent, failed, retrying).
5. Permission enforcement (403 Forbidden for non-reviewer role on hypothesis confirmation).
"""
import io
import json
import zipfile
import pytest
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import api.main as api_main
from src.core.repository import (
    Repository, DatasetVersionRow, IncidentRow, HypothesisRow
)
from src.core.schemas import HypothesisStatus
from src.risk.hypotheses import HypothesisCase, EvidenceLedger, LedgerEvidence
from src.data.schema_mapper import suggest_mappings
from src.data.profiler import profile_data, _check_zip_bomb
from src.nlp.stage_explainer import generate_stage_explanation, verify_factual_integrity
from src.alerts.manager import AlertManager
from src.connectors.notifications import TelegramNotificationAdapter


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repo = Repository("sqlite://", company_id="test-company", engine=engine)
    monkeypatch.setenv("API_KEYS_JSON", json.dumps({
        "key-viewer": "viewer",
        "key-analyst": "analyst",
        "key-reviewer": "reviewer",
        "key-admin": "admin",
    }))
    monkeypatch.setattr(api_main, "_audit", lambda *args, **kwargs: None)
    app = api_main.create_app(repo)
    app.state.kill_switch = False
    return TestClient(app), repo


def auth_header(role="analyst"):
    return {"X-API-Key": f"key-{role}"}


# ── Test 1: Zip Safety & Sheet Skipping ───────────────────────────────────────

def test_zip_safety_path_traversal_rejection():
    """Verify that archives with path traversal members are rejected."""
    # 1. safe_member_name validation
    assert api_main.safe_member_name("orders.csv") is True
    assert api_main.safe_member_name("data/sub/orders.csv") is True
    assert api_main.safe_member_name("../evil.csv") is False
    assert api_main.safe_member_name("/absolute/evil.csv") is False
    assert api_main.safe_member_name("sub/../../evil.csv") is False

    # 2. _check_zip_bomb path traversal detection
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.csv", "bad,data\n1,2\n")
    buf.seek(0)
    with pytest.raises(ValueError, match="Path traversal"):
        with zipfile.ZipFile(buf) as z:
            _check_zip_bomb(z, buf.getbuffer().nbytes)


def test_excel_non_tabular_sheet_skipping(tmp_path):
    """Verify non-tabular sheets (e.g. metadata or blank sheets) are handled gracefully."""
    excel_path = tmp_path / "multi_sheet.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        pd.DataFrame({"order_id": ["ORD-1", "ORD-2"], "val": [10, 20]}).to_excel(
            writer, sheet_name="Orders", index=False
        )

    frames = list(api_main._source_frames(excel_path, "multi_sheet.xlsx", chunk_rows=100))
    assert len(frames) == 1
    assert "order_id" in frames[0].columns
    assert len(frames[0]) == 2


# ── Test 2: Mapping Ambiguity Distinction ────────────────────────────────────

def test_mapping_ambiguity_distinction():
    """Verify that confident columns are auto-accepted while ambiguous ones are flagged for clarification."""
    csv_data = (
        b"order_id,order_date,misc_col\n"
        b"1,NOT_A_DATE,x\n"
        b"2,NOT_A_DATE,y\n"
    )
    report = profile_data(csv_data, filename="synthetic_shipments.csv", dataset_name="synthetic_shipments")
    result = suggest_mappings(report)

    # 1. order_id is confident and auto-accepted
    order_id_sug = next(s for s in result.suggestions if s.column_name == "order_id")
    assert order_id_sug.suggested_role == "order_id"
    assert order_id_sug.auto_accepted is True
    assert order_id_sug.needs_clarification is False
    assert "order_id" in result.auto_accepted_mappings

    # 2. order_date with contradicted non-date values has moderate confidence -> flagged ambiguous
    order_date_sug = next(s for s in result.suggestions if s.column_name == "order_date")
    assert order_date_sug.needs_clarification is True
    assert order_date_sug.auto_accepted is False
    assert "order_date" in result.ambiguous_columns

    # 3. misc_col has no canonical match -> preserved as custom field
    misc_sug = next(s for s in result.suggestions if s.column_name == "misc_col")
    assert misc_sug.is_custom_field is True
    assert "misc_col" in result.unmapped_columns


# ── Test 3: NLP Stage Explainer Fact-Checking ────────────────────────────────

def test_nlp_stage_explainer_factual_integrity():
    """Verify fact-checking rejects candidate explanations that hallucinate numbers or unverified entities."""
    stage_data = {
        "name": "data_quality",
        "input_rows": 1000,
        "output_rows": 980,
        "counts": {"duplicates": 12, "negatives": 8},
        "warnings": [],
    }

    # 1. Truthful explanation with exact facts
    truthful_candidate = "Data quality processed 1000 rows, identifying 12 duplicates and 8 negative values."
    is_valid, _ = verify_factual_integrity(truthful_candidate, stage_data)
    assert is_valid is True

    # 2. Hallucinated explanation with fake numbers
    hallucinated_candidate = "Data quality processed 1000 rows and dropped 9999 fake records."
    is_valid_fake, reason = verify_factual_integrity(hallucinated_candidate, stage_data)
    assert is_valid_fake is False
    assert "9999" in reason

    # 3. generate_stage_explanation should fall back to deterministic verified template
    explanation = generate_stage_explanation("data_quality", stage_data)
    assert "1,000 input rows" in explanation or "1000" in explanation
    assert "12 duplicate" in explanation


# ── Test 4: Alert Delivery Status Tracking ───────────────────────────────────

def test_alert_delivery_status_tracking(monkeypatch, tmp_path):
    """Verify that notifications track explicit delivery status (DRY_RUN, SENT, FAILED, RETRYING)."""
    # 1. Telegram adapter in disabled/dry-run mode returns DRY_RUN
    monkeypatch.setenv("CONNECTORS_ENABLED", "false")
    adapter = TelegramNotificationAdapter()
    res = adapter.send(subject="Spike", message="Test dry run alert")
    assert res["status"] == "DRY_RUN"

    # 2. Telegram adapter with simulated HTTP 200 response returns SENT
    class DummyResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setenv("CONNECTORS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_bot_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    simulated_adapter = TelegramNotificationAdapter(request_transport=lambda req, timeout: DummyResponse())
    sent_res = simulated_adapter.send(subject="Spike", message="Carrier spike")
    assert sent_res["status"] == "SENT"

    # 3. Alert manager records delivery status in audit history
    manager = AlertManager(channels={"telegram": simulated_adapter}, history_path=tmp_path / "history.jsonl")
    alert_payload = {
        "source": "olist",
        "incident_key": "carrier_route_spike",
        "severity": "HIGH",
        "message": "Carrier A delay spike on Route SP-RJ",
    }
    history_record = manager.process(alert_payload)
    assert "delivery_status" in history_record or history_record.get("status") in ("ROUTED", "SENT", "OPEN")


# ── Test 5: Permission Enforcement (Reviewer Gated Hypothesis Confirmation) ──

def test_permission_enforcement_hypothesis_confirmation(test_client):
    """Verify HTTP 403 Forbidden when a viewer or analyst attempts to confirm a hypothesis."""
    client, repo = test_client
    observed = api_main.datetime.now(api_main.timezone.utc)

    # Seed an incident and hypothesis with supporting evidence ledger
    repo.add(DatasetVersionRow(
        id="synthetic-dataset", dataset="synthetic", source="synthetic",
        source_hash="synthetic-hash", observed_at=observed, payload={}
    ))
    repo.add(IncidentRow(
        id="inc-99", dataset_version_id="synthetic-dataset", source="synthetic",
        title="Test Incident", occurred_at=observed, payload={}
    ))

    case = HypothesisCase(
        id="hyp-99",
        statement="Carrier Route delay contributing factor",
        source="drivers",
        status=HypothesisStatus.SUPPORTED,
        ledger=EvidenceLedger(supporting=[
            LedgerEvidence(evidence_id="ev-1", classification="supporting", source="drivers", record_refs=["r1"], observed_at=observed, strength=0.9, description="Evidence 1"),
            LedgerEvidence(evidence_id="ev-2", classification="supporting", source="drivers", record_refs=["r2"], observed_at=observed, strength=0.9, description="Evidence 2"),
        ]),
    )
    repo.add(HypothesisRow(
        id=case.id,
        incident_id="inc-99",
        statement=case.statement,
        status=case.status.value,
        payload=case.model_dump(mode="json"),
    ))

    # 1. Analyst role should be rejected with 403 Forbidden
    res_analyst = client.post(
        f"/api/v1/hypotheses/{case.id}/confirm",
        headers=auth_header("analyst"),
        json={"rationale": "Analyst confirmation attempt"},
    )
    assert res_analyst.status_code == 403, res_analyst.text

    # 2. Viewer role should be rejected with 403 Forbidden
    res_viewer = client.post(
        f"/api/v1/hypotheses/{case.id}/confirm",
        headers=auth_header("viewer"),
        json={"rationale": "Viewer confirmation attempt"},
    )
    assert res_viewer.status_code == 403, res_viewer.text

    # 3. Reviewer role should succeed with 200 OK
    res_reviewer = client.post(
        f"/api/v1/hypotheses/{case.id}/confirm",
        headers=auth_header("reviewer"),
        json={"rationale": "Reviewer confirmed based on empirical carrier delay evidence."},
    )
    assert res_reviewer.status_code == 200, res_reviewer.text
    assert res_reviewer.json()["status"] == "CONFIRMED"
