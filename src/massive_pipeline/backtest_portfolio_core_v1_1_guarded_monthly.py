from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.backtest_pair_session_policy import (
    build_policy,
    build_risk,
    build_session_filter,
    load_json,
    run_segment,
    segmented_rows,
)
from massive_pipeline.trading_config import load_config

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_core_v1_1_guarded.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_core_v1_1_guarded_monthly_summary.json"


def load_month_frame(pair: str, year: int, month: int) -> pl.DataFrame:
    path = PRICE_DIR / f"year={year:04d}" / f"month={month:02d}" / "data.parquet"
    if not path.exists():
        return pl.DataFrame(schema={"timestamp_utc": pl.Datetime, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "pair": pl.Utf8})
    return (
        pl.read_parquet(path)
        .filter(pl.col("pair") == pair.upper())
        .select(["timestamp_utc", "open", "high", "low", "close", "pair"])
        .sort("timestamp_utc")
    )


def apply_slot_guardrails(item: dict, guardrails: dict) -> tuple[dict, int | None]:
    slot_key = f"{item['pair']}:{item['session']}"
    overrides = guardrails.get('slot_overrides', {}).get(slot_key, {})
    out = dict(item)
    managed_close_override = None
    if 'max_grid_levels' in overrides:
        max_levels = int(overrides['max_grid_levels'])
        out['grid_levels'] = min(int(out.get('grid_levels', max_levels)), max_levels)
    if 'max_slot_drawdown_currency' in overrides:
        out['drawdown_limit_currency'] = min(float(out.get('drawdown_limit_currency', overrides['max_slot_drawdown_currency'])), float(overrides['max_slot_drawdown_currency']))
    if 'managed_close_minutes' in overrides:
        managed_close_override = int(overrides['managed_close_minutes'])
    return out, managed_close_override


def main() -> int:
    config = load_config()
    portfolio = load_json(PORTFOLIO_FILE)
    lot_sizing = portfolio.get('lot_sizing', {})
    guardrails = portfolio.get('guardrails', {})
    rows = []
    for year_dir in sorted(PRICE_DIR.glob('year=*')):
        year = int(year_dir.name.split('=')[1])
        for month_dir in sorted(year_dir.glob('month=*')):
            month = int(month_dir.name.split('=')[1])
            month_total = 0.0
            month_forced = 0
            pair_rows = []
            active_slots = 0
            total_initial_lots = 0.0
            blocked_new_entries = False
            for item in portfolio['portfolio']:
                if active_slots >= int(guardrails.get('max_active_slots', 999)):
                    break
                guarded_item, managed_close_override = apply_slot_guardrails(item, guardrails)
                pair = guarded_item['pair']
                session_name = guarded_item['session']
                if blocked_new_entries:
                    break
                frame = load_month_frame(pair, year, month)
                if frame.height == 0:
                    continue
                policy = build_policy(guarded_item, config=config, lot_sizing=lot_sizing)
                if total_initial_lots + float(policy.initial_lot) > float(guardrails.get('max_total_initial_lots', 999.0)):
                    continue
                base_filter = build_session_filter(portfolio, session_name)
                session_filter = type(base_filter)(
                    start_hhmm=base_filter.start_hhmm,
                    stop_hhmm=base_filter.stop_hhmm,
                    managed_close_minutes=managed_close_override if managed_close_override is not None else base_filter.managed_close_minutes,
                    timezone_name=base_filter.timezone_name,
                    allowed_weekdays=base_filter.allowed_weekdays,
                    exempted_month_days=base_filter.exempted_month_days,
                )
                segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= 30]
                risk = build_risk(config, guarded_item)
                pip_size_map = config['pip_config']['pip_size']
                pip_value_map = config['pip_config']['pip_value_per_001_lot']
                pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith('JPY') else 0.0001))
                pip_value = float(pip_value_map.get(pair, pip_value_map.get('GBPUSD', 0.13)))
                runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
                total = sum(r['buy_realized_pnl'] + r['sell_realized_pnl'] for r in runs)
                forced = sum(1 for r in runs if r.get('buy_closed_reason') == 'forced_session_close' or r.get('sell_closed_reason') == 'forced_session_close')
                month_total += total
                month_forced += forced
                active_slots += 1
                total_initial_lots += float(policy.initial_lot)
                pair_rows.append({
                    'pair': pair,
                    'session': session_name,
                    'total_pnl': total,
                    'forced_close_count': forced,
                    'segments': len(runs),
                    'guarded_policy': guarded_item,
                    'managed_close_minutes': session_filter.managed_close_minutes,
                })
                if month_total <= -float(guardrails.get('daily_loss_cap_currency', 999999.0)) and guardrails.get('block_new_entries_after_daily_cap', False):
                    blocked_new_entries = True
            rows.append({
                'year': year,
                'month': month,
                'portfolio_total_pnl': month_total,
                'portfolio_forced_close_count': month_forced,
                'active_slots': active_slots,
                'components': pair_rows,
            })
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'guardrails': guardrails,
        'monthly': rows,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
