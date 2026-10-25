"""Extract synthetic Kaveri Foods test fixture to tests/fixtures/synthetic/kaveri_foods/."""
import zipfile
from pathlib import Path

def main():
    zip_path = Path("kaveri_foods_sample.zip")
    if not zip_path.exists():
        print("kaveri_foods_sample.zip not found.")
        return 1
    dest = Path("tests/fixtures/synthetic/kaveri_foods")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            # Strip top-level kaveri_foods_sample/ prefix
            rel_path = member.filename
            if rel_path.startswith("kaveri_foods_sample/"):
                rel_path = rel_path[len("kaveri_foods_sample/"):]
            target = dest / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as sink:
                sink.write(source.read())
    print(f"Extracted {len(list(dest.rglob('*')))} items to {dest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
