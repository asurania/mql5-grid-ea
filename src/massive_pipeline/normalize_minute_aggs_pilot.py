from __future__ import annotations

from pathlib import Path

import polars as pl

RAW_DIR = Path("data/raw/massive/forex/minute_aggs/2026/03")
OUT_DIR = Path("data/processed/massive")
PAIR_MAP = {
    "C:EUR-JPY": "EURJPY",
    "C:GBP-JPY": "GBPJPY",
    "C:GBP-USD": "GBPUSD",
    "C:NZD-USD": "NZDUSD",
}


def session_label_expr() -> pl.Expr:
    h = pl.col("timestamp_utc").dt.hour()
    return (
        pl.when((h >= 0) & (h < 8)).then(pl.lit("asia"))
        .when((h >= 7) & (h < 16)).then(pl.lit("london"))
        .when((h >= 12) & (h < 21)).then(pl.lit("newyork"))
        .otherwise(pl.lit("other"))
        .alias("session_label")
    )


def main() -> None:
    files = sorted(RAW_DIR.glob("*.csv.gz"))
    if not files:
        raise SystemExit("No pilot raw files found")

    dfs = []
    for path in files:
        df = pl.read_csv(path)
        dfs.append(df)

    df = pl.concat(dfs)
    df = df.with_columns(
        [
            pl.col("ticker").replace(PAIR_MAP).alias("pair"),
            pl.from_epoch(pl.col("window_start"), time_unit="ns").dt.replace_time_zone("UTC").alias("timestamp_utc"),
        ]
    )
    df = df.with_columns(
        [
            pl.col("timestamp_utc").dt.date().alias("date_utc"),
            pl.col("timestamp_utc").dt.year().alias("year"),
            pl.col("timestamp_utc").dt.month().alias("month"),
            pl.col("timestamp_utc").dt.day().alias("day"),
            pl.col("timestamp_utc").dt.hour().alias("hour"),
            pl.col("timestamp_utc").dt.minute().alias("minute"),
            session_label_expr(),
        ]
    )
    df = df.select(
        [
            "pair",
            "ticker",
            "timestamp_utc",
            "date_utc",
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "session_label",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "transactions",
        ]
    ).sort(["pair", "timestamp_utc"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / "fx_minute_bars_pilot_2026_03.parquet"
    df.write_parquet(out_file)

    summary = (
        df.group_by(["pair", "session_label"])
        .agg(pl.len().alias("rows"))
        .sort(["pair", "session_label"])
    )
    summary.write_csv(OUT_DIR / "fx_minute_bars_pilot_2026_03_summary.csv")

    print(summary)
    print(f"Wrote {df.height} rows to {out_file}")


if __name__ == "__main__":
    main()
