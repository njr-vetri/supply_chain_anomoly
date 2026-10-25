"""Local background scheduler for recurring pipeline, connector checks, and workflow jobs."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class LocalScheduler:
    """Manages an in-process periodic scheduler thread for API/app background tasks."""

    def __init__(self, interval_seconds: int = 300, tick_callback: Callable[[], None] | None = None):
        self.interval_seconds = interval_seconds
        self.tick_callback = tick_callback
        env_enabled = os.getenv("SCHEDULER_ENABLED", "false").lower() in ("true", "1", "yes")
        self.enabled: bool = env_enabled
        self.running: bool = False
        self.last_run: datetime | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.running or not self.enabled:
            return
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="LocalSchedulerWorker")
        self._thread.start()
        logger.info("LocalScheduler started with interval %ds", self.interval_seconds)

    def stop(self) -> None:
        if not self.running:
            return
        self._stop_event.set()
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("LocalScheduler stopped")

    def toggle(self, enabled: bool) -> dict[str, Any]:
        self.enabled = enabled
        if self.enabled:
            self.start()
        else:
            self.stop()
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "last_run": self.last_run.isoformat() if self.last_run else None,
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.last_run = datetime.now(timezone.utc)
                if self.tick_callback:
                    self.tick_callback()
            except Exception as exc:  # noqa: BLE001
                logger.warning("LocalScheduler cycle error: %s", exc)
            self._stop_event.wait(self.interval_seconds)


class LocalWorkflowScheduler:
    """Manages queued connector jobs, idempotency, retry loops and sanitized execution history."""

    def __init__(
        self,
        runner: Callable[[dict[str, Any]], Any],
        history_path: Path | None = None,
        interval_seconds: int = 300,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.runner = runner
        self.history_path = Path(history_path) if history_path else None
        self.interval_seconds = interval_seconds
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleeper = sleeper
        self._jobs: dict[str, dict[str, Any]] = {}
        self._seen_idempotency_keys: set[str] = set()
        self._queue: list[str] = []

    def submit(
        self,
        trigger: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        # Validate for untrusted text/commands
        for k, v in payload.items():
            if k == "command" or any(bad in str(v).lower() for bad in ("delete", "drop", "exec", "rm ", ";")):
                raise ValueError(f"untrusted text in payload field '{k}'")

        if idempotency_key and idempotency_key in self._seen_idempotency_keys:
            return {"duplicate_suppressed": True, "idempotency_key": idempotency_key}

        if idempotency_key:
            self._seen_idempotency_keys.add(idempotency_key)

        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "trigger": trigger,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "status": "QUEUED",
            "attempts": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "duplicate_suppressed": False,
        }
        self._jobs[job_id] = job
        self._queue.append(job_id)
        return job

    def new_batch(
        self,
        batch_id: str,
        project_id: str | None = None,
        source_id: str | None = None,
        simulation_label: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "batch_id": batch_id,
            "project_id": project_id,
            "source_id": source_id,
            "simulation_label": simulation_label,
        }
        return self.submit(trigger="new_batch", payload=payload, idempotency_key=f"batch:{batch_id}")

    def timer_tick(self, slot: str | None = None) -> dict[str, Any]:
        payload = {"slot": slot or datetime.now(timezone.utc).isoformat()}
        return self.submit(trigger="timer", payload=payload, idempotency_key=f"timer:{payload['slot']}")

    def run_pending(self) -> list[dict[str, Any]]:
        results = []
        while self._queue:
            job_id = self._queue.pop(0)
            job = self._jobs[job_id]
            while job["attempts"] < self.max_attempts:
                job["attempts"] += 1
                try:
                    res = self.runner(job["payload"])
                    job["status"] = "COMPLETED"
                    job["result"] = res
                    break
                except Exception as exc:
                    if job["attempts"] >= self.max_attempts:
                        job["status"] = "FAILED"
                        job["error"] = f"{type(exc).__name__}: sanitized execution error"
                        break
                    if self.retry_backoff_seconds > 0:
                        self.sleeper(self.retry_backoff_seconds)
            results.append(job)
            self._record_history(job)
        return results

    def _record_history(self, job: dict[str, Any]) -> None:
        if not self.history_path:
            return
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        safe_job = {
            "id": job["id"],
            "trigger": job["trigger"],
            "status": job["status"],
            "attempts": job["attempts"],
            "created_at": job["created_at"],
        }
        if "error" in job:
            safe_job["error"] = job["error"]
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe_job) + "\n")

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._jobs.values())[-limit:]

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


# Global singleton instance for API/admin scheduler
scheduler = LocalScheduler()
