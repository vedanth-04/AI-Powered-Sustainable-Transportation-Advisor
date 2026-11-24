"""Download the pinned public Delhi transit datasets for the advisor and verify their sha256.

    python -m scripts.advisor_fetch_data           # skips files that are already present and valid
    python -m scripts.advisor_fetch_data --force   # re-download everything

Files go to data/raw/transit/<dataset>/ (git-ignored). About 460 MB in total.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "advisor" / "config" / "sources.json"
RAW = ROOT / "data" / "raw" / "transit"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "delhi-transport-advisor/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            if total:
                print(f"\r  {target.name}: {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    tmp.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    datasets = json.loads(SOURCES.read_text(encoding="utf-8"))["datasets"]
    failures = 0
    for key, ds in datasets.items():
        folder = RAW / key
        folder.mkdir(parents=True, exist_ok=True)
        print(f"{ds['title']}\n  source: {ds['official_page']}\n  pinned copy: {ds['mirror']}")
        for name, expected in ds["files"].items():
            target = folder / name
            if target.exists() and not args.force and sha256_file(target) == expected:
                print(f"  {name}: ok (already present)")
                continue
            try:
                fetch(ds["base_url"] + name, target)
            except Exception as exc:
                print(f"  {name}: download failed ({exc})")
                failures += 1
                continue
            actual = sha256_file(target)
            if actual != expected:
                print(f"  {name}: sha256 mismatch ({actual}); file kept for inspection but will be rejected by the build")
                failures += 1
            else:
                print(f"  {name}: verified")
    if failures:
        print(f"\n{failures} file(s) failed. Re-run, or download them manually into {RAW}.")
        return 1
    print(f"\nAll files verified in {RAW}. Next: python -m scripts.advisor_build_network")
    return 0


if __name__ == "__main__":
    sys.exit(main())
