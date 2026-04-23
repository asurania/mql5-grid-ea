from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv-forex" / "bin" / "python"
LIVE_EVENT_RISK_JSON = ROOT / "data" / "live" / "event_risk" / "event_risk_actions.json"
PAIR_POLICY_JSON = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
RUN_LOG_JSON = ROOT / "data" / "live" / "policy" / "event_risk_master_run.json"

BASE_STEPS = [
    ROOT / "src" / "massive_pipeline" / "run_live_event_risk_inference.py",
    ROOT / "src" / "massive_pipeline" / "run_live_event_impact_inference.py",
    ROOT / "src" / "massive_pipeline" / "build_pair_risk_policy.py",
    ROOT / "src" / "massive_pipeline" / "publish_pair_risk_policy.py",
    ROOT / "src" / "massive_pipeline" / "build_entry_intent_v2.py",
    ROOT / "src" / "massive_pipeline" / "publish_entry_intent.py",
    ROOT / "src" / "massive_pipeline" / "build_live_session_range_features.py",
    ROOT / "src" / "massive_pipeline" / "run_live_session_range_inference.py",
    ROOT / "src" / "massive_pipeline" / "publish_grid_policy.py",
]
GRID_POLICY_SCRIPT = ROOT / "src" / "massive_pipeline" / "build_grid_policy.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Forex event-risk master pipeline")
    parser.add_argument("--account-equity", type=float, default=10000.0, help="Account equity for grid optimizer sizing")
    parser.add_argument("--risk-mode", choices=["low", "medium", "high"], default="medium", help="Risk mode passed into grid optimizer")
    parser.add_argument("--allow-gbpjpy-demo-override", action="store_true", help="Keep GBPJPY demo override active in grid optimizer")
    return parser.parse_args()


def run_step(script: Path, extra_args: list[str] | None = None) -> dict:
    started = datetime.now(timezone.utc)
    command = [str(PYTHON), str(script)]
    if extra_args:
        command.extend(extra_args)
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    finished = datetime.now(timezone.utc)
    return {
        "script": str(script.relative_to(ROOT)),
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    args = parse_args()
    results = []
    started = datetime.now(timezone.utc)

    steps: list[tuple[Path, list[str]]] = [(step, []) for step in BASE_STEPS]
    grid_args = ["--account-equity", str(args.account_equity), "--risk-mode", args.risk_mode]
    if args.allow_gbpjpy_demo_override:
        grid_args.append("--allow-gbpjpy-demo-override")
    steps.insert(8, (GRID_POLICY_SCRIPT, grid_args))

    for step, extra_args in steps:
        result = run_step(step, extra_args)
        results.append(result)
        if result["returncode"] != 0:
            RUN_LOG_JSON.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "failed",
                "started_at_utc": started.isoformat(),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "steps": results,
            }
            RUN_LOG_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps(payload, indent=2))
            return result["returncode"]

    live_actions = json.loads(LIVE_EVENT_RISK_JSON.read_text(encoding="utf-8")) if LIVE_EVENT_RISK_JSON.exists() else {}
    pair_policy = json.loads(PAIR_POLICY_JSON.read_text(encoding="utf-8")) if PAIR_POLICY_JSON.exists() else {}

    payload = {
        "status": "ok",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "steps": results,
        "summary": {
            "event_rows": len(live_actions.get("rows", [])),
            "pair_policy_rows": len(pair_policy.get("pair_policies", [])),
            "grid_optimizer_account_equity": args.account_equity,
            "grid_optimizer_risk_mode": args.risk_mode,
            "grid_optimizer_demo_override": args.allow_gbpjpy_demo_override,
        },
        "artifacts": {
            "event_risk_actions_json": str(LIVE_EVENT_RISK_JSON.relative_to(ROOT)),
            "pair_risk_policy_json": str(PAIR_POLICY_JSON.relative_to(ROOT)),
            "published_pair_risk_policy_json": "runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json",
            "entry_intent_json": "data/live/policy/entry_intent.json",
            "published_entry_intent_json": "runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json",
            "grid_policy_json": "data/live/policy/grid_policy.json",
            "published_grid_policy_json": "runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json",
        },
    }
    RUN_LOG_JSON.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
