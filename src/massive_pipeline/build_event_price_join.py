from __future__ import annotations

from pathlib import Path

import polars as pl

EVENTS_FILE = Path("data/processed/economic_calendar/events_with_session_avoidance.parquet")
PRICE_DIR = Path("data/processed/massive/fx_minute_bars")
OUT_DIR = Path("data/processed/joined")
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
PAIR_RISK_COLS = {
    "EURJPY": "risk_prior_eurjpy",
    "GBPJPY": "risk_prior_gbpjpy",
    "GBPUSD": "risk_prior_gbpusd",
    "NZDUSD": "risk_prior_nzdusd",
}
PAIR_SESSION_COLS = {
    "EURJPY": "avoid_session_eurjpy",
    "GBPJPY": "avoid_session_gbpjpy",
    "GBPUSD": "avoid_session_gbpusd",
    "NZDUSD": "avoid_session_nzdusd",
}
PAIR_REL_COLS = {
    "EURJPY": "rel_eurjpy",
    "GBPJPY": "rel_gbpjpy",
    "GBPUSD": "rel_gbpusd",
    "NZDUSD": "rel_nzdusd",
}
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
    return pl.concat([pl.read_parquet(p) for p in existing])


def pair_events(events: pl.DataFrame, pair: str) -> pl.DataFrame:
    return (
        events.filter(pl.col(PAIR_REL_COLS[pair]))
        .select(
            [
                pl.lit(pair).alias("pair"),
                pl.col("id").alias("event_id"),
                pl.col("event_timestamp_utc"),
                pl.col("event_name"),
                pl.col("event_category"),
                pl.col("currency_norm"),
                pl.col("importance_score"),
                pl.col(PAIR_RISK_COLS[pair]).alias("risk_prior"),
                pl.col(PAIR_SESSION_COLS[pair]).alias("avoid_session"),
            ]
        )
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events = pl.read_parquet(EVENTS_FILE)
    prices = load_price_frame()

    event_frames = [pair_events(events, pair) for pair in PAIRS]
    event_df = pl.concat(event_frames).sort(["pair", "event_timestamp_utc"])

    # Ensure join keys are sorted for asof joins.
    event_df = event_df.with_columns(
        pl.col("event_timestamp_utc").dt.cast_time_unit("ns").alias("event_ts")
    )
    prices = prices.with_columns(
        pl.col("timestamp_utc").dt.cast_time_unit("ns").alias("timestamp_utc")
    ).sort(["pair", "timestamp_utc"])

    event_with_entry = event_df.join_asof(
        prices.select(["pair", "timestamp_utc", "close"]).sort(["pair", "timestamp_utc"]),
        left_on="event_ts",
        right_on="timestamp_utc",
        by="pair",
        strategy="backward",
    ).rename({"close": "entry_close", "timestamp_utc": "entry_bar_ts"})

    horizons = [5, 15, 30, 60, 180]
    joined = event_with_entry
    for horizon in horizons:
        horizon_col = f"ts_plus_{horizon}m"
        joined = joined.with_columns(
            (pl.col("event_ts") + pl.duration(minutes=horizon)).dt.cast_time_unit("ns").alias(horizon_col)
        )
        future = joined.select(["pair", horizon_col]).rename({horizon_col: "target_ts"})
        future_prices = prices.select(["pair", "timestamp_utc", "close"]).sort(["pair", "timestamp_utc"])
        future_join = future.join_asof(
            future_prices,
            left_on="target_ts",
            right_on="timestamp_utc",
            by="pair",
            strategy="forward",
        ).rename({"close": f"close_plus_{horizon}m"})
        joined = joined.with_columns(future_join[f"close_plus_{horizon}m"])

    reaction = joined.with_columns(
        [
            ((pl.col("close_plus_5m") - pl.col("entry_close")) / pl.col("entry_close")).alias("ret_5m"),
            ((pl.col("close_plus_15m") - pl.col("entry_close")) / pl.col("entry_close")).alias("ret_15m"),
            ((pl.col("close_plus_30m") - pl.col("entry_close")) / pl.col("entry_close")).alias("ret_30m"),
            ((pl.col("close_plus_60m") - pl.col("entry_close")) / pl.col("entry_close")).alias("ret_60m"),
            ((pl.col("close_plus_180m") - pl.col("entry_close")) / pl.col("entry_close")).alias("ret_180m"),
        ]
    )

    reaction = reaction.with_columns(
        [
            pl.max_horizontal(pl.col("ret_5m").abs(), pl.col("ret_15m").abs(), pl.col("ret_30m").abs(), pl.col("ret_60m").abs()).alias("max_abs_ret_60m"),
            (pl.col("ret_180m").abs() / (pl.col("ret_5m").abs() + 1e-9)).alias("trend_persistence_ratio"),
            (pl.col("ret_15m") * pl.col("ret_60m") < 0).alias("sign_flip_15_60"),
            (pl.col("ret_30m") * pl.col("ret_180m") < 0).alias("sign_flip_30_180"),
        ]
    )

    reaction = reaction.with_columns(
        [
            pl.when((pl.col("ret_60m").abs() >= 0.0025) | (pl.col("ret_180m").abs() >= 0.0040))
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("volatility_expansion"),
            pl.when(
                ((pl.col("ret_60m").abs() >= 0.0020) & (pl.col("ret_180m").abs() >= 0.0030) & (~pl.col("sign_flip_30_180")))
                | (pl.col("trend_persistence_ratio") >= 3.0)
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("trend_danger"),
            pl.when(
                (pl.col("sign_flip_15_60") | pl.col("sign_flip_30_180"))
                & (pl.col("max_abs_ret_60m") >= 0.0015)
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("whipsaw_danger"),
        ]
    )

    reaction = reaction.with_columns(
        [
            pl.when(
                (pl.col("avoid_session") != "none")
                | (pl.col("trend_danger"))
                | ((pl.col("ret_180m").abs() >= 0.0035) & (pl.col("risk_prior") != "safe"))
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("post_news_session_risk")
        ]
    )

    reaction = reaction.with_columns(
        [
            pl.when(pl.col("trend_danger")).then(pl.lit("trend_danger"))
            .when(pl.col("whipsaw_danger")).then(pl.lit("whipsaw_danger"))
            .when(pl.col("volatility_expansion")).then(pl.lit("volatility_expansion"))
            .otherwise(pl.lit("normal")).alias("reaction_label")
        ]
    )

    out_file = OUT_DIR / "event_market_context.parquet"
    reaction.write_parquet(out_file)

    summary = (
        reaction.group_by(["pair", "reaction_label"])
        .agg(pl.len().alias("rows"))
        .sort(["pair", "reaction_label"])
    )
    summary.write_csv(OUT_DIR / "event_market_context_summary.csv")
    print(summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
