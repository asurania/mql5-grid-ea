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
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_core_v1.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_core_v1_monthly_summary.json"


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


def main() -> int:
    config = load_config()
    portfolio = load_json(PORTFOLIO_FILE)
    lot_sizing = portfolio.get('lot_sizing', {})
    rows = []
    for year_dir in sorted(PRICE_DIR.glob('year=*')):
        year = int(year_dir.name.split('=')[1])
        for month_dir in sorted(year_dir.glob('month=*')):
            month = int(month_dir.name.split('=')[1])
            month_total = 0.0
            month_forced = 0
            pair_rows = []
            for item in portfolio['portfolio']:
                pair = item['pair']
                session_name = item['session']
                frame = load_month_frame(pair, year, month)
                if frame.height == 0:
                    continue
                session_filter = build_session_filter(portfolio, session_name)
                segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= 30]
                policy = build_policy(item, config=config, lot_sizing=lot_sizing)
                risk = build_risk(config, item)
                pip_size_map = config['pip_config']['pip_size']
                pip_value_map = config['pip_config']['pip_value_per_001_lot']
                pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith('JPY') else 0.0001))
                pip_value = float(pip_value_map.get(pair, pip_value_map.get('GBPUSD', 0.13)))
                runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
                total = sum(r['buy_realized_pnl'] + r['sell_realized_pnl'] for r in runs)
                forced = sum(1 for r in runs if r.get('buy_closed_reason') == 'forced_session_close' or r.get('sell_closed_reason') == 'forced_session_close')
                month_total += total
                month_forced += forced
                pair_rows.append({
                    'pair': pair,
                    'session': session_name,
                    'total_pnl': total,
                    'forced_close_count': forced,
                    'segments': len(runs),
                })
            rows.append({
                'year': year,
                'month': month,
                'portfolio_total_pnl': month_total,
                'portfolio_forced_close_count': month_forced,
                'components': pair_rows,
            })
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'monthly': rows,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
