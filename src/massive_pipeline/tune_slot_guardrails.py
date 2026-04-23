from __future__ import annotations

import json
from copy import deepcopy
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
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_core_v1_guarded.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "slot_guardrail_tuning.json"
TARGET_SLOTS = {"GBPJPY:london", "GBPUSD:new_york"}


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


def apply_slot_guardrails(item: dict, guardrails: dict) -> dict:
    slot_key = f"{item['pair']}:{item['session']}"
    overrides = guardrails.get('slot_overrides', {}).get(slot_key, {})
    out = dict(item)
    if 'max_grid_levels' in overrides:
        out['grid_levels'] = min(int(out.get('grid_levels', overrides['max_grid_levels'])), int(overrides['max_grid_levels']))
    if 'max_slot_drawdown_currency' in overrides:
        out['drawdown_limit_currency'] = min(float(out.get('drawdown_limit_currency', overrides['max_slot_drawdown_currency'])), float(overrides['max_slot_drawdown_currency']))
    return out


def evaluate(portfolio: dict, config: dict) -> dict:
    lot_sizing = portfolio.get('lot_sizing', {})
    guardrails = portfolio.get('guardrails', {})
    total_pnl = 0.0
    total_forced = 0
    slot_forced = {slot: 0 for slot in TARGET_SLOTS}
    slot_pnl = {slot: 0.0 for slot in TARGET_SLOTS}
    slot_worst_seg = {slot: None for slot in TARGET_SLOTS}
    for year_dir in sorted(PRICE_DIR.glob('year=*')):
        year = int(year_dir.name.split('=')[1])
        for month_dir in sorted(year_dir.glob('month=*')):
            month = int(month_dir.name.split('=')[1])
            for item in portfolio['portfolio']:
                slot_key = f"{item['pair']}:{item['session']}"
                guarded_item = apply_slot_guardrails(item, guardrails)
                pair = guarded_item['pair']
                session_name = guarded_item['session']
                frame = load_month_frame(pair, year, month)
                if frame.height == 0:
                    continue
                session_filter = build_session_filter(portfolio, session_name)
                segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= 30]
                policy = build_policy(guarded_item, config=config, lot_sizing=lot_sizing)
                risk = build_risk(config, guarded_item)
                pip_size_map = config['pip_config']['pip_size']
                pip_value_map = config['pip_config']['pip_value_per_001_lot']
                pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith('JPY') else 0.0001))
                pip_value = float(pip_value_map.get(pair, pip_value_map.get('GBPUSD', 0.13)))
                runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
                totals = [r['buy_realized_pnl'] + r['sell_realized_pnl'] for r in runs]
                forced = sum(1 for r in runs if r.get('buy_closed_reason') == 'forced_session_close' or r.get('sell_closed_reason') == 'forced_session_close')
                total = sum(totals)
                total_pnl += total
                total_forced += forced
                if slot_key in TARGET_SLOTS:
                    slot_forced[slot_key] += forced
                    slot_pnl[slot_key] += total
                    if totals:
                        worst = min(totals)
                        if slot_worst_seg[slot_key] is None or worst < slot_worst_seg[slot_key]:
                            slot_worst_seg[slot_key] = worst
    score = total_pnl - total_forced * 35.0
    if slot_worst_seg['GBPJPY:london'] is not None:
        score += min(0.0, slot_worst_seg['GBPJPY:london']) * 2.0
    score -= slot_forced['GBPUSD:new_york'] * 8.0
    return {
        'total_pnl': total_pnl,
        'total_forced': total_forced,
        'slot_forced': slot_forced,
        'slot_pnl': slot_pnl,
        'slot_worst_seg': slot_worst_seg,
        'score': score,
    }


def variants(base: dict):
    base_overrides = base['guardrails']['slot_overrides']
    for gj_levels in (7, 8, 9):
        for gj_dd in (140.0, 160.0, 180.0):
            for gu_dd in (90.0, 110.0, 130.0):
                for gu_levels in (3, 4):
                    variant = deepcopy(base)
                    variant['guardrails']['slot_overrides']['GBPJPY:london']['max_grid_levels'] = gj_levels
                    variant['guardrails']['slot_overrides']['GBPJPY:london']['max_slot_drawdown_currency'] = gj_dd
                    variant['guardrails']['slot_overrides']['GBPUSD:new_york']['max_grid_levels'] = gu_levels
                    variant['guardrails']['slot_overrides']['GBPUSD:new_york']['max_slot_drawdown_currency'] = gu_dd
                    yield variant


def main() -> int:
    config = load_config()
    base = load_json(PORTFOLIO_FILE)
    trials = []
    for variant in variants(base):
        result = evaluate(variant, config)
        trials.append({
            'slot_overrides': variant['guardrails']['slot_overrides'],
            **result,
        })
    trials.sort(key=lambda x: x['score'], reverse=True)
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'best': trials[:10],
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
