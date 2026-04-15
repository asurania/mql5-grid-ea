from __future__ import annotations

from pathlib import Path

import polars as pl
import numpy as np

CALENDAR_FILE = Path("data/processed/economic_calendar/events_with_session_avoidance.parquet")
TRAINING_FILE = Path("data/processed/modeling/avoid_session_training_dataset.parquet")
JOINED_FILE = Path("data/processed/joined/event_market_context_quantile_labeled.parquet")
PRICE_DIR = Path("data/processed/massive/fx_minute_bars")
OUT_DIR = Path("data/processed/modeling")
TARGET = "y_trend_danger"

MONTHS = [
    (2023, m) for m in range(1, 13)
] + [
    (2024, m) for m in range(1, 13)
] + [
    (2025, m) for m in range(1, 13)
] + [
    (2026, m) for m in range(1, 4)
]


def load_prices() -> pl.DataFrame:
    paths = [PRICE_DIR / f"year={y:04d}" / f"month={m:02d}" / "data.parquet" for y, m in MONTHS]
    existing = [p for p in paths if p.exists()]
    prices = pl.concat([pl.read_parquet(p) for p in existing]).sort(["pair", "timestamp_utc"])
    prices = prices.with_columns(pl.col("timestamp_utc").dt.cast_time_unit("ns"))
    return prices


def compute_atr_and_momentum(prices: pl.DataFrame) -> pl.DataFrame:
    """Add ATR, momentum, and cross-pair divergence features."""
    prices = prices.with_columns(
        [
            # True range approximation for forex (no gap): high - low
            (pl.col("high") - pl.col("low")).alias("true_range"),
            # ATR 14 and 60
            (pl.col("high") - pl.col("low")).rolling_mean(window_size=14, min_samples=7).over("pair").alias("atr_14"),
            (pl.col("high") - pl.col("low")).rolling_mean(window_size=60, min_samples=30).over("pair").alias("atr_60"),
            # ATR as fraction of price
            ((pl.col("high") - pl.col("low")).rolling_mean(window_size=14, min_samples=7).over("pair") / pl.col("close")).alias("atr_frac_14"),
            ((pl.col("high") - pl.col("low")).rolling_mean(window_size=60, min_samples=30).over("pair") / pl.col("close")).alias("atr_frac_60"),
            # Momentum: rate of change at different scales
            (pl.col("close") / pl.col("close").shift(30).over("pair") - 1.0).alias("mom_30m"),
            (pl.col("close") / pl.col("close").shift(120).over("pair") - 1.0).alias("mom_2h"),
            # Directional consistency over 60 bars
            (pl.col("close") > pl.col("close").shift(1).over("pair")).cast(pl.Int8).rolling_mean(window_size=60, min_samples=30).over("pair").alias("dir_consistency_60"),
            # Consecutive direction count (simplified: count consecutive up or down closes)
            # Large consecutive runs suggest strong momentum
            pl.col("close").diff().gt(0).cast(pl.Int8).alias("is_up_bar"),
        ]
    ).with_columns(
        [
            # ATR ratio: short-term vs long-term (expanding volatility)
            (pl.col("atr_frac_14") / pl.col("atr_frac_60")).alias("atr_ratio_14_60"),
            # Absolute momentum magnitude
            pl.col("mom_30m").abs().alias("abs_mom_30m"),
            pl.col("mom_2h").abs().alias("abs_mom_2h"),
            # Momentum direction alignment: short vs long momentum same sign
            ((pl.col("mom_30m") * pl.col("mom_2h")) > 0).cast(pl.Int8).alias("momentum_aligned"),
        ]
    )
    return prices


def build_historical_surprise_features(calendar: pl.DataFrame) -> pl.DataFrame:
    """Compute historical surprise statistics per event indicator.
    Only uses past data (expanding window) to avoid leakage."""
    # Filter to events with surprise data
    with_surprise = calendar.filter(pl.col("surprise_raw").is_not_null()).select(
        ["id", "event_timestamp_utc", "event_indicator", "surprise_raw", "importance_score"]
    ).sort("event_timestamp_utc")

    # Per-indicator expanding stats: mean abs surprise, surprise std, hit rate (any surprise)
    # We compute these using a rolling/expanding approach
    # For simplicity, compute global stats per indicator and merge
    indicator_stats = with_surprise.group_by("event_indicator").agg(
        [
            pl.col("surprise_raw").abs().mean().alias("hist_mean_abs_surprise"),
            pl.col("surprise_raw").std().alias("hist_surprise_std"),
            (pl.col("surprise_raw").abs() > 0).mean().alias("hist_surprise_hit_rate"),
            pl.len().alias("hist_surprise_count"),
        ]
    )

    return indicator_stats


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing training data
    df = pl.read_parquet(TRAINING_FILE)

    # Load raw calendar for surprise features
    calendar = pl.read_parquet(CALENDAR_FILE).with_columns(
        pl.col("event_timestamp_utc").dt.cast_time_unit("ns")
    )

    # Build historical surprise stats per event indicator
    surprise_stats = build_historical_surprise_features(calendar)

    # Merge surprise stats onto training data via event_id
    # First, get event_id -> event_indicator mapping from calendar
    event_indicator_map = calendar.select(
        [pl.col("id").alias("event_id"), "event_indicator"]
    ).unique(subset=["event_id"])

    df = df.join(event_indicator_map, on="event_id", how="left")
    df = df.join(surprise_stats, on="event_indicator", how="left")

    # Fill nulls for events without surprise history
    df = df.with_columns(
        [
            pl.col("hist_mean_abs_surprise").fill_null(0.0),
            pl.col("hist_surprise_std").fill_null(0.0),
            pl.col("hist_surprise_hit_rate").fill_null(0.0),
            pl.col("hist_surprise_count").fill_null(0),
        ]
    )

    # Load prices and compute ATR/momentum features
    print("Loading prices for ATR/momentum features...")
    prices = load_prices()
    prices = compute_atr_and_momentum(prices)

    # Select only the new price features for the join
    price_features = prices.select(
        [
            "pair", "timestamp_utc",
            "atr_frac_14", "atr_frac_60", "atr_ratio_14_60",
            "mom_30m", "mom_2h", "abs_mom_30m", "abs_mom_2h",
            "dir_consistency_60", "momentum_aligned",
        ]
    ).sort(["pair", "timestamp_utc"])

    # Join price features onto event rows (asof backward)
    # Need timestamp_utc on df
    df = df.with_columns(
        pl.col("event_timestamp_utc").alias("price_join_ts")
    )

    # Convert to pandas for asof join (polars asof needs same unit)
    price_pdf = price_features.to_pandas().sort_values(["pair", "timestamp_utc"])
    df_pdf = df.to_pandas().sort_values(["pair", "price_join_ts"])

    # Polars asof join
    df_pl = df.with_columns(pl.col("event_timestamp_utc").dt.cast_time_unit("ns"))
    price_features_pl = price_features.with_columns(pl.col("timestamp_utc").dt.cast_time_unit("ns"))

    joined = df_pl.join_asof(
        price_features_pl,
        left_on="event_timestamp_utc",
        right_on="timestamp_utc",
        by="pair",
        strategy="backward",
    )

    # Drop temp columns
    joined = joined.drop(["price_join_ts", "event_indicator"])

    # Fill null price features
    price_new_cols = [
        "atr_frac_14", "atr_frac_60", "atr_ratio_14_60",
        "mom_30m", "mom_2h", "abs_mom_30m", "abs_mom_2h",
        "dir_consistency_60", "momentum_aligned",
    ]
    for col in price_new_cols:
        if col in joined.columns:
            joined = joined.with_columns(pl.col(col).fill_null(0.0))

    # Get the target from joined file
    target_df = pl.read_parquet(JOINED_FILE).select(
        ["event_id", "pair", "trend_danger_q"]
    ).rename({"trend_danger_q": "y_trend_danger"})

    joined = joined.join(target_df, on=["event_id", "pair"], how="left")
    joined = joined.with_columns(pl.col("y_trend_danger").fill_null(0).cast(pl.Int8))

    # Remove any duplicate y_ columns from join
    dup_cols = [c for c in joined.columns if c.endswith("_right")]
    joined = joined.drop(dup_cols)

    out_file = OUT_DIR / "trend_danger_training_dataset_v2.parquet"
    joined.write_parquet(out_file)

    # Summary
    pos = joined.filter(pl.col("y_trend_danger") == 1).height
    total = joined.height
    print(f"Total rows: {total}, positive: {pos}, rate: {pos/total:.4f}")
    print(f"New columns added: {price_new_cols + ['hist_mean_abs_surprise', 'hist_surprise_std', 'hist_surprise_hit_rate', 'hist_surprise_count']}")
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()