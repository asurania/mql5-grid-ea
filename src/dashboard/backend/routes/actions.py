"""Action routes — trigger trading system actions."""

from fastapi import APIRouter, HTTPException
import subprocess
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]  # workspace root
PYTHON = ROOT / ".venv-forex" / "bin" / "python"
SRC = ROOT / "src" / "massive_pipeline"
BRIDGE_SCRIPT = SRC / "run_mt5_live_bridge.py"
SOURCE_POLICY_DIR = ROOT / "data" / "live" / "policy"
HANDOFF_DIR = ROOT / "runtime_handoff" / "mt5_common" / "Files" / "ForexSlave"
MT5_DESTINATIONS = [
    Path("/home/asurani/.wine-mt5/drive_c/Program Files/MetaTrader 5/MQL5/Files/ForexSlave"),
    Path("/home/asurani/.wine-mt5/drive_c/users/asurani/AppData/Roaming/MetaQuotes/Terminal/Common/Files/ForexSlave"),
]
FILES_TO_COPY = [
    "pair_risk_policy.json",
    "entry_intent.json",
    "grid_policy.json",
]
BRIDGE_LOG = ROOT / "data" / "live" / "policy" / "mt5_live_bridge_run.json"

router = APIRouter()


def _load_config():
    """Load trading config via the shared module."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from massive_pipeline.trading_config import load_config
    return load_config()


def _run_script(script_name: str, args: list[str] = None, timeout: int = 120) -> dict:
    """Run a pipeline script and return result."""
    script_path = SRC / script_name
    if not script_path.exists():
        raise HTTPException(404, f"Script not found: {script_name}")

    cmd = [str(PYTHON), str(script_path)] + (args or [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return {
            "script": script_name,
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000] if result.stdout else "",
            "stderr": result.stderr[:1000] if result.stderr else "",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(408, f"Script timed out: {script_name}")
    except Exception as e:
        raise HTTPException(500, f"Script error: {e}")


def _copy_handoff_to_mt5() -> dict:
    """Copy all handoff files from runtime_handoff to MT5 directories."""
    results = []
    for dest_dir in MT5_DESTINATIONS:
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        for name in FILES_TO_COPY:
            src = HANDOFF_DIR / name
            if src.exists():
                shutil.copy2(src, dest_dir / name)
                copied.append(name)
        results.append({
            "destination": str(dest_dir),
            "copied": copied,
        })
    return {"status": "ok", "destinations": results}


def _read_bridge_log() -> dict | None:
    """Read the last bridge run log."""
    if BRIDGE_LOG.exists():
        try:
            return json.loads(BRIDGE_LOG.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# --- Bridge: full refresh + copy ---

@router.post("/bridge/refresh")
async def bridge_refresh():
    """Run the full bridge cycle: master pipeline → publish → copy to MT5.
    
    This is the one-command bridge that does everything.
    """
    cfg = _load_config()
    equity = cfg["account"]["equity"]
    risk_mode = cfg["account"]["risk_mode"]

    args = ["--once", "--account-equity", str(equity), "--risk-mode", risk_mode]
    if cfg.get("bridge", {}).get("allow_gbpjpy_demo_override"):
        args.append("--allow-gbpjpy-demo-override")

    result = _run_script("run_mt5_live_bridge.py", args, timeout=180)
    
    # Read the bridge log for the structured result
    bridge_log = _read_bridge_log()
    
    return {
        "status": "completed" if result["exit_code"] == 0 else "failed",
        "bridge_log": bridge_log,
        "script_result": result,
    }


@router.post("/bridge/copy")
async def bridge_copy():
    """Copy current handoff files to MT5 directories without re-running pipeline."""
    result = _copy_handoff_to_mt5()
    return result


# --- Individual refresh steps ---

@router.post("/refresh-policy")
async def refresh_policy():
    """Run the full master pipeline (event risk → entry intent → grid policy)."""
    cfg = _load_config()
    equity = cfg["account"]["equity"]
    risk_mode = cfg["account"]["risk_mode"]

    args = ["--account-equity", str(equity), "--risk-mode", risk_mode]
    if cfg.get("bridge", {}).get("allow_gbpjpy_demo_override"):
        args.append("--allow-gbpjpy-demo-override")

    result = _run_script("run_event_risk_master.py", args)
    return {"status": "refreshed" if result["exit_code"] == 0 else "failed", "result": result}


@router.post("/refresh-grid-policy")
async def refresh_grid_policy():
    """Rebuild just the grid policy."""
    cfg = _load_config()
    equity = cfg["account"]["equity"]
    risk_mode = cfg["account"]["risk_mode"]

    args = ["--account-equity", str(equity), "--risk-mode", risk_mode]
    if cfg.get("bridge", {}).get("allow_gbpjpy_demo_override"):
        args.append("--allow-gbpjpy-demo-override")

    result = _run_script("build_grid_policy.py", args)
    return {"status": "refreshed" if result["exit_code"] == 0 else "failed", "result": result}


@router.post("/refresh-entry-intent")
async def refresh_entry_intent():
    """Rebuild just the entry intent."""
    result = _run_script("build_entry_intent_v2.py")
    return {"status": "refreshed" if result["exit_code"] == 0 else "failed", "result": result}


@router.post("/copy-to-mt5")
async def copy_to_mt5():
    """Publish all policy files and copy to MT5 directories."""
    r1 = _run_script("publish_pair_risk_policy.py")
    r2 = _run_script("publish_entry_intent.py")
    r3 = _run_script("publish_grid_policy.py")
    copy_result = _copy_handoff_to_mt5()
    return {
        "status": "ok",
        "publish": [r1, r2, r3],
        "copy": copy_result,
    }


# --- Trading control ---

@router.post("/toggle-trading")
async def toggle_trading(data: dict):
    """Toggle live trading on/off via config."""
    enabled = data.get("enabled")
    if enabled is None:
        raise HTTPException(400, "Must provide 'enabled' (true/false)")

    from massive_pipeline.trading_config import patch_config
    updated = patch_config({"bridge": {"live_trading_enabled": enabled}})
    return {"status": "toggled", "live_trading_enabled": enabled}


@router.post("/force-close-pair")
async def force_close_pair(data: dict):
    """Mark a pair for force close in the next policy cycle."""
    pair = data.get("pair")
    if not pair:
        raise HTTPException(400, "Must provide 'pair'")

    from massive_pipeline.trading_config import patch_config
    updated = patch_config({
        "grid_templates": {
            f"force_close_{pair.lower()}": {
                "allow_new_basket": False,
                "grid_mode": "both_sides",
                "seed_mode": "single_side",
                "step_pips": 0,
                "initial_lot": 0.0,
                "multiplier": 1.0,
                "max_trades_per_side": 0,
                "basket_tp_currency": 0.0,
                "max_gross_lots": 0.0,
                "max_basket_drawdown_currency": 0.0,
                "min_step_to_spread_ratio": 0.0,
                "min_free_margin_percent": 0.0,
                "flatten_on_strong_avoid": True,
                "confidence": 1.0,
                "reason": f"force_close_{pair}",
            }
        }
    })
    return {"status": "marked_for_close", "pair": pair}


@router.post("/validate-config")
async def validate_config():
    """Validate the current config file."""
    try:
        cfg = _load_config()
        issues = []

        if not cfg.get("pairs"):
            issues.append("No pairs configured")
        if not cfg.get("sessions"):
            issues.append("No sessions configured")
        for sname, sconf in cfg.get("sessions", {}).items():
            if "close_utc" not in sconf:
                issues.append(f"Session {sname} missing close_utc")
        risk = cfg.get("risk", {})
        for mode in ["low", "medium", "high"]:
            if mode not in risk.get("budget_pct", {}):
                issues.append(f"Risk mode {mode} missing from budget_pct")

        if issues:
            return {"valid": False, "issues": issues}
        return {"valid": True, "issues": []}
    except Exception as e:
        return {"valid": False, "issues": [str(e)]}