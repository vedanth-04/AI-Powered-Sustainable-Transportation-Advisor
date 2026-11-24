"""Run the complete Phase 3 workflow: drift replay -> retraining -> gated promotion -> export.

    python -m scripts.run_phase3                  # uses the approved v1 bundle
    python -m scripts.run_phase3 --write-evidence # also records a small summary under docs/results/phase3

It never modifies the live Phase 2 deployment, its MLflow registry or its GHCR image.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if sys.version_info < (3, 12):
    sys.exit(f"Phase 3 needs the project's Python 3.12 environment; this is Python {sys.version.split()[0]} "
             f"({sys.executable}).\nRun it with:  .\\.venv-dev\\Scripts\\python.exe -m scripts.run_phase3 --write-evidence")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.config import OUTPUTS_DIR  # noqa: E402
from src.monitoring.replay import (DEFAULT_BUNDLE, DEFAULT_POLICY, DEFAULT_TRAVERSALS, load_approved_v1,  # noqa: E402
                                   load_policy, load_splits, reproduce_v1, run_replay)
from src.versioning.lifecycle import DEFAULT_PROMOTION_POLICY, run_lifecycle  # noqa: E402


def evidence_summary(monitoring: dict, lifecycle: dict) -> dict:
    """Small, path-free record suitable for committing next to the Phase 2 evidence."""
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "kind": "historical_replay_and_lifecycle",
        "model_v1_source": monitoring["model"]["source"],
        "model_v1_sha256": monitoring["model"]["sha256"],
        "inputs": monitoring["inputs"],
        "approved_validation_mae": monitoring["reference"]["approved_validation_mae"],
        "scenarios": {
            name: {"alerts_by_type": item["alerts_by_type"], "detection_delay_minutes": item["detection_delay_minutes"],
                   "first_alert_after_onset": {k: v["detected_at_ist"] for k, v in item["first_alert_after_onset"].items()},
                   "cusum_alarms": [(a["detector"], a["detected_at_ist"]) for a in item["cusum_alarms"]],
                   "daily": item["daily"]}
            for name, item in monitoring["scenarios"].items()
        },
        "retraining_trigger": lifecycle["retraining_trigger"],
        "versions": [{k: v for k, v in record.items() if k != "artifact"} | {"artifact_sha256": (record.get("artifact") or {}).get("sha256")}
                     for record in lifecycle["versions"]],
        "aliases": lifecycle["aliases"],
        "gates": lifecycle["gates"],
        "rollback_drill": lifecycle["rollback_drill"],
        "export": {k: v for k, v in lifecycle["export"].items() if k != "serve_command"},
        "mlflow_status": lifecycle["mlflow"].get("status"),
        "audit_chain": lifecycle["audit_chain"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--traversals", type=Path, default=DEFAULT_TRAVERSALS)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR / "phase3")
    parser.add_argument("--monitoring-policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--promotion-policy", type=Path, default=DEFAULT_PROMOTION_POLICY)
    parser.add_argument("--reproduce-v1", action="store_true",
                        help="Refit v1 instead of loading the approved bundle (recorded as a substitution).")
    parser.add_argument("--no-mlflow", action="store_true", help="Skip mirroring versions into the Phase 3 MLflow registry.")
    parser.add_argument("--actor", help="Team member recorded in the audit log (default: MLOPS_ACTOR or OS user).")
    parser.add_argument("--write-evidence", action="store_true", help="Write docs/results/phase3/phase3_summary.json.")
    args = parser.parse_args()

    if (args.output_dir / "registry" / "model_versions.json").exists():
        parser.exit(2, f"{args.output_dir} already holds a Phase 3 run. Choose a new --output-dir or move the old run; "
                       "the version ledger is append-only and is never overwritten.\n")
    if not args.traversals.exists():
        parser.exit(2, f"Missing {args.traversals}. Phase 3 replays the 637-row Phase 2 input; see docs/PHASE3_GUIDE.md.\n")
    policy = load_policy(args.monitoring_policy)
    splits = load_splits(args.traversals, policy)
    if args.reproduce_v1:
        handle, v1_bytes = reproduce_v1(splits[0]), None
    else:
        handle = load_approved_v1(args.bundle_dir)
        v1_bytes = (args.bundle_dir / "model.joblib").read_bytes()

    print(f"[1/3] Historical replay with v{handle.version} ({handle.source}) ...")
    monitoring = run_replay(args.traversals, handle, args.output_dir / "monitoring", policy_path=args.monitoring_policy,
                            splits=splits)
    for name, summary in monitoring["scenarios"].items():
        first = {kind: value["detected_at_ist"] for kind, value in summary["first_alert_after_onset"].items()}
        print(f"      {name:16s} first alerts: {first or 'none'}")

    print("[2/3] Lifecycle: register v1, retrain on drift, gate, promote, export, rollback drill ...")
    traversals = pd.concat(splits)  # exactly the rows the replay used
    lifecycle = run_lifecycle(
        traversals=traversals, traversals_sha256=sha256(args.traversals.read_bytes()).hexdigest(),
        output_dir=args.output_dir, v1=handle, v1_bytes=v1_bytes, v1_training=splits[0], monitoring_report=monitoring,
        monitoring_policy=policy, promotion_policy_path=args.promotion_policy, actor=args.actor,
        mlflow_sync=not args.no_mlflow)
    for record in lifecycle["versions"]:
        mae = record["holdout_metrics"]["mae_minutes"]
        print(f"      v{record['version']} {record['status']:9s} {record['change_type']:18s} holdout MAE {mae:.3f} min")
    print(f"      aliases {lifecycle['aliases']}; rollback drill passed: {(lifecycle['rollback_drill'] or {}).get('passed')}")
    print(f"      MLflow mirror: {lifecycle['mlflow'].get('status')} {lifecycle['mlflow'].get('error', '')}")

    summary = evidence_summary(monitoring, lifecycle)
    (args.output_dir / "phase3_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.write_evidence:
        target = ROOT / "docs" / "results" / "phase3" / "phase3_summary.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"      evidence written to {target.relative_to(ROOT)}")
    print("[3/3] Done. Open the dashboard: python -m dashboard.server  ->  http://127.0.0.1:8050")


if __name__ == "__main__":
    main()
