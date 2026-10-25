"""Pre-commit guard for raw archives, datasets, databases and model artifacts."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

FORBIDDEN_SUFFIXES = {".zip", ".7z", ".rar", ".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".db", ".sqlite", ".sqlite3"}
FORBIDDEN_DIRS = {"data", "models"}


def is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized.startswith("tests/fixtures/synthetic/kaveri_foods/"):
        return False
    parts = [part.lower() for part in PurePosixPath(normalized).parts]
    if any(part in FORBIDDEN_DIRS for part in parts[:-1]):
        return True
    name = parts[-1] if parts else ""
    return PurePosixPath(name).suffix.lower() in FORBIDDEN_SUFFIXES or name.endswith((
        ".db-wal", ".db-shm", ".db-journal", ".sqlite-wal", ".sqlite-shm", ".sqlite-journal",
        ".sqlite3-wal", ".sqlite3-shm", ".sqlite3-journal",
    ))


def staged_paths() -> list[str]:
    completed = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=True, capture_output=True, text=True)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", help="Check explicit paths (also used by tests)")
    args = parser.parse_args()
    try:
        paths = args.paths if args.paths is not None else staged_paths()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Cannot inspect staged paths: {exc}", file=sys.stderr)
        return 2
    blocked = [path for path in paths if is_protected_path(path)]
    if blocked:
        print("Protected files cannot be committed:", file=sys.stderr)
        for path in blocked:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("Protected-file check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
