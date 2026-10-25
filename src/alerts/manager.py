"""Incident grouping, duplicate suppression, severity routing and escalation."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

from src.core.config import load_settings
from src.core.privacy import sanitize_for_log
from src.alerts.channels import AlertChannel


SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class AlertManager:
    def __init__(self, *, channels: dict[str, AlertChannel], history_path: Path | str,
                 settings: dict[str, Any] | None = None, clock=None):
        self.settings = settings or load_settings().alerts
        self.channels = channels
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._seen: dict[str, dict[str, Any]] = {}
        # Restore groups so duplicate suppression continues across process restarts.
        if self.history_path.exists():
            for event in self.history():
                if event.get("event") == "duplicate_suppressed" and event.get("source") and event.get("incident_key"):
                    identity = hashlib.sha256(f"{event['source']}|{event['incident_key']}".encode()).hexdigest()
                    if identity in self._seen:
                        try:
                            self._seen[identity]["last_seen"] = datetime.fromisoformat(event["at"])
                            self._seen[identity]["duplicate_count"] = event.get("duplicate_count", 0)
                        except (KeyError, ValueError):
                            pass
                    continue
                if event.get("event") in {"alert_acknowledged", "alert_assigned"}:
                    prior_state = next((item for item in self._seen.values()
                                        if item["group_id"] == event.get("group_id")), None)
                    if prior_state:
                        if event["event"] == "alert_acknowledged":
                            prior_state["status"] = "ACKNOWLEDGED"
                            prior_state["acknowledged_by"] = event.get("actor")
                        else:
                            prior_state["assigned_to"] = event.get("assigned_to")
                    continue
                if event.get("event") != "alert_routed" or not event.get("source") or not event.get("incident_key"):
                    continue
                identity = hashlib.sha256(f"{event['source']}|{event['incident_key']}".encode()).hexdigest()
                try:
                    first_seen = datetime.fromisoformat(event["first_seen"])
                    last_seen = datetime.fromisoformat(event["last_seen"])
                except (KeyError, ValueError):
                    continue
                self._seen[identity] = {"first_seen": first_seen, "last_seen": last_seen,
                                        "group_id": event["group_id"], "duplicate_count": 0,
                                        "status": "OPEN", "assigned_to": None}

    def _append_history(self, event: dict[str, Any]) -> None:
        with self.history_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sanitize_for_log(event), ensure_ascii=False, default=str) + "\n")

    def history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        return [json.loads(line) for line in self.history_path.read_text(encoding="utf-8").splitlines() if line]

    def process(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Handle structured alert data only; text fields are never interpreted as commands."""
        if "source" not in alert or "incident_key" not in alert:
            raise ValueError("Alert requires source and incident_key")
        severity = str(alert.get("severity", "LOW")).upper()
        if severity not in SEVERITY_ORDER:
            raise ValueError("Unknown severity")
        now = self.clock()
        identity = hashlib.sha256(f"{alert['source']}|{alert['incident_key']}".encode()).hexdigest()
        prior = self._seen.get(identity)
        if prior:
            age = (now - prior["last_seen"]).total_seconds()
            if age <= self.settings["dedup_window_seconds"]:
                prior["last_seen"] = now
                prior["duplicate_count"] += 1
                event = {"event": "duplicate_suppressed", "group_id": prior["group_id"],
                         "source": alert["source"], "incident_key": alert["incident_key"],
                         "at": now.isoformat(), "duplicate_count": prior["duplicate_count"]}
                self._append_history(event)
                return event
            first_seen, group_id = prior["first_seen"], prior["group_id"]
        else:
            first_seen, group_id = now, identity[:16]
        elapsed = (now - first_seen).total_seconds()
        routed_severity = severity
        for policy in self.settings["escalation"]:
            if elapsed >= policy["after_seconds"] and routed_severity == policy["from_severity"]:
                routed_severity = policy["to_severity"]
        payload = {key: value for key, value in alert.items()}  # inbound fields remain inert serialized data
        payload.update({"group_id": group_id, "severity": routed_severity, "first_seen": first_seen.isoformat(),
                        "last_seen": now.isoformat(), "status": "ROUTED"})
        self._seen[identity] = {"first_seen": first_seen, "last_seen": now, "group_id": group_id, "duplicate_count": 0}
        self._seen[identity].update({"status": "OPEN", "assigned_to": None})
        routes = self.settings["severity_routes"].get(routed_severity, [])
        for channel_name in routes:
            channel = self.channels.get(channel_name)
            if channel is not None:
                channel.send(payload)
        event = {"event": "alert_routed", **payload, "routes": routes}
        self._append_history(event)
        return event

    def _group_state(self, group_id: str) -> dict[str, Any]:
        state = next((item for item in self._seen.values() if item["group_id"] == group_id), None)
        if state is None:
            raise KeyError("Alert group not found")
        return state

    def acknowledge(self, group_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ValueError("Acknowledger and reason are required")
        state = self._group_state(group_id)
        if state["status"] == "ACKNOWLEDGED":
            return {"status": "ACKNOWLEDGED", "group_id": group_id, "duplicate": True}
        state["status"] = "ACKNOWLEDGED"
        state["acknowledged_by"] = actor
        event = {"event": "alert_acknowledged", "group_id": group_id, "actor": actor,
                 "reason": reason, "at": self.clock().isoformat(), "status": "ACKNOWLEDGED"}
        self._append_history(event)
        return event

    def assign(self, group_id: str, *, actor: str, assigned_to: str) -> dict[str, Any]:
        if not actor.strip() or not assigned_to.strip():
            raise ValueError("Assigner and assignee are required")
        state = self._group_state(group_id)
        state["assigned_to"] = assigned_to
        event = {"event": "alert_assigned", "group_id": group_id, "actor": actor,
                 "assigned_to": assigned_to, "at": self.clock().isoformat(), "status": state["status"]}
        self._append_history(event)
        return event

    def group(self, group_id: str) -> dict[str, Any]:
        return dict(self._group_state(group_id))
