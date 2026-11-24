"""Build the advisor's multimodal network from the verified raw datasets.

    python -m scripts.advisor_build_network

Writes data/processed/advisor/network.npz and network_meta.json (git-ignored), about 1 minute.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advisor.ingest import OUT_DIR, build_network  # noqa: E402


def main() -> int:
    counts = build_network()
    print(f"Done: {OUT_DIR}\n{counts}\nStart the advisor: python -m advisor.server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
