from __future__ import annotations

from pathlib import Path

import polars as pl

EVENTS_FILE = Path("data/processed/modeling/event_risk_training_dataset.parquet")
PRICE_DIR = Path("data/processed/massive/fx_minute_bars")
OUT_DIR = Path("data/processed/modeling")
MONTHS = [
    (2023, m) for m in range(1, 13)
] + [
    (2024, m) for m in range(1, 13)
] + [
    (2025, m) for m in range(1, 13)
] + [
    (2026, m) for m in range(1, 4)
]


def load_price_frame() -> pl.DataFrame:
    paths = [PRICE_DIR / f"year={y:04d}" / f"month={m:02d}" / "data.parquet" for y, m in MONTHS]
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise SystemExit("No price parquet files found")
    df = pl.concat([pl.read_parquet(p) for p in existing]).sort(["pair", "timestamp_utc"])
    df = df.with_columns(pl.col("timestamp_utc").dt.cast_time_unit("ns").alias("timestamp_utc"))
    return df


def make_price_features(prices: pl.DataFrame) -> pl.DataFrame:
    return prices.with_columns(
        [
            (pl.col("close") / pl.col("close").shift(5).over("pair") - 1.0).alias("ret_prev_5m"),
            (pl.col("close") / pl.col("close").shift(15).over("pair") - 1.0).alias("ret_prev_15m"),
            (pl.col("close") / pl.col("close").shift(60).over("pair") - 1.0).alias("ret_prev_60m"),
            (pl.col("close") / pl.col("close").shift(240).over("pair") - 1.0).alias("ret_prev_240m"),
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_frac"),
        ]
    ).with_columns(
        [
            pl.col("ret_prev_5m").rolling_std(window_size=30, min_samples=10).over("pair").alias("rolling_std_5m_30"),
            pl.col("ret_prev_15m").rolling_std(window_size=30, min_samples=10).over("pair").alias("rolling_std_15m_30"),
            pl.col("bar_range_frac").rolling_mean(window_size=60, min_samples=20).over("pair").alias("avg_range_frac_60"),
            pl.col("high").rolling_max(window_size=60, min_samples=20).over("pair").alias("rolling_high_60"),
            pl.col("low").rolling_min(window_size=60, min_samples=20).over("pair").alias("rolling_low_60"),
            pl.col("close").rolling_mean(window_size=60, min_samples=20).over("pair").alias("rolling_mean_close_60"),
        ]
    ).with_columns(
        [
            ((pl.col("rolling_high_60") - pl.col("rolling_low_60")) / pl.col("close")).alias("range_width_60"),
            ((pl.col("close") - pl.col("rolling_mean_close_60")) / pl.col("close")).alias("dist_from_mean_60"),
        ]
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = pl.read_parquet(EVENTS_FILE).with_columns(
        pl.col("event_timestamp_utc").dt.cast_time_unit("ns").alias("event_timestamp_utc")
    )
    prices = make_price_features(load_price_frame())

    features = prices.select(
        [
            "pair",
            "timestamp_utc",
            "ret_prev_5m",
            "ret_prev_15m",
            "ret_prev_60m",
            "ret_prev_240m",
            "rolling_std_5m_30",
            "rolling_std_15m_30",
            "avg_range_frac_60",
            "range_width_60",
            "dist_from_mean_60",
        ]
    ).sort(["pair", "timestamp_utc"])

    joined = events.join_asof(
        features,
        left_on="event_timestamp_utc",
        right_on="timestamp_utc",
        by="pair",
        strategy="backward",
    ).rename({"timestamp_utc": "feature_bar_ts"})

    out_file = OUT_DIR / "event_risk_training_dataset_with_price_context.parquet"
    joined.write_parquet(out_file)

    summary = joined.select(
        [
            pl.len().alias("rows"),
            pl.col("ret_prev_5m").null_count().alias("null_ret_prev_5m"),
            pl.col("ret_prev_60m").null_count().alias("null_ret_prev_60m"),
            pl.col("rolling_std_5m_30").null_count().alias("null_rolling_std_5m_30"),
            pl.col("range_width_60").null_count().alias("null_range_width_60"),
        ]
    )
    summary.write_csv(OUT_DIR / "event_risk_training_dataset_with_price_context_summary.csv")

    print(summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
