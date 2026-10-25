"""Synthetic alert fixtures verify grouping, routing, deduplication and history."""
from datetime import datetime, timezone, timedelta

from src.alerts.manager import AlertManager


class MemoryChannel:
    def __init__(self):
        self.sent = []

    def send(self, alert):
        self.sent.append(alert)


def test_alert_duplicate_is_suppressed_and_history_is_retained(tmp_path):
    now = [datetime(2025, 1, 1, tzinfo=timezone.utc)]
    console, file = MemoryChannel(), MemoryChannel()
    settings = {"dedup_window_seconds": 60, "severity_routes": {"HIGH": ["console", "file"]},
                "escalation": [], "group_by": ["source", "incident_key"]}
    manager = AlertManager(channels={"console": console, "file": file}, history_path=tmp_path / "alerts.jsonl",
                           settings=settings, clock=lambda: now[0])
    first = manager.process({"source": "synthetic", "incident_key": "incident-1", "severity": "HIGH",
                             "message": "untrusted inert text"})
    now[0] += timedelta(seconds=1)
    duplicate = manager.process({"source": "synthetic", "incident_key": "incident-1", "severity": "HIGH"})
    assert first["event"] == "alert_routed"
    assert duplicate["event"] == "duplicate_suppressed"
    assert len(console.sent) == 1 and len(file.sent) == 1
    assert len(manager.history()) == 2
    restarted = AlertManager(channels={"console": console, "file": file}, history_path=tmp_path / "alerts.jsonl",
                             settings=settings, clock=lambda: now[0] + timedelta(seconds=1))
    assert restarted.process({"source": "synthetic", "incident_key": "incident-1", "severity": "HIGH"})[
        "event"] == "duplicate_suppressed"


def test_alert_escalation_routes_using_policy(tmp_path):
    now = [datetime(2025, 1, 1, tzinfo=timezone.utc)]
    console = MemoryChannel()
    settings = {"dedup_window_seconds": 1, "severity_routes": {"MEDIUM": [], "HIGH": ["console"]},
                "escalation": [{"after_seconds": 10, "from_severity": "MEDIUM", "to_severity": "HIGH"}],
                "group_by": ["source", "incident_key"]}
    manager = AlertManager(channels={"console": console}, history_path=tmp_path / "alerts.jsonl",
                           settings=settings, clock=lambda: now[0])
    manager.process({"source": "synthetic", "incident_key": "group", "severity": "MEDIUM"})
    now[0] += timedelta(seconds=11)
    escalated = manager.process({"source": "synthetic", "incident_key": "group", "severity": "MEDIUM"})
    assert escalated["severity"] == "HIGH"
    assert console.sent[-1]["severity"] == "HIGH"
