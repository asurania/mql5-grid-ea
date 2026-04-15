from __future__ import annotations

from pathlib import Path

import polars as pl
import numpy as np

PRICE_DIR = Path("data/processed/massive/fx_minute_bars")
OUT_DIR = Path("data/processed/regime")
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
MONTHS = [
    (y, m)
    for y in range(2023, 2027)
    for m in range(1, 13)
    if (y, m) <= (2026, 3)
]

# Regime labeling window
LOOKBACK = 60       # bars for computing regime features
HORIZON = 60       # bars forward for labeling realized outcome


def load_prices() -> pl.DataFrame:
    paths = [
        PRICE_DIR / f"year={y:04d}" / f"month={m:02d}" / "data.parquet"
        for y, m in MONTHS
    ]
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise SystemExit("No price files found")
    return pl.concat([pl.read_parquet(p) for p in existing]).sort(["pair", "timestamp_utc"])


def compute_regime_features(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        [
            # Returns at multiple scales
            (pl.col("close") / pl.col("close").shift(5).over("pair") - 1.0).alias("ret_5m"),
            (pl.col("close") / pl.col("close").shift(15).over("pair") - 1.0).alias("ret_15m"),
            (pl.col("close") / pl.col("close").shift(30).over("pair") - 1.0).alias("ret_30m"),
            (pl.col("close") / pl.col("close").shift(60).over("pair") - 1.0).alias("ret_60m"),
            (pl.col("close") / pl.col("close").shift(240).over("pair") - 1.0).alias("ret_240m"),
            # Range fraction
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_frac"),
        ]
    ).with_columns(
        [
            # Rolling volatility
            pl.col("ret_5m").rolling_std(window_size=20, min_samples=10).over("pair").alias("rvol_5m_20"),
            pl.col("ret_5m").rolling_std(window_size=60, min_samples=20).over("pair").alias("rvol_5m_60"),
            # Rolling range
            pl.col("bar_range_frac").rolling_mean(window_size=20, min_samples=10).over("pair").alias("avg_range_20"),
            pl.col("bar_range_frac").rolling_mean(window_size=60, min_samples=20).over("pair").alias("avg_range_60"),
            # Rolling high/low channel
            pl.col("high").rolling_max(window_size=60, min_samples=20).over("pair").alias("roll_high_60"),
            pl.col("low").rolling_min(window_size=60, min_samples=20).over("pair").alias("roll_low_60"),
            pl.col("high").rolling_max(window_size=240, min_samples=60).over("pair").alias("roll_high_240"),
            pl.col("low").rolling_min(window_size=240, min_samples=60).over("pair").alias("roll_low_240"),
            # Rolling mean
            pl.col("close").rolling_mean(window_size=60, min_samples=20).over("pair").alias("ma_60"),
            pl.col("close").rolling_mean(window_size=240, min_samples=60).over("pair").alias("ma_240"),
        ]
    ).with_columns(
        [
            # Channel width relative to price
            ((pl.col("roll_high_60") - pl.col("roll_low_60")) / pl.col("close")).alias("channel_width_60"),
            ((pl.col("roll_high_240") - pl.col("roll_low_240")) / pl.col("close")).alias("channel_width_240"),
            # Distance from moving averages
            ((pl.col("close") - pl.col("ma_60")) / pl.col("close")).alias("dist_from_ma60"),
            ((pl.col("close") - pl.col("ma_240")) / pl.col("close")).alias("dist_from_ma240"),
            # Trend consistency: how often do 5m returns have same sign over last 20 bars
            (pl.col("ret_5m").rolling_map(lambda s: (np.sign(s.to_numpy()) == np.sign(s[-1])).mean() if len(s) >= 5 else 0.0, window_size=20, min_samples=10).over("pair").alias("trend_consistency_20")),
        ]
    )


def compute_realized_outcomes(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        [
            # Forward 60-bar return (absolute)
            pl.col("close").shift(-HORIZON).over("pair").alias("close_fwd_60"),
            # Forward max adverse excursion
            pl.col("low").rolling_min(window_size=HORIZON, min_samples=HORIZON).over("pair").shift(-HORIZON).alias("fwd_min_low_60"),
            # Forward max favorable excursion
            pl.col("high").rolling_max(window_size=HORIZON, min_samples=HORIZON).over("pair").shift(-HORIZON).alias("fwd_max_high_60"),
        ]
    ).with_columns(
        [
            (pl.col("close_fwd_60") / pl.col("close") - 1.0).alias("fwd_ret_60"),
            ((pl.col("close_fwd_60") - pl.col("close")).abs() / pl.col("close")).alias("abs_fwd_ret_60"),
            ((pl.col("fwd_max_high_60") - pl.col("fwd_min_low_60")) / pl.col("close")).alias("fwd_range_60"),
        ]
    )


def label_regime(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        [
            # Trend strength: absolute forward return relative to forward range
            # If most of the 60-bar range is in one direction, it's trending
            (pl.col("abs_fwd_ret_60") / pl.col("fwd_range_60").clip(lower_bound=1e-10)).alias("trend_frac"),
        ]
    )

    # Use pair-specific quantiles for thresholding
    return df.with_columns(
        [
            # Primary label: trend vs range
            pl.when(pl.col("trend_frac") >= 0.65)
            .then(pl.lit("trend"))
            .when(pl.col("trend_frac") <= 0.30)
            .then(pl.lit("range"))
            .otherwise(pl.lit("neutral"))
            .alias("regime_label"),
        ]
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading prices...")
    prices = load_prices()

    print("Computing regime features...")
    prices = compute_regime_features(prices)

    print("Computing realized outcomes...")
    prices = compute_realized_outcomes(prices)

    print("Labeling regime...")
    prices = label_regime(prices)

    # Drop forward-looking columns for the training-safe version
    feature_cols = [
        "pair", "timestamp_utc", "close",
        "ret_5m", "ret_15m", "ret_30m", "ret_60m", "ret_240m",
        "rvol_5m_20", "rvol_5m_60",
        "avg_range_20", "avg_range_60",
        "channel_width_60", "channel_width_240",
        "dist_from_ma60", "dist_from_ma240",
        "trend_consistency_20",
        "bar_range_frac",
        "regime_label",
    ]

    out = prices.select(feature_cols).drop_nulls(subset=["regime_label"])

    # Sample: keep every 5th row to reduce size
    out = out.with_columns((pl.col("timestamp_utc").dt.epoch("s") % 300 == 0).alias("keep_sample"))
    out_sampled = out.filter(pl.col("keep_sample")).drop("keep_sample")
    # Also keep the last bar of each pair for live inference
    last_bars = out.drop("keep_sample").group_by("pair").tail(1)
    combined = pl.concat([out_sampled, last_bars]).unique(subset=["pair", "timestamp_utc"]).sort(["pair", "timestamp_utc"])

    combined.write_parquet(OUT_DIR / "fx_regime_dataset.parquet")

    summary = combined.group_by("regime_label").len().sort("regime_label")
    summary.write_csv(OUT_DIR / "fx_regime_dataset_summary.csv")

    pair_summary = combined.group_by(["pair", "regime_label"]).len().sort(["pair", "regime_label"])
    pair_summary.write_csv(OUT_DIR / "fx_regime_dataset_pair_summary.csv")

    print(summary)
    print(pair_summary)
    print(f"Total rows: {combined.height}")
    print(f"Wrote {OUT_DIR / 'fx_regime_dataset.parquet'}")


if __name__ == "__main__":
    main()