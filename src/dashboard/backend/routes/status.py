"""Status routes — read live trading status (read-only)."""

from fastapi import APIRouter
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]  # workspace root

router = APIRouter()


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/summary")
async def status_summary():
    """Get a high-level summary of the trading system state."""
    risk_policy = _read_json(ROOT / "data" / "live" / "policy" / "pair_risk_policy.json")
    entry_intent = _read_json(ROOT / "data" / "live" / "policy" / "entry_intent.json")
    grid_policy = _read_json(ROOT / "data" / "live" / "policy" / "grid_policy.json")
    bridge_run = _read_json(ROOT / "data" / "live" / "policy" / "mt5_live_bridge_run.json")
    event_actions = _read_json(ROOT / "data" / "live" / "event_risk" / "event_risk_actions.json")

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bridge": None,
        "session": None,
        "pairs": [],
        "event_risk": None,
    }

    if bridge_run:
        summary["bridge"] = {
            "last_run_utc": bridge_run.get("last_run_utc"),
            "run_count": bridge_run.get("run_count", 0),
            "status": bridge_run.get("status", "unknown"),
            "errors": bridge_run.get("errors", []),
        }

    if grid_policy:
        summary["session"] = {
            "name": grid_policy.get("session_name"),
            "close_utc": grid_policy.get("session_close_utc"),
            "managed_close_utc": grid_policy.get("managed_close_utc"),
            "daily_liquidate_utc": grid_policy.get("daily_liquidate_utc"),
            "risk_mode": grid_policy.get("risk_mode"),
            "account_equity": grid_policy.get("account_equity"),
        }

    if grid_policy and "pairs" in grid_policy:
        for p in grid_policy["pairs"]:
            pair_info = {
                "pair": p.get("pair"),
                "grid_mode": p.get("grid_mode"),
                "initial_lot": p.get("initial_lot"),
                "step_pips": p.get("step_pips"),
                "multiplier": p.get("multiplier"),
                "max_trades_per_side": p.get("max_trades_per_side"),
                "basket_tp_pips": p.get("basket_tp_pips"),
                "basket_sl_pips": p.get("basket_sl_pips"),
                "policy_id": p.get("policy_id"),
                "allow_new_basket": p.get("allow_new_basket"),
                "expires_at_utc": p.get("expires_at_utc"),
            }
            summary["pairs"].append(pair_info)

    if entry_intent and "pairs" in entry_intent:
        intent_map = {p["pair"]: p for p in entry_intent["pairs"] if "pair" in p}
        for ps in summary["pairs"]:
            pair = ps["pair"]
            if pair in intent_map:
                ps["entry_direction"] = intent_map[pair].get("direction")
                ps["entry_should_enter"] = intent_map[pair].get("should_enter")
                ps["entry_reason"] = intent_map[pair].get("reason")

    if risk_policy and "pair_policies" in risk_policy:
        rp_map = {p["pair"]: p for p in risk_policy["pair_policies"] if "pair" in p}
        for ps in summary["pairs"]:
            pair = ps["pair"]
            if pair in rp_map:
                ps["risk_action"] = rp_map[pair].get("policy_action")
                ps["risk_band"] = rp_map[pair].get("policy_band")

    if event_actions:
        summary["event_risk"] = event_actions

    return summary


@router.get("/pair-risk-policy")
async def status_pair_risk_policy():
    """Get the current pair risk policy."""
    data = _read_json(ROOT / "data" / "live" / "policy" / "pair_risk_policy.json")
    if not data:
        return {"status": "unavailable", "reason": "file not found"}
    return data


@router.get("/entry-intent")
async def status_entry_intent():
    """Get the current entry intent."""
    data = _read_json(ROOT / "data" / "live" / "policy" / "entry_intent.json")
    if not data:
        return {"status": "unavailable", "reason": "file not found"}
    return data


@router.get("/grid-policy")
async def status_grid_policy():
    """Get the current grid policy."""
    data = _read_json(ROOT / "data" / "live" / "policy" / "grid_policy.json")
    if not data:
        return {"status": "unavailable", "reason": "file not found"}
    return data


@router.get("/bridge")
async def status_bridge():
    """Get bridge run status."""
    data = _read_json(ROOT / "data" / "live" / "policy" / "mt5_live_bridge_run.json")
    if not data:
        return {"status": "unavailable", "reason": "bridge not running"}
    return data


@router.get("/event-risk")
async def status_event_risk():
    """Get current event risk actions."""
    data = _read_json(ROOT / "data" / "live" / "event_risk" / "event_risk_actions.json")
    if not data:
        return {"status": "unavailable", "reason": "file not found"}
    return data


@router.get("/session-range")
async def status_session_range():
    """Get session range predictions."""
    data = _read_json(ROOT / "data" / "live" / "policy" / "session_range_predictions.json")
    if not data:
        return {"status": "unavailable", "reason": "file not found"}
    return data