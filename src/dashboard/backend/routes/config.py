"""Config routes — read and update trading configuration."""

from fastapi import APIRouter, HTTPException
from typing import Any
import sys
from pathlib import Path

# Add src to path so we can import trading_config
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from massive_pipeline.trading_config import (
    load_config,
    save_config,
    patch_config,
    reset_config,
    get_account,
    get_sessions,
    get_risk,
    get_grid_optimizer,
    get_entry_intent,
    get_pip_config,
    get_pairs,
    get_bridge,
    get_grid_templates,
)

router = APIRouter()


# --- Full config ---

@router.get("/")
async def get_full_config():
    """Get the complete trading configuration."""
    return load_config()


@router.put("/")
async def put_full_config(config: dict):
    """Replace the entire trading configuration."""
    save_config(config)
    return {"status": "saved", "config": load_config()}


@router.patch("/")
async def patch_full_config(patch: dict):
    """Partial update of the trading configuration (deep merge)."""
    updated = patch_config(patch)
    return {"status": "patched", "config": updated}


@router.post("/reset")
async def reset_full_config():
    """Reset configuration to defaults."""
    defaults = reset_config()
    return {"status": "reset", "config": defaults}


# --- Sections ---

@router.get("/account")
async def read_account():
    return get_account()


@router.patch("/account")
async def patch_account(data: dict):
    return patch_config({"account": data})


@router.get("/pairs")
async def read_pairs():
    return {"pairs": get_pairs()}


@router.put("/pairs")
async def put_pairs(data: dict):
    pairs = data.get("pairs")
    if not pairs or not isinstance(pairs, list):
        raise HTTPException(400, "pairs must be a list")
    return patch_config({"pairs": pairs})


@router.get("/sessions")
async def read_sessions():
    return get_sessions()


@router.get("/sessions/{session_name}")
async def read_session(session_name: str):
    sessions = get_sessions()
    if session_name not in sessions:
        raise HTTPException(404, f"Session '{session_name}' not found")
    return sessions[session_name]


@router.patch("/sessions/{session_name}")
async def patch_session(session_name: str, data: dict):
    sessions = get_sessions()
    if session_name not in sessions:
        raise HTTPException(404, f"Session '{session_name}' not found")
    return patch_config({"sessions": {session_name: data}})


@router.get("/daily-liquidation")
async def read_daily_liquidation():
    cfg = load_config()
    return {"daily_liquidation_utc": cfg.get("daily_liquidation_utc", [20, 50])}


@router.put("/daily-liquidation")
async def put_daily_liquidation(data: dict):
    val = data.get("daily_liquidation_utc")
    if not val or len(val) != 2:
        raise HTTPException(400, "daily_liquidation_utc must be [hour, minute]")
    return patch_config({"daily_liquidation_utc": val})


@router.get("/risk")
async def read_risk():
    return get_risk()


@router.patch("/risk")
async def patch_risk(data: dict):
    return patch_config({"risk": data})


@router.get("/grid-optimizer")
async def read_grid_optimizer():
    return get_grid_optimizer()


@router.patch("/grid-optimizer")
async def patch_grid_optimizer(data: dict):
    return patch_config({"grid_optimizer": data})


@router.get("/entry-intent")
async def read_entry_intent():
    return get_entry_intent()


@router.patch("/entry-intent")
async def patch_entry_intent(data: dict):
    return patch_config({"entry_intent": data})


@router.get("/pip-config")
async def read_pip_config():
    return get_pip_config()


@router.patch("/pip-config")
async def patch_pip_config(data: dict):
    return patch_config({"pip_config": data})


@router.get("/bridge")
async def read_bridge():
    return get_bridge()


@router.patch("/bridge")
async def patch_bridge(data: dict):
    return patch_config({"bridge": data})


@router.get("/grid-templates")
async def read_grid_templates():
    return get_grid_templates()


@router.get("/grid-templates/{template_name}")
async def read_grid_template(template_name: str):
    templates = get_grid_templates()
    if template_name not in templates:
        raise HTTPException(404, f"Template '{template_name}' not found")
    return templates[template_name]


@router.patch("/grid-templates/{template_name}")
async def patch_grid_template(template_name: str, data: dict):
    templates = get_grid_templates()
    if template_name not in templates:
        raise HTTPException(404, f"Template '{template_name}' not found")
    return patch_config({"grid_templates": {template_name: data}})