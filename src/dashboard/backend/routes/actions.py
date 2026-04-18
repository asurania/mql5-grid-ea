"""Action routes — trigger trading system actions."""

from fastapi import APIRouter, HTTPException
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]  # workspace root
PYTHON = ROOT / ".venv-forex" / "bin" / "python"
SRC = ROOT / "src" / "massive_pipeline"

router = APIRouter()


def _run_script(script_name: str, args: list[str] = None) -> dict:
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
            timeout=120,
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


@router.post("/refresh-policy")
async def refresh_policy():
    """Force a full policy refresh (run the master pipeline once)."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from massive_pipeline.trading_config import load_config
    cfg = load_config()
    equity = cfg["account"]["equity"]
    risk_mode = cfg["account"]["risk_mode"]

    args = ["--account-equity", str(equity), "--risk-mode", risk_mode]
    if cfg.get("bridge", {}).get("allow_gbpjpy_demo_override"):
        args.append("--allow-gbpjpy-demo-override")

    result = _run_script("run_event_risk_master.py")
    return {"status": "refreshed", "result": result}


@router.post("/refresh-grid-policy")
async def refresh_grid_policy():
    """Rebuild just the grid policy."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from massive_pipeline.trading_config import load_config
    cfg = load_config()
    equity = cfg["account"]["equity"]
    risk_mode = cfg["account"]["risk_mode"]

    args = ["--account-equity", str(equity), "--risk-mode", risk_mode]
    if cfg.get("bridge", {}).get("allow_gbpjpy_demo_override"):
        args.append("--allow-gbpjpy-demo-override")

    result = _run_script("build_grid_policy.py", args)
    return {"status": "refreshed", "result": result}


@router.post("/refresh-entry-intent")
async def refresh_entry_intent():
    """Rebuild just the entry intent."""
    result = _run_script("build_entry_intent_v2.py")
    return {"status": "refreshed", "result": result}


@router.post("/copy-to-mt5")
async def copy_to_mt5():
    """Copy all policy files to MT5 handoff directories."""
    result = _run_script("publish_pair_risk_policy.py")
    result2 = _run_script("publish_entry_intent.py")
    result3 = _run_script("publish_grid_policy.py")
    return {
        "status": "copied",
        "results": [result, result2, result3],
    }


@router.post("/toggle-trading")
async def toggle_trading(data: dict):
    """Toggle live trading on/off via config."""
    enabled = data.get("enabled")
    if enabled is None:
        raise HTTPException(400, "Must provide 'enabled' (true/false)")

    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from massive_pipeline.trading_config import patch_config

    updated = patch_config({"bridge": {"live_trading_enabled": enabled}})
    return {"status": "toggled", "live_trading_enabled": enabled}


@router.post("/force-close-pair")
async def force_close_pair(data: dict):
    """Mark a pair for force close in the next policy cycle.

    This sets the pair's grid policy to no_trade template,
    which the MQL5 EA will pick up on its next refresh.
    """
    pair = data.get("pair")
    if not pair:
        raise HTTPException(400, "Must provide 'pair'")

    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from massive_pipeline.trading_config import patch_config

    # Set the pair's template to no_trade
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
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from massive_pipeline.trading_config import load_config

    try:
        cfg = load_config()
        issues = []

        # Basic validation
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