from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv-forex" / "bin" / "python"
MASTER_SCRIPT = ROOT / "src" / "massive_pipeline" / "run_event_risk_master.py"
EXPORT_SCRIPT = ROOT / "src" / "massive_pipeline" / "export_all_mt5_policies.py"
POLICY_DIR = ROOT / "data" / "live" / "policy"
EVENT_RISK_DIR = ROOT / "data" / "live" / "event_risk"
SOURCE_DIR = ROOT / "runtime_handoff" / "mt5_common" / "Files" / "ForexSlave"
DEFAULT_DESTINATIONS = [
    Path("/home/asurani/.wine-mt5/drive_c/Program Files/MetaTrader 5/MQL5/Files/ForexSlave"),
    Path("/home/asurani/.wine-mt5/drive_c/users/asurani/AppData/Roaming/MetaQuotes/Terminal/Common/Files/ForexSlave"),
]
FILES_TO_COPY = [
    "core_portfolio_policy.json",
    "pair_risk_policy.json",
    "entry_intent.json",
    "grid_policy.json",
    "event_impact_actions.json",
]
RUN_LOG = ROOT / "data" / "live" / "policy" / "mt5_live_bridge_run.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MT5 live bridge loop for ForexSlave handoff files.")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between refresh cycles (default: 30)")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--account-equity", type=float, default=10000.0, help="Account equity passed into grid optimizer")
    parser.add_argument("--risk-mode", choices=["low", "medium", "high"], default="medium", help="Risk mode passed into grid optimizer")
    parser.add_argument("--allow-gbpjpy-demo-override", action="store_true", help="Keep GBPJPY demo override active in grid optimizer")
    parser.add_argument(
        "--dest",
        action="append",
        default=[],
        help="Additional destination directory for MT5 ForexSlave files. Can be passed multiple times.",
    )
    return parser.parse_args()


def build_destinations(extra_dests: list[str]) -> list[Path]:
    dests = list(DEFAULT_DESTINATIONS)
    for raw in extra_dests:
        p = Path(raw).expanduser()
        if p not in dests:
            dests.append(p)
    return dests


def run_master(account_equity: float, risk_mode: str, allow_gbpjpy_demo_override: bool) -> dict:
    started = utc_now_iso()
    command = [
        str(PYTHON),
        str(MASTER_SCRIPT),
        "--account-equity",
        str(account_equity),
        "--risk-mode",
        risk_mode,
    ]
    if allow_gbpjpy_demo_override:
        command.append("--allow-gbpjpy-demo-override")
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    finished = utc_now_iso()
    return {
        "started_at_utc": started,
        "finished_at_utc": finished,
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_export() -> dict:
    started = utc_now_iso()
    command = [str(PYTHON), str(EXPORT_SCRIPT)]
    proc = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, check=False)
    finished = utc_now_iso()
    return {
        "started_at_utc": started,
        "finished_at_utc": finished,
        "command": [str(x) for x in command],
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def copy_policy_to_source() -> list[str]:
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_RISK_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in FILES_TO_COPY:
        # Try policy dir first, then event risk dir
        src = POLICY_DIR / name
        if not src.exists():
            src = EVENT_RISK_DIR / name
        if not src.exists():
            print(f"[WARN] missing policy file: {name}")
            continue
        shutil.copy2(src, SOURCE_DIR / name)
        copied.append(name)
    return copied


def copy_handoff_files(destinations: list[Path]) -> list[dict]:
    copy_results: list[dict] = []
    for dest in destinations:
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for name in FILES_TO_COPY:
            src = SOURCE_DIR / name
            if not src.exists():
                raise FileNotFoundError(f"missing source handoff file: {src}")
            shutil.copy2(src, dest / name)
            copied.append(name)
        copy_results.append({
            "destination": str(dest),
            "copied_files": copied,
        })
    return copy_results


def write_run_log(payload: dict) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    RUN_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_cycle(
    destinations: list[Path],
    cycle_number: int,
    *,
    account_equity: float,
    risk_mode: str,
    allow_gbpjpy_demo_override: bool,
) -> dict:
    cycle_started = utc_now_iso()
    master = run_master(account_equity, risk_mode, allow_gbpjpy_demo_override)
    if master["returncode"] != 0:
        payload = {
            "status": "failed",
            "cycle": cycle_number,
            "started_at_utc": cycle_started,
            "finished_at_utc": utc_now_iso(),
            "master": master,
            "copy": [],
        }
        write_run_log(payload)
        return payload

    export_result = run_export()
    copy_policy_to_source()

    copy_results = copy_handoff_files(destinations)
    payload = {
        "status": "ok",
        "cycle": cycle_number,
        "started_at_utc": cycle_started,
        "finished_at_utc": utc_now_iso(),
        "master": master,
        "export": export_result,
        "copy": copy_results,
        "source_dir": str(SOURCE_DIR),
        "grid_optimizer": {
            "account_equity": account_equity,
            "risk_mode": risk_mode,
            "allow_gbpjpy_demo_override": allow_gbpjpy_demo_override,
        },
    }
    write_run_log(payload)
    return payload


def print_cycle_summary(payload: dict) -> None:
    status = payload.get("status", "unknown")
    cycle = payload.get("cycle")
    finished = payload.get("finished_at_utc")
    print(f"[{finished}] cycle={cycle} status={status}")
    if status == "ok":
        for row in payload.get("copy", []):
            print(f"  copied -> {row['destination']}")
    else:
        master = payload.get("master", {})
        print(f"  master returncode={master.get('returncode')}")
        stderr = (master.get("stderr") or "").strip()
        if stderr:
            print(stderr)


def main() -> int:
    args = parse_args()
    destinations = build_destinations(args.dest)
    cycle = 0

    print("Starting MT5 live bridge")
    print(f"Master script: {MASTER_SCRIPT}")
    print(f"Refresh interval: {args.interval}s")
    print(f"Grid optimizer account equity: {args.account_equity}")
    print(f"Grid optimizer risk mode: {args.risk_mode}")
    print(f"GBPJPY demo override: {args.allow_gbpjpy_demo_override}")
    for dest in destinations:
        print(f"Destination: {dest}")

    while True:
        cycle += 1
        try:
            payload = run_cycle(
                destinations,
                cycle,
                account_equity=args.account_equity,
                risk_mode=args.risk_mode,
                allow_gbpjpy_demo_override=args.allow_gbpjpy_demo_override,
            )
        except KeyboardInterrupt:
            print("Stopped by user")
            return 130
        except Exception as exc:
            payload = {
                "status": "exception",
                "cycle": cycle,
                "started_at_utc": utc_now_iso(),
                "finished_at_utc": utc_now_iso(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            write_run_log(payload)
        print_cycle_summary(payload)

        if args.once:
            return 0 if payload.get("status") == "ok" else 1

        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    sys.exit(main())
