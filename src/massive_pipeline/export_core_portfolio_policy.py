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
OUT_FILE = ROOT / "data" / "live" / "policy" / "core_portfolio_policy.json"


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


def main() -> int:
    config = load_config()
    source = load_json(SOURCE_FILE)
    lot_sizing = source.get('lot_sizing', {})
    guardrails = source.get('guardrails', {})
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=15)
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
            'expires_at_utc': expires.isoformat(),
            'reason': f"core_v1.1_guarded_{guarded_item['pair'].lower()}_{guarded_item['session']}"
        }
        if 'tail_loss_guard_currency' in slot_override:
            row['tail_loss_guard_currency'] = float(slot_override['tail_loss_guard_currency'])
        if 'forced_close_rate_warn' in slot_override:
            row['forced_close_rate_warn'] = float(slot_override['forced_close_rate_warn'])
        pairs.append(row)
    payload = {
        'generated_at_utc': now.isoformat(),
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
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
