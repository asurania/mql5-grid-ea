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
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_core_v1_guarded.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "gbpusd_ny_session_behavior_tuning.json"
TARGET_SLOT = "GBPUSD:new_york"


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


def evaluate_variant(portfolio: dict, managed_close_minutes: int, min_segment_rows: int) -> dict:
    config = load_config()
    lot_sizing = portfolio.get('lot_sizing', {})
    item = next(x for x in portfolio['portfolio'] if f"{x['pair']}:{x['session']}" == TARGET_SLOT)
    pair = item['pair']
    session_name = item['session']
    total_pnl = 0.0
    total_forced = 0
    worst_segment = None
    segments_total = 0
    for year_dir in sorted(PRICE_DIR.glob('year=*')):
        year = int(year_dir.name.split('=')[1])
        for month_dir in sorted(year_dir.glob('month=*')):
            month = int(month_dir.name.split('=')[1])
            frame = load_month_frame(pair, year, month)
            if frame.height == 0:
                continue
            base_filter = build_session_filter(portfolio, session_name)
            session_filter = type(base_filter)(
                start_hhmm=base_filter.start_hhmm,
                stop_hhmm=base_filter.stop_hhmm,
                managed_close_minutes=managed_close_minutes,
                timezone_name=base_filter.timezone_name,
                allowed_weekdays=base_filter.allowed_weekdays,
                exempted_month_days=base_filter.exempted_month_days,
            )
            segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= min_segment_rows]
            policy = build_policy(item, config=config, lot_sizing=lot_sizing)
            risk = build_risk(config, item)
            pip_size_map = config['pip_config']['pip_size']
            pip_value_map = config['pip_config']['pip_value_per_001_lot']
            pip_size = float(pip_size_map.get(pair, 0.0001))
            pip_value = float(pip_value_map.get(pair, pip_value_map.get('GBPUSD', 0.13)))
            runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
            vals = [r['buy_realized_pnl'] + r['sell_realized_pnl'] for r in runs]
            forced = sum(1 for r in runs if r.get('buy_closed_reason') == 'forced_session_close' or r.get('sell_closed_reason') == 'forced_session_close')
            total_pnl += sum(vals)
            total_forced += forced
            segments_total += len(runs)
            if vals:
                w = min(vals)
                if worst_segment is None or w < worst_segment:
                    worst_segment = w
    score = total_pnl - total_forced * 20.0 + (worst_segment or 0.0)
    return {
        'managed_close_minutes': managed_close_minutes,
        'min_segment_rows': min_segment_rows,
        'total_pnl': total_pnl,
        'forced_close_count': total_forced,
        'segments': segments_total,
        'worst_segment_pnl': worst_segment,
        'score': score,
    }


def main() -> int:
    portfolio = load_json(PORTFOLIO_FILE)
    trials = []
    for managed_close in (30, 45, 60, 75, 90):
        for min_rows in (30, 60, 90):
            trials.append(evaluate_variant(portfolio, managed_close, min_rows))
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
