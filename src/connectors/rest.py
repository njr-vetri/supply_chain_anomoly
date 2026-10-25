"""REST polling connector using urllib and environment-sourced credentials."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.connectors.base import ConnectorHealth, RecordBatch


class RestPollingConnector:
    def __init__(self, endpoint: str, *, token_env: str | None = None, timeout_seconds: int = 15,
                 transport: Callable[[Request, int], bytes] | None = None):
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("REST endpoint must be an absolute HTTP(S) URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.endpoint = endpoint
        self.token_env = token_env
        self.timeout = timeout_seconds
        self.simulated = transport is not None
        self.transport = transport or self._read

    @staticmethod
    def _read(request: Request, timeout: int) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    def _request(self) -> Request:
        headers = {"Accept": "application/json"}
        token = os.getenv(self.token_env) if self.token_env else None
        if self.token_env and not token:
            raise RuntimeError("REST token environment variable is not configured")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return Request(self.endpoint, headers=headers, method="GET")

    def health_check(self) -> ConnectorHealth:
        try:
            self._request()
            status, detail = ("SIMULATED", "injected transport; no external endpoint was contacted") if self.simulated else (
                "CONFIGURED", "endpoint and credentials are configured; network not contacted")
        except RuntimeError:
            status, detail = "UNAVAILABLE", "required credential environment variable is missing"
        return ConnectorHealth("rest_polling", status, datetime.now(timezone.utc).isoformat(), detail)

    def poll(self) -> RecordBatch:
        body = self.transport(self._request(), self.timeout)
        try:
            parsed: Any = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("REST response was not valid JSON") from exc
        if isinstance(parsed, dict):
            records = parsed.get("items", parsed.get("data", [parsed]))
        else:
            records = parsed
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            raise ValueError("REST response must contain a list of JSON objects")
        return RecordBatch("rest_polling", self.endpoint, None, records,
                           label="SIMULATED" if self.simulated else "REAL")

    def read_batches(self):
        yield self.poll()
