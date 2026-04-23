from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.backtest_pair_session_policy import build_session_filter, load_json, segmented_rows

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_v3.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_v3_coverage_audit.json"


def load_month_frame(pair: str, year: int, month: int) -> pl.DataFrame:
    path = PRICE_DIR / f"year={year}" / f"month={month}" / "data.parquet"
    if not path.exists():
        return pl.DataFrame(schema={"timestamp_utc": pl.Datetime, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "pair": pl.Utf8})
    return (
        pl.read_parquet(path)
        .filter(pl.col("pair") == pair.upper())
        .select(["timestamp_utc", "open", "high", "low", "close", "pair"])
        .sort("timestamp_utc")
    )


def main() -> int:
    portfolio = load_json(PORTFOLIO_FILE)
    rows = []
    for year_dir in sorted(PRICE_DIR.glob('year=*')):
        year = int(year_dir.name.split('=')[1])
        for month_dir in sorted(year_dir.glob('month=*')):
            month = int(month_dir.name.split('=')[1])
            month_rows = []
            for item in portfolio['portfolio']:
                pair = item['pair']
                session_name = item['session']
                frame = load_month_frame(pair, year, month)
                raw_rows = frame.height
                session_filter = build_session_filter(portfolio, session_name)
                segments = segmented_rows(frame, session_filter) if raw_rows else []
                qualifying_segments = [seg for seg in segments if len(seg) >= 30]
                month_rows.append({
                    'pair': pair,
                    'session': session_name,
                    'raw_rows': raw_rows,
                    'segment_count': len(segments),
                    'qualifying_segment_count': len(qualifying_segments),
                    'max_segment_rows': max((len(seg) for seg in segments), default=0),
                    'status': (
                        'no_raw_rows' if raw_rows == 0 else
                        'no_segments' if len(segments) == 0 else
                        'no_qualifying_segments' if len(qualifying_segments) == 0 else
                        'ok'
                    ),
                })
            rows.append({
                'year': year,
                'month': month,
                'slots': month_rows,
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
