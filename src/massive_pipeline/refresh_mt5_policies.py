from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "data" / "live" / "policy"
RUNTIME_DIR = ROOT / "runtime_handoff" / "mt5_common" / "Files" / "ForexSlave"
MT5_COMMON_DIR = Path("/home/asurani/.wine-mt5/drive_c/users/asurani/AppData/Roaming/MetaQuotes/Terminal/Common/Files/ForexSlave")
RUN_LOG = ROOT / "data" / "live" / "policy" / "refresh_mt5_policies_run.json"

FILES = [
    "core_portfolio_policy.json",
    "entry_intent.json",
    "pair_risk_policy.json",
]


def run_export() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "src" / "massive_pipeline" / "export_all_mt5_policies.py")],
        cwd=ROOT,
        check=True,
    )


def copy_one(name: str) -> dict:
    src = POLICY_DIR / name
    if not src.exists():
        raise FileNotFoundError(f"missing policy file: {src}")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    MT5_COMMON_DIR.mkdir(parents=True, exist_ok=True)

    runtime_dest = RUNTIME_DIR / name
    mt5_dest = MT5_COMMON_DIR / name

    shutil.copy2(src, runtime_dest)
    shutil.copy2(src, mt5_dest)

    return {
        "file": name,
        "source": str(src.relative_to(ROOT)),
        "runtime_dest": str(runtime_dest.relative_to(ROOT)),
        "mt5_common_dest": str(mt5_dest),
    }


def main() -> int:
    started = datetime.now(timezone.utc)
    payload: dict = {
        "status": "started",
        "started_at_utc": started.isoformat(),
        "files": [],
    }

    try:
        run_export()
        payload["files"] = [copy_one(name) for name in FILES]
        payload["status"] = "ok"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)

    payload["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
