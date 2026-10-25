"""Local heuristic secrets scan; reports paths/rule names, never matched values."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".ps1", ".yml", ".yaml", ".toml", ".ini", ".md", ".txt", ".lock", ".json", ".sh"}
SKIP_DIRS = {".git", ".venv", "data", "models", "__pycache__", ".pytest_cache", ".pytest_tmp", "node_modules"}
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|passwd|secret|access[_-]?token)\b\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
)
PLACEHOLDERS = ("example", "replace", "change-me", "changeme", "your-", "your_", "dummy", "placeholder", "os.getenv", "environ")


def findings(root: Path = ROOT) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        env_file = path.name == ".env" or path.name.startswith(".env.")
        if not path.is_file() or (path.suffix.lower() not in TEXT_SUFFIXES and not env_file):
            continue
        relative = path.relative_to(root)
        if any(part.lower() in SKIP_DIRS or part.lower().startswith(".pytest_tmp") for part in relative.parts):
            continue
        if relative.as_posix() == ".env.example":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            if PRIVATE_KEY.search(line):
                found.append((f"{relative}:{number}", "private-key-block"))
            for match in ASSIGNMENT.finditer(line):
                value = match.group(1).lower()
                if not any(marker in value for marker in PLACEHOLDERS):
                    found.append((f"{relative}:{number}", "credential-assignment"))
    return found


def main() -> int:
    results = findings()
    if results:
        for path, rule in results:
            print(f"{path}: {rule}", file=sys.stderr)
        return 1
    print("Heuristic secrets scan found no matches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
