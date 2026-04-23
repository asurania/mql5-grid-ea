"""Emit all three MT5 policy JSONs from core_v1.1_guarded config.

Outputs:
  data/live/policy/core_portfolio_policy.json   (already existed, now unified)
  data/live/policy/entry_intent.json             (new)
  data/live/policy/pair_risk_policy.json         (new)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.backtest_pair_session_policy import build_policy, load_json
from massive_pipeline.trading_config import load_config

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILE = ROOT / "config" / "pair_session_portfolio_core_v1_1_guarded.json"
POLICY_DIR = ROOT / "data" / "live" / "policy"

INTENT_EXPIRY_MINUTES = 15
RISK_EXPIRY_MINUTES = 15
CORE_EXPIRY_MINUTES = 15


def mt5_datetime(dt: datetime) -> str:
    """Format datetime for MQL5 StringToTime(): 'YYYY.MM.DD HH:MM:SS'."""
    return dt.strftime("%Y.%m.%d %H:%M:%S")


def apply_slot_guardrails(item: dict, guardrails: dict) -> tuple[dict, int | None]:
    slot_key = f"{item['pair']}:{item['session']}"
    overrides = guardrails.get('slot_overrides', {}).get(slot_key, {})
    out = dict(item)
    managed_close_override = None
    if 'max_grid_levels' in overrides:
        out['grid_levels'] = min(int(out.get('grid_levels', overrides['max_grid_levels'])), int(overrides['max_grid_levels']))
    if 'max_slot_drawdown_currency' in overrides:
        out['drawdown_limit_currency'] = min(float(out.get('drawdown_limit_currency', overrides['max_slot_drawdown_currency'])), float(overrides['max_slot_drawdown_currency']))
    if 'managed_close_minutes' in overrides:
        managed_close_override = int(overrides['managed_close_minutes'])
    return out, managed_close_override


def emit_core_portfolio_policy(source: dict, config: dict, now: datetime) -> dict:
    lot_sizing = source.get('lot_sizing', {})
    guardrails = source.get('guardrails', {})
    expires = now + timedelta(minutes=CORE_EXPIRY_MINUTES)
    pairs = []
    for item in source.get('portfolio', []):
        if not item.get('enabled', True):
            continue
        guarded_item, managed_close_override = apply_slot_guardrails(item, guardrails)
        policy = build_policy(guarded_item, config=config, lot_sizing=lot_sizing)
        slot_key = f"{guarded_item['pair']}:{guarded_item['session']}"
        slot_override = guardrails.get('slot_overrides', {}).get(slot_key, {})
        row = {
            'pair': guarded_item['pair'],
            'session_name': guarded_item['session'],
            'enabled': True,
            'allow_new_basket': True,
            'grid_mode': 'both_sides',
            'seed_mode': 'single_side',
            'step_pips': float(guarded_item['step_pips']),
            'initial_lot': float(policy.initial_lot),
            'initial_lot_mode': guarded_item.get('initial_lot_mode', lot_sizing.get('mode', 'fixed')),
            'base_equity': float(guarded_item.get('base_equity', lot_sizing.get('base_equity', 10000.0))),
            'multiplier': float(guarded_item['multiplier']),
            'max_trades_per_side': int(guarded_item['grid_levels']),
            'basket_tp_pips': float(guarded_item['tp_pips']),
            'basket_sl_pips': float(guarded_item['sl_pips']),
            'max_basket_drawdown_currency': float(guarded_item['drawdown_limit_currency']),
            'max_slot_drawdown_currency': float(slot_override.get('max_slot_drawdown_currency', guarded_item['drawdown_limit_currency'])),
            'managed_close_minutes': managed_close_override if managed_close_override is not None else 30,
            'session_close_behavior': 'managed_close_only',
            'flatten_on_account_breach': bool(guardrails.get('flatten_on_account_breach', True)),
            'expires_at_utc': mt5_datetime(expires),
            'reason': f"core_v1.1_guarded_{guarded_item['pair'].lower()}_{guarded_item['session']}"
        }
        if 'tail_loss_guard_currency' in slot_override:
            row['tail_loss_guard_currency'] = float(slot_override['tail_loss_guard_currency'])
        if 'forced_close_rate_warn' in slot_override:
            row['forced_close_rate_warn'] = float(slot_override['forced_close_rate_warn'])
        pairs.append(row)
    return {
        'generated_at_utc': mt5_datetime(now),
        'version': 'core_portfolio_policy_v1',
        'source': 'core_v1.1_guarded',
        'account': {
            'equity_reference': float(lot_sizing.get('base_equity', 10000.0)),
            'lot_sizing_mode': lot_sizing.get('mode', 'fixed'),
        },
        'guardrails': {
            'max_active_slots': int(guardrails.get('max_active_slots', 3)),
            'max_total_initial_lots': float(guardrails.get('max_total_initial_lots', 0.04)),
            'max_total_drawdown_currency': float(guardrails.get('max_total_drawdown_currency', 300.0)),
            'daily_loss_cap_currency': float(guardrails.get('daily_loss_cap_currency', 220.0)),
            'session_loss_cap_currency': float(guardrails.get('session_loss_cap_currency', 120.0)),
            'flatten_on_account_breach': bool(guardrails.get('flatten_on_account_breach', True)),
            'block_new_entries_after_daily_cap': bool(guardrails.get('block_new_entries_after_daily_cap', True)),
        },
        'pairs': pairs,
    }


def emit_pair_risk_policy(source: dict, now: datetime) -> dict:
    """Emit pair_risk_policy.json from core config.

    This file gates whether a pair/session is allowed to start new baskets.
    In steady state, all core slots are enabled and allowed.
    A control-plane process can later override specific rows.
    """
    expires = now + timedelta(minutes=RISK_EXPIRY_MINUTES)
    pairs = []
    for item in source.get('portfolio', []):
        if not item.get('enabled', True):
            continue
        pairs.append({
            'pair': item['pair'],
            'enabled': True,
            'allow_new_entries': True,
            'policy_action': 'allow_trading',
            'reason': f"core_v1.1_guarded_{item['pair'].lower()}_{item['session']}",
            'expires_at_utc': mt5_datetime(expires),
        })
    return {
        'generated_at_utc': mt5_datetime(now),
        'version': 'pair_risk_policy_v1',
        'pairs': pairs,
    }


def emit_entry_intent(source: dict, now: datetime) -> dict:
    """Emit entry_intent.json from core config.

    This file authorizes first-entry direction for each slot.
    When grid_mode is 'both_sides', direction is 'both' so the EA
    seeds both buy and sell grids simultaneously.

    A control-plane process can later override direction or confidence.
    """
    expires = now + timedelta(minutes=INTENT_EXPIRY_MINUTES)
    pairs = []
    for item in source.get('portfolio', []):
        if not item.get('enabled', True):
            continue
        grid_mode = item.get('grid_mode', 'both_sides')
        if grid_mode == 'both_sides':
            direction = 'both'
            reason = 'both_sides_grid_seed'
        else:
            session = item.get('session', '')
            if 'london' in session.lower():
                direction = 'sell'
                reason = 'london_mean_reversion_sell_bias'
            elif 'new_york' in session.lower() or 'newyork' in session.lower():
                direction = 'sell'
                reason = 'new_york_mean_reversion_sell_bias'
            else:
                direction = 'sell'
                reason = 'default_sell_bias'
        pairs.append({
            'pair': item['pair'],
            'enabled': True,
            'allow_first_entry': True,
            'direction': direction,
            'confidence': 0.5,
            'reason': reason,
            'expires_at_utc': mt5_datetime(expires),
        })
    return {
        'generated_at_utc': mt5_datetime(now),
        'version': 'entry_intent_v1',
        'pairs': pairs,
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def main() -> int:
    source = load_json(SOURCE_FILE)
    config = load_config()
    now = datetime.now(timezone.utc)

    core_policy = emit_core_portfolio_policy(source, config, now)
    pair_risk = emit_pair_risk_policy(source, now)
    entry_intent = emit_entry_intent(source, now)

    write_json(POLICY_DIR / "core_portfolio_policy.json", core_policy)
    write_json(POLICY_DIR / "pair_risk_policy.json", pair_risk)
    write_json(POLICY_DIR / "entry_intent.json", entry_intent)

    print(f"Core portfolio policy: {len(core_policy['pairs'])} pairs")
    print(f"Pair risk policy:      {len(pair_risk['pairs'])} pairs")
    print(f"Entry intent:          {len(entry_intent['pairs'])} pairs")
    print(f"Written to {POLICY_DIR}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())