from __future__ import annotations

from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
OUT_DIR = ROOT / "data" / "processed" / "session_range"
CALENDAR_FILE = ROOT / "data" / "processed" / "economic_calendar" / "events_with_session_avoidance.parquet"
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
PIP_SIZE = {
    "EURJPY": 0.01,
    "GBPJPY": 0.01,
    "GBPUSD": 0.0001,
    "NZDUSD": 0.0001,
}
SESSION_WINDOWS_NY = {
    "asia": (17, 0, 0, 59),
    "london": (3, 0, 11, 59),
    "new_york": (8, 0, 17, 0),
}
PAIR_TO_AVOID_COL = {
    "EURJPY": "avoid_session_eurjpy",
    "GBPJPY": "avoid_session_gbpjpy",
    "GBPUSD": "avoid_session_gbpusd",
    "NZDUSD": "avoid_session_nzdusd",
}


def load_prices() -> pl.DataFrame:
    paths = sorted(PRICE_DIR.glob("year=*/month=*/data.parquet"))
    if not paths:
        raise SystemExit(f"No price files found under {PRICE_DIR}")
    return (
        pl.scan_parquet([str(p) for p in paths])
        .filter(pl.col("pair").is_in(PAIRS))
        .select(["pair", "timestamp_utc", "open", "high", "low", "close"])
        .collect()
        .sort(["pair", "timestamp_utc"])
    )


def build_session_ranges(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(pl.col("timestamp_utc").dt.convert_time_zone("America/New_York").alias("ts_ny"))
    df = df.with_columns(
        [
            pl.col("ts_ny").dt.date().alias("date_ny"),
            pl.col("ts_ny").dt.hour().alias("hour_ny"),
            pl.col("ts_ny").dt.minute().alias("minute_ny"),
        ]
    )
    hm = pl.col("hour_ny").cast(pl.Int32) * 60 + pl.col("minute_ny").cast(pl.Int32)

    frames: list[pl.DataFrame] = []
    for session_name, (sh, sm, eh, em) in SESSION_WINDOWS_NY.items():
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= end:
            session_filter = (hm >= start) & (hm <= end)
        else:
            session_filter = (hm >= start) | (hm <= end)

        sess = (
            df.filter(session_filter)
            .group_by(["pair", "date_ny"])
            .agg(
                [
                    pl.col("open").first().alias("session_open"),
                    pl.col("close").last().alias("session_close"),
                    pl.col("high").max().alias("session_high"),
                    pl.col("low").min().alias("session_low"),
                ]
            )
            .with_columns(
                [
                    pl.lit(session_name).alias("session_name"),
                    ((pl.col("session_high") - pl.col("session_low")) / pl.col("pair").replace_strict(PIP_SIZE)).alias("session_range_pips"),
                    (((pl.col("session_close") - pl.col("session_open")).abs()) / pl.col("pair").replace_strict(PIP_SIZE)).alias("session_body_pips"),
                    ((pl.col("session_close") - pl.col("session_open")) / pl.col("pair").replace_strict(PIP_SIZE)).alias("session_ret_pips"),
                ]
            )
            .sort(["pair", "session_name", "date_ny"])
        )
        frames.append(sess)

    out = pl.concat(frames).sort(["pair", "session_name", "date_ny"])
    out = out.with_columns(
        [
            ((pl.col("session_high") - pl.col("session_low")) / pl.col("session_open")).alias("session_range_frac"),
            ((pl.col("session_close") - pl.col("session_open")) / pl.col("session_open")).alias("session_return_frac"),
        ]
    )
    return out.with_columns(
        [
            pl.col("session_range_pips").shift(1).over(["pair", "session_name"]).alias("lag_range_1"),
            pl.col("session_range_pips").shift(2).over(["pair", "session_name"]).alias("lag_range_2"),
            pl.col("session_range_pips").shift(3).over(["pair", "session_name"]).alias("lag_range_3"),
            pl.col("session_range_pips").rolling_mean(window_size=5, min_samples=3).shift(1).over(["pair", "session_name"]).alias("avg_range_5"),
            pl.col("session_range_pips").rolling_mean(window_size=10, min_samples=5).shift(1).over(["pair", "session_name"]).alias("avg_range_10"),
            pl.col("session_range_pips").rolling_std(window_size=10, min_samples=5).shift(1).over(["pair", "session_name"]).alias("std_range_10"),
            pl.col("session_body_pips").rolling_mean(window_size=5, min_samples=3).shift(1).over(["pair", "session_name"]).alias("avg_body_5"),
            pl.col("session_ret_pips").rolling_mean(window_size=5, min_samples=3).shift(1).over(["pair", "session_name"]).alias("avg_ret_5"),
            pl.col("session_range_frac").rolling_mean(window_size=5, min_samples=3).shift(1).over(["pair", "session_name"]).alias("avg_range_frac_5"),
            pl.col("session_return_frac").rolling_mean(window_size=5, min_samples=3).shift(1).over(["pair", "session_name"]).alias("avg_return_frac_5"),
            pl.col("date_ny").dt.weekday().alias("day_of_week"),
            pl.col("date_ny").dt.month().alias("month_num"),
        ]
    )


def add_intraday_context(dataset: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    ctx = (
        prices.with_columns(pl.col("timestamp_utc").dt.convert_time_zone("America/New_York").alias("ts_ny"))
        .with_columns([
            pl.col("ts_ny").dt.date().alias("date_ny"),
            pl.col("ts_ny").dt.hour().alias("hour_ny"),
            pl.col("ts_ny").dt.minute().alias("minute_ny"),
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_frac"),
            (pl.col("close") / pl.col("close").shift(5).over("pair") - 1.0).alias("ret_5m"),
            (pl.col("close") / pl.col("close").shift(60).over("pair") - 1.0).alias("ret_60m"),
        ])
        .with_columns([
            pl.col("ret_5m").rolling_std(window_size=30, min_samples=10).over("pair").alias("rolling_std_5m_30"),
            pl.col("bar_range_frac").rolling_mean(window_size=60, min_samples=20).over("pair").alias("avg_bar_range_frac_60"),
        ])
        .group_by(["pair", "date_ny"])
        .agg([
            pl.col("rolling_std_5m_30").last().alias("intraday_rvol_5m_30"),
            pl.col("avg_bar_range_frac_60").last().alias("intraday_avg_range_frac_60"),
            pl.col("ret_60m").last().alias("intraday_ret_60m"),
        ])
    )
    return dataset.join(ctx, on=["pair", "date_ny"], how="left")


def add_event_context(dataset: pl.DataFrame) -> pl.DataFrame:
    if not CALENDAR_FILE.exists():
        return dataset

    events = pl.read_parquet(CALENDAR_FILE).with_columns(
        pl.col("event_timestamp_utc").dt.convert_time_zone("America/New_York").alias("event_ts_ny")
    )
    events = events.with_columns([
        pl.col("event_ts_ny").dt.date().alias("event_date_ny"),
        pl.col("event_ts_ny").dt.hour().alias("event_hour_ny"),
        pl.col("event_ts_ny").dt.minute().alias("event_minute_ny"),
        (pl.col("importance_score").cast(pl.Float64) + 1.0).alias("importance_w"),
        pl.col("is_major_macro").cast(pl.Int32).alias("is_major_macro_i"),
        pl.col("is_noisy_macro").cast(pl.Int32).alias("is_noisy_macro_i"),
    ])

    frames: list[pl.DataFrame] = []
    for pair in PAIRS:
        avoid_col = PAIR_TO_AVOID_COL[pair]
        pair_events = events.filter(
            (pl.col("currency_norm").is_in([pair[:3], pair[3:]]))
            | (pl.col(avoid_col) != "none")
        )
        if pair_events.height == 0:
            continue

        agg = (
            pair_events.group_by("event_date_ny")
            .agg([
                pl.len().alias("event_count_24h"),
                pl.col("is_major_macro_i").sum().alias("major_event_count_24h"),
                pl.col("is_noisy_macro_i").sum().alias("noisy_event_count_24h"),
                pl.col("importance_score").max().alias("max_importance_24h"),
                pl.col("importance_w").sum().alias("importance_sum_24h"),
                pl.col("surprise_raw").abs().max().alias("max_abs_surprise_24h"),
                pl.col("surprise_raw").abs().mean().alias("avg_abs_surprise_24h"),
                pl.col(avoid_col).eq("asia").any().cast(pl.Int32).alias("has_avoid_asia_24h"),
                pl.col(avoid_col).eq("london").any().cast(pl.Int32).alias("has_avoid_london_24h"),
                pl.col(avoid_col).eq("both").any().cast(pl.Int32).alias("has_avoid_both_24h"),
                pl.col("event_hour_ny").filter(pl.col("event_hour_ny") < 3).len().alias("pre_london_event_count"),
                pl.col("event_hour_ny").filter((pl.col("event_hour_ny") >= 12) | (pl.col("event_hour_ny") <= 0)).len().alias("pre_asia_event_count"),
                pl.col("importance_w").filter(pl.col("event_hour_ny") < 3).sum().alias("pre_london_importance_sum"),
                pl.col("importance_w").filter((pl.col("event_hour_ny") >= 12) | (pl.col("event_hour_ny") <= 0)).sum().alias("pre_asia_importance_sum"),
            ])
            .with_columns(pl.lit(pair).alias("pair"))
            .rename({"event_date_ny": "date_ny"})
        )
        frames.append(agg)

    if not frames:
        return dataset

    event_ctx = pl.concat(frames, how="vertical_relaxed")
    out = dataset.join(event_ctx, on=["pair", "date_ny"], how="left")
    fill_zero_cols = [
        "event_count_24h",
        "major_event_count_24h",
        "noisy_event_count_24h",
        "max_importance_24h",
        "importance_sum_24h",
        "max_abs_surprise_24h",
        "avg_abs_surprise_24h",
        "has_avoid_asia_24h",
        "has_avoid_london_24h",
        "has_avoid_both_24h",
        "pre_london_event_count",
        "pre_asia_event_count",
        "pre_london_importance_sum",
        "pre_asia_importance_sum",
    ]
    return out.with_columns([pl.col(c).fill_null(0) for c in fill_zero_cols])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_prices()
    dataset = build_session_ranges(prices)
    dataset = add_intraday_context(dataset, prices)
    dataset = add_event_context(dataset)
    dataset = dataset.drop_nulls(subset=["lag_range_1", "avg_range_5", "avg_range_10"])
    dataset.write_parquet(OUT_DIR / "session_range_dataset.parquet")
    dataset.group_by(["pair", "session_name"]).len().sort(["pair", "session_name"]).write_csv(OUT_DIR / "session_range_dataset_summary.csv")
    print(dataset.select(["pair", "session_name", "date_ny", "session_range_pips", "lag_range_1", "avg_range_5"]).head(10))
    print(f"rows={dataset.height}")


if __name__ == "__main__":
    main()
