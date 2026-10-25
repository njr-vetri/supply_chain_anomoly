"""Local connector interfaces and result types."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class ConnectorHealth:
    name: str
    status: str
    checked_at: str
    detail: str


@dataclass(frozen=True)
class RecordBatch:
    connector: str
    source_ref: str
    source_sha256: str | None
    records: list[dict[str, Any]]
    label: str = "REAL"


class SourceConnector(Protocol):
    def health_check(self) -> ConnectorHealth: ...
    def read_batches(self) -> Iterable[RecordBatch]: ...


class NotificationConnector(Protocol):
    def health_check(self) -> ConnectorHealth: ...
    def send(self, *, subject: str, message: str) -> dict[str, Any]: ...
