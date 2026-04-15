from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv-forex" / "bin" / "python"
LIVE_EVENT_RISK_JSON = ROOT / "data" / "live" / "event_risk" / "event_risk_actions.json"
PAIR_POLICY_JSON = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
RUN_LOG_JSON = ROOT / "data" / "live" / "policy" / "event_risk_master_run.json"

STEPS = [
    ROOT / "src" / "massive_pipeline" / "run_live_event_risk_inference.py",
    ROOT / "src" / "massive_pipeline" / "build_pair_risk_policy.py",
]


def run_step(script: Path) -> dict:
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        [str(PYTHON), str(script)],
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
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    results = []
    started = datetime.now(timezone.utc)

    for step in STEPS:
        result = run_step(step)
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
        },
        "artifacts": {
            "event_risk_actions_json": str(LIVE_EVENT_RISK_JSON.relative_to(ROOT)),
            "pair_risk_policy_json": str(PAIR_POLICY_JSON.relative_to(ROOT)),
        },
    }
    RUN_LOG_JSON.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
