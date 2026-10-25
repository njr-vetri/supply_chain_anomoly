"""Connect local source polling to idempotent timer/new-batch workflow jobs."""
from __future__ import annotations

import hashlib
from typing import Any

from src.connectors.base import SourceConnector
from src.workflow.scheduler import LocalWorkflowScheduler


class WorkflowEngine:
    def __init__(self, scheduler: LocalWorkflowScheduler):
        self.scheduler = scheduler

    def poll_connector(self, connector: SourceConnector, *, project_id: str | None = None,
                       source_id: str | None = None) -> list[dict[str, Any]]:
        """Queue one run per source batch; raw records remain owned by the connector."""
        health = connector.health_check()
        if health.status not in {"HEALTHY", "CONFIGURED", "SIMULATED"}:
            raise RuntimeError(f"Connector unavailable: {health.name} ({health.status})")
        jobs = []
        for batch in connector.read_batches():
            identity = f"{batch.connector}|{batch.source_ref}|{batch.source_sha256 or ''}"
            batch_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            jobs.append(self.scheduler.new_batch(batch_id, project_id=project_id, source_id=source_id,
                                                 simulation_label=batch.label))
        return jobs

    def timer_trigger(self, *, slot: str | None = None) -> dict[str, Any]:
        return self.scheduler.timer_tick(slot=slot)

    def run_pending(self) -> list[dict[str, Any]]:
        return self.scheduler.run_pending()

    def start_timer(self) -> None:
        self.scheduler.start()

    def stop_timer(self) -> None:
        self.scheduler.stop()

    def job(self, job_id: str) -> dict[str, Any] | None:
        return self.scheduler.get(job_id)

    def jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.scheduler.history(limit)
