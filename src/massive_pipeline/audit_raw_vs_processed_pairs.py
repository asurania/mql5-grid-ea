from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "massive" / "forex" / "minute_aggs"
PROCESSED_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "raw_vs_processed_pair_audit.json"
TARGET_PAIRS = ["AUDNZD", "NZDUSD", "GBPJPY", "GBPUSD"]
RAW_TICKERS = {
    "AUDNZD": "C:AUD-NZD",
    "NZDUSD": "C:NZD-USD",
    "GBPJPY": "C:GBP-JPY",
    "GBPUSD": "C:GBP-USD",
}


def raw_month_counts(year: int, month: int) -> dict[str, int]:
    month_dir = RAW_DIR / str(year) / f"{month:02d}"
    counts = defaultdict(int)
    if not month_dir.exists():
        return counts
    for path in sorted(month_dir.glob("*.csv.gz")):
        try:
            df = pl.read_csv(path)
        except Exception:
            continue
        if "ticker" not in df.columns:
            continue
        for pair, ticker in RAW_TICKERS.items():
            counts[pair] += int(df.filter(pl.col("ticker") == ticker).height)
    return counts


def processed_count(year: int, month: int, pair: str) -> int:
    path = PROCESSED_DIR / f"year={year:04d}" / f"month={month:02d}" / "data.parquet"
    if not path.exists():
        return 0
    try:
        return int(pl.read_parquet(path).filter(pl.col("pair") == pair).height)
    except Exception:
        return 0


def main() -> int:
    rows = []
    years = sorted([int(p.name) for p in RAW_DIR.glob('*') if p.is_dir() and p.name.isdigit()])
    for year in years:
        for month in range(1, 13):
            raw_counts = raw_month_counts(year, month)
            pair_rows = []
            for pair in TARGET_PAIRS:
                raw_rows = int(raw_counts.get(pair, 0))
                proc_rows = processed_count(year, month, pair)
                pair_rows.append({
                    'pair': pair,
                    'raw_rows': raw_rows,
                    'processed_rows': proc_rows,
                    'status': (
                        'missing_in_both' if raw_rows == 0 and proc_rows == 0 else
                        'raw_only' if raw_rows > 0 and proc_rows == 0 else
                        'processed_only' if raw_rows == 0 and proc_rows > 0 else
                        'ok' if raw_rows > 0 and proc_rows > 0 else
                        'unknown'
                    ),
                })
            rows.append({'year': year, 'month': month, 'pairs': pair_rows})
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'monthly': rows,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
