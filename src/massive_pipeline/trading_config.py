"""Trading configuration loader.

Reads config/trading_config.json as the single source of truth.
All pipeline scripts should call load_config() instead of using hardcoded constants.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config" / "trading_config.json"

_config_cache: dict | None = None
_config_mtime: float = 0.0


def _read_raw() -> dict:
    """Read the raw JSON config file."""
    global _config_cache, _config_mtime
    if not CONFIG_FILE.exists():
        return _defaults()
    mtime = CONFIG_FILE.stat().st_mtime
    if _config_cache is not None and mtime == _config_mtime:
        return _config_cache
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _config_cache = data
    _config_mtime = mtime
    return data


def load_config() -> dict:
    """Load the full trading config, with defaults for any missing sections."""
    raw = _read_raw()
    defaults = _defaults()
    # Deep merge: raw overrides defaults
    return _deep_merge(defaults, raw)


def save_config(config: dict) -> None:
    """Write the full config back to disk."""
    global _config_cache, _config_mtime
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    _config_cache = config
    _config_mtime = CONFIG_FILE.stat().st_mtime


def patch_config(patch: dict[str, Any]) -> dict:
    """Apply a partial update to the config and save.
    Returns the updated full config.
    """
    config = load_config()
    merged = _deep_merge(config, patch)
    save_config(merged)
    return merged


def reset_config() -> dict:
    """Reset config to defaults."""
    defaults = _defaults()
    save_config(defaults)
    return defaults


# --- Convenience accessors ---

def get_account() -> dict:
    c = load_config()
    return c.get("account", {})


def get_sessions() -> dict:
    c = load_config()
    return c.get("sessions", {})


def get_risk() -> dict:
    c = load_config()
    return c.get("risk", {})


def get_grid_optimizer() -> dict:
    c = load_config()
    return c.get("grid_optimizer", {})


def get_entry_intent() -> dict:
    c = load_config()
    return c.get("entry_intent", {})


def get_pip_config() -> dict:
    c = load_config()
    return c.get("pip_config", {})


def get_pairs() -> list[str]:
    c = load_config()
    return c.get("pairs", ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"])


def get_bridge() -> dict:
    c = load_config()
    return c.get("bridge", {})


def get_grid_templates() -> dict:
    c = load_config()
    return c.get("grid_templates", {})


# --- Internal helpers ---

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Override values win."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _defaults() -> dict:
    """Return the full default config (same as the initial trading_config.json)."""
    return {
        "account": {
            "equity": 10000.0,
            "risk_mode": "medium",
            "currency": "USD",
        },
        "pairs": ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"],
        "sessions": {
            "asia": {
                "enabled": True,
                "start_ny_time": [18, 0],
                "managed_close_ny_time": [22, 0],
                "close_utc": [3, 0],
                "managed_close_minutes_before": 0,
                "tp_pips": 4.0,
                "sl_pips": 40.0,
            },
            "london": {
                "enabled": True,
                "start_ny_time": [22, 0],
                "managed_close_ny_time": [6, 0],
                "close_utc": [10, 0],
                "managed_close_minutes_before": 0,
                "tp_pips": 3.0,
                "sl_pips": 55.0,
            },
            "new_york": {
                "enabled": True,
                "start_ny_time": [8, 0],
                "close_utc": [21, 0],
                "managed_close_minutes_before": 30,
                "liquidate_minutes_before": 10,
                "tp_pips": 3.0,
                "sl_pips": 50.0,
            },
        },
        "daily_liquidation_utc": [20, 50],
        "risk": {
            "budget_pct": {"low": 0.01, "medium": 0.015, "high": 0.02},
            "target_profit_pct": {"low": 0.01, "medium": 0.015, "high": 0.02},
            "max_basket_dd_pct": {"low": 0.01, "medium": 0.015, "high": 0.02},
            "min_step_to_spread_ratio": {"low": 4.0, "medium": 3.0, "high": 2.5},
            "min_free_margin_percent": {"low": 85.0, "medium": 75.0, "high": 65.0},
        },
        "grid_optimizer": {
            "search_step_pips": [6, 8, 10, 12, 15, 18, 22],
            "search_multipliers": [1.03, 1.05, 1.08, 1.10, 1.12, 1.15, 1.20],
            "search_levels": [2, 3, 4, 5, 6],
            "min_initial_lot": 0.01,
            "max_initial_lot": 5.00,
            "lot_step": 0.01,
            "max_gross_lots_pct_of_equity": 0.00004,
        },
        "entry_intent": {
            "min_alignment_score": 0.5,
            "min_trend_strength": 0.0002,
            "max_trend_strength": 0.015,
            "min_atr_frac": 0.0003,
            "max_atr_frac": 0.008,
            "expiry_minutes": 15,
            "legacy_ma_period": 21,
            "legacy_ma_price": "close",
            "legacy_gann_use": True,
            "legacy_gann_period": 21,
        },
        "pip_config": {
            "pip_size": {"EURJPY": 0.01, "GBPJPY": 0.01, "GBPUSD": 0.0001, "NZDUSD": 0.0001},
            "pip_value_per_001_lot": {"EURJPY": 0.09, "GBPJPY": 0.09, "GBPUSD": 0.13, "NZDUSD": 0.13},
            "assumed_spread_pips": {"EURJPY": 1.2, "GBPJPY": 1.8, "GBPUSD": 1.0, "NZDUSD": 1.4},
        },
        "bridge": {
            "refresh_interval_seconds": 30,
            "policy_expiry_minutes": 15,
            "destinations": [
                "C:\\Program Files\\MetaTrader 5\\MQL5\\Files\\ForexSlave\\",
                "C:\\Users\\asurani\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files\\ForexSlave\\",
            ],
            "allow_gbpjpy_demo_override": False,
        },
        "grid_templates": {
            "no_trade": {
                "allow_new_basket": False, "grid_mode": "both_sides", "seed_mode": "single_side",
                "step_pips": 0, "initial_lot": 0.0, "multiplier": 1.0, "max_trades_per_side": 0,
                "basket_tp_currency": 0.0, "max_gross_lots": 0.0, "max_basket_drawdown_currency": 0.0,
                "min_step_to_spread_ratio": 0.0, "min_free_margin_percent": 0.0,
                "flatten_on_strong_avoid": True, "confidence": 1.0, "reason": "no_trade_template",
            },
        },
    }