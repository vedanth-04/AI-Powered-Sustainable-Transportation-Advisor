"""Register the Delhi advisor as BusTravelTimePredictor v4 (a system release) in the ledger and in MLflow.

    .\\.venv-dev\\Scripts\\python.exe -m scripts.register_advisor_release --dry-run   # release gate only
    .\\.venv-dev\\Scripts\\python.exe -m scripts.register_advisor_release             # gate, ledger v4, MLflow v4

v4 keeps the champion's bus model weights byte-for-byte and adds the planner, the pinned Delhi data
snapshot, fares and cab settings. The champion alias stays where it is, so the bus model API is not
affected; v4 gets the `advisor` alias. Nothing is written unless every release-gate check passes.
Running it again with unchanged files reports the existing release and only retries the MLflow sync.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.versioning.ledger import Ledger, verify_audit_chain  # noqa: E402
from src.versioning.release import (  # noqa: E402
    RELEASE_ALIAS, advisor_checks, build_manifest, data_checks, find_release, ledger_checks, register_release,
    release_gate, test_check,
)


def show(checks: list[dict]) -> None:
    for item in checks:
        print(f"[{'PASS' if item['passed'] else 'FAIL'}] {item['name']}: {item['detail']}")


def mlflow_features():
    """Two real requests on the approved corridor, used as the MLflow input example and signature."""
    import pandas as pd

    from src.features.label_generation import IST_OFFSET
    from src.features.segment_config import get_segment
    from src.monitoring.replay import FEATURES, serving_features

    segment = get_segment("ORR_CHIRAG_TO_NEHRU_PLACE_EB")
    rows = [{"segment_id": segment.segment_id, "direction": segment.direction, "segment_length_km": segment.length_km,
             "route_id": segment.primary_routes[0],
             "entry_ts_sent": datetime(2019, 7, 8, hour, minute, tzinfo=IST_OFFSET).timestamp()}
            for hour, minute in ((8, 30), (17, 10))]
    return serving_features(pd.DataFrame(rows))[FEATURES]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="run the release gate and write nothing")
    parser.add_argument("--expect-version", type=int, default=4, help="the version number the release must get (default 4)")
    parser.add_argument("--registry-dir", type=Path, default=ROOT / "outputs" / "phase3" / "registry")
    parser.add_argument("--skip-mlflow", action="store_true", help="register in the ledger only")
    args = parser.parse_args()

    ledger_path = args.registry_dir / "model_versions.json"
    if not ledger_path.is_file():
        print(f"No Phase 3 ledger at {ledger_path}. Run python -m scripts.run_phase3 first.")
        return 1
    ledger = Ledger.load(ledger_path)
    champion = ledger.champion()
    print(f"Ledger {ledger.model_name}: versions {[r['version'] for r in ledger.versions]}, aliases {ledger.aliases}")

    checks = ledger_checks(ledger, args.registry_dir)
    if champion is None or not all(c["passed"] for c in checks):
        show(checks)
        print("Stopped: the ledger or the champion artifact failed its checks.")
        return 1
    manifest = build_manifest(ROOT, champion)
    print(f"Release fingerprint {manifest['fingerprint'][:16]}… (bus model v{champion['version']}, "
          f"planner {manifest['components']['planner']['sha256'][:10]}, data "
          f"{manifest['data']['snapshot']['network.npz']['sha256'][:10]})")

    existing = find_release(ledger, manifest["fingerprint"])
    if existing:
        print(f"These exact files are already registered as v{existing['version']}; no new version is needed.")
        record = existing
    else:
        checks += data_checks(ROOT)
        print("Running the advisor checks (real network, offline) and the advisor tests…")
        try:
            checks += advisor_checks(champion["version"])
        except Exception as exc:
            checks.append({"name": "advisor_loads", "passed": False, "detail": f"{type(exc).__name__}: {exc}"})
        checks.append(test_check(ROOT))
        gate = release_gate(checks)
        show(checks)
        if not gate["passed"]:
            print("Release gate FAILED: nothing was written. Fix the failing checks and run again.")
            return 1
        if args.dry_run:
            print(f"Release gate passed. Dry run: v{ledger.next_version()} was not registered.")
            return 0
        from src.versioning.lifecycle import code_identity

        try:
            record = register_release(ledger, args.registry_dir, manifest, gate, expected_version=args.expect_version,
                                      code=code_identity())
        except ValueError as exc:
            print(f"Stopped: {exc}")
            return 1
        print(f"Registered v{record['version']} ({record['status']}), alias '{RELEASE_ALIAS}' -> v{record['version']}; "
              f"champion stays v{ledger.aliases['champion']}.")

    result = {"status": "skipped", "reason": "--skip-mlflow was given."}
    if not args.skip_mlflow and not args.dry_run:
        if (record.get("mlflow") or {}).get("status") in ("registered", "already_registered"):
            print(f"MLflow already holds v{record['version']}; aliases are re-applied.")
        from src.versioning.mlflow_sync import sync_to_mlflow

        result = sync_to_mlflow(ledger, args.registry_dir, mlflow_features())
        mine = next((item for item in result.get("versions", []) if item["version"] == record["version"]), None)
        if mine:
            ledger.get(record["version"])["mlflow"] = mine
            ledger.save()
        print(f"MLflow: {result['status']}" + (f" - {result.get('error') or result.get('reason')}"
                                               if result["status"] != "ok" else f", aliases {result['aliases']}"))
        if result.get("ui_command"):
            print(f"Open it with:  {result['ui_command']}")
    chain = verify_audit_chain(ledger.audit_path)
    report = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "version": record["version"],
              "status": record["status"], "fingerprint": record["release"]["fingerprint"], "gate": record["gate"],
              "aliases": dict(ledger.aliases), "mlflow": result, "audit_chain": chain}
    if not args.dry_run:
        (args.registry_dir / "advisor_release.json").write_text(json.dumps(report, indent=2, default=str) + "\n",
                                                                encoding="utf-8")
    print(f"Audit chain: {'valid' if chain['valid'] else 'BROKEN'} ({chain['entries']} entries).")
    return 0 if chain["valid"] and result["status"] in ("ok", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
