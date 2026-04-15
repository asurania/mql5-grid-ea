from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE_POLICY = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
DEFAULT_HANDOFF_DIR = ROOT / "runtime_handoff" / "mt5_common" / "Files" / "ForexSlave"
OUT_RUN_LOG = ROOT / "data" / "live" / "policy" / "publish_pair_risk_policy_run.json"


def main() -> int:
    started = datetime.now(timezone.utc)
    DEFAULT_HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_POLICY.exists():
        payload = {
            "status": "failed",
            "started_at_utc": started.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "error": f"missing source policy: {SOURCE_POLICY}",
        }
        OUT_RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        OUT_RUN_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    dest = DEFAULT_HANDOFF_DIR / "pair_risk_policy.json"
    shutil.copy2(SOURCE_POLICY, dest)

    payload = {
        "status": "ok",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_policy": str(SOURCE_POLICY.relative_to(ROOT)),
        "published_policy": str(dest.relative_to(ROOT)),
    }
    OUT_RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    OUT_RUN_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
