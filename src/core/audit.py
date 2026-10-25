"""Append-only JSONL audit log with a SHA-256 hash chain."""

import hashlib
import json
from pathlib import Path
from typing import Any

from src.core.schemas import AuditEvent
from src.core.privacy import sanitize_for_log

GENESIS_HASH = "0" * 64
def _redact(value: Any, key: str = "") -> Any:
    return sanitize_for_log(value, key)


class AuditLog:
    """Writes events only by appending; each hash covers the previous hash and event."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, *, event_type: str, actor: str, source: str | None = None,
               record_refs: list[str] | None = None, details: dict[str, Any] | None = None) -> AuditEvent:
        events = self.read_all()
        previous = events[-1].event_hash if events else GENESIS_HASH
        payload = {"event_type": event_type, "actor": actor, "source": source,
                   "record_refs": record_refs or [], "details": _redact(details or {})}
        canonical = json.dumps({"previous_hash": previous, **payload}, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event = AuditEvent(**payload, previous_hash=previous, event_hash=digest)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(event.model_dump_json() + "\n")
        return event

    def read_all(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        return [AuditEvent.model_validate_json(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def verify(self) -> bool:
        previous = GENESIS_HASH
        for event in self.read_all():
            payload = {"event_type": event.event_type, "actor": event.actor, "source": event.source,
                       "record_refs": event.record_refs, "details": event.details}
            canonical = json.dumps({"previous_hash": previous, **payload}, sort_keys=True, separators=(",", ":"), default=str)
            if event.previous_hash != previous or hashlib.sha256(canonical.encode("utf-8")).hexdigest() != event.event_hash:
                return False
            previous = event.event_hash
        return True
