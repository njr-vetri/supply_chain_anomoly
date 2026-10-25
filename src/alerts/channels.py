"""Alert channel interface with local console/file implementations only."""
from pathlib import Path
from typing import Any, Protocol
import json

from src.core.privacy import sanitize_for_log


class AlertChannel(Protocol):
    def send(self, alert: dict[str, Any]) -> None: ...


class ConsoleChannel:
    def send(self, alert: dict[str, Any]) -> None:
        # JSON serialization treats alert text as data; it is never parsed or executed.
        print(json.dumps(sanitize_for_log(alert), ensure_ascii=False, default=str))


class FileChannel:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, alert: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sanitize_for_log(alert), ensure_ascii=False, default=str) + "\n")
