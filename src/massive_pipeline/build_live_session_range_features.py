from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import json
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
CALENDAR_FILE = ROOT / "data" / "processed" / "economic_calendar" / "events_with_session_avoidance.parquet"
OUT_FILE = ROOT / "data" / "live" / "policy" / "session_range_features.json"
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


def infer_session_name(now_utc: datetime) -> str:
    ny = now_utc.astimezone(timezone(timedelta(hours=-4)))
    hm = ny.hour * 60 + ny.minute
    for session_name, (start_h, start_m, end_h, end_m) in SESSION_WINDOWS_NY.items():
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start <= end:
            if start <= hm <= end:
                return session_name
        else:
            if hm >= start or hm <= end:
                return session_name
    return "new_york"


def load_recent_sessions() -> pl.DataFrame:
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


def build_features(now_utc: datetime) -> list[dict]:
    df = load_recent_sessions()
    df = df.with_columns(pl.col("timestamp_utc").dt.convert_time_zone("America/New_York").alias("ts_ny"))
    df = df.with_columns([
        pl.col("ts_ny").dt.date().alias("date_ny"),
        pl.col("ts_ny").dt.hour().alias("hour_ny"),
        pl.col("ts_ny").dt.minute().alias("minute_ny"),
    ])

    session_name = infer_session_name(now_utc)
    sh, sm, eh, em = SESSION_WINDOWS_NY[session_name]
    start = sh * 60 + sm
    end = eh * 60 + em
    hm = pl.col("hour_ny").cast(pl.Int32) * 60 + pl.col("minute_ny").cast(pl.Int32)
    if start <= end:
        session_filter = (hm >= start) & (hm <= end)
    else:
        session_filter = (hm >= start) | (hm <= end)

    sess = (
        df.filter(session_filter)
        .group_by(["pair", "date_ny"])
        .agg([
            pl.col("open").first().alias("session_open"),
            pl.col("close").last().alias("session_close"),
            pl.col("high").max().alias("session_high"),
            pl.col("low").min().alias("session_low"),
        ])
        .with_columns([
            pl.lit(session_name).alias("session_name"),
            ((pl.col("session_high") - pl.col("session_low")) / pl.col("pair").replace_strict(PIP_SIZE)).alias("session_range_pips"),
            (((pl.col("session_close") - pl.col("session_open")).abs()) / pl.col("pair").replace_strict(PIP_SIZE)).alias("session_body_pips"),
            ((pl.col("session_close") - pl.col("session_open")) / pl.col("pair").replace_strict(PIP_SIZE)).alias("session_ret_pips"),
            ((pl.col("session_high") - pl.col("session_low")) / pl.col("session_open")).alias("session_range_frac"),
            ((pl.col("session_close") - pl.col("session_open")) / pl.col("session_open")).alias("session_return_frac"),
        ])
        .sort(["pair", "date_ny"])
        .with_columns([
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
        ])
    )

    intraday = (
        df.with_columns([
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
    sess = sess.join(intraday, on=["pair", "date_ny"], how="left")
    sess = add_live_event_context(sess, now_utc)

    latest = sess.group_by(["pair", "session_name"]).tail(1).sort(["pair", "session_name"])
    return latest.to_dicts()


def add_live_event_context(sess: pl.DataFrame, now_utc: datetime) -> pl.DataFrame:
    if not CALENDAR_FILE.exists() or sess.height == 0:
        return sess

    now_ny = now_utc.astimezone(timezone(timedelta(hours=-4)))
    today_ny = now_ny.date()

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

    rows = []
    for pair in PAIRS:
        avoid_col = PAIR_TO_AVOID_COL[pair]
        pair_events = events.filter(
            ((pl.col("currency_norm").is_in([pair[:3], pair[3:]])) | (pl.col(avoid_col) != "none"))
            & (pl.col("event_date_ny") == pl.lit(today_ny))
        )

        if pair_events.height == 0:
            rows.append({
                "pair": pair,
                "date_ny": today_ny,
                "event_count_24h": 0,
                "major_event_count_24h": 0,
                "noisy_event_count_24h": 0,
                "max_importance_24h": 0,
                "importance_sum_24h": 0.0,
                "max_abs_surprise_24h": 0.0,
                "avg_abs_surprise_24h": 0.0,
                "has_avoid_asia_24h": 0,
                "has_avoid_london_24h": 0,
                "has_avoid_both_24h": 0,
                "pre_london_event_count": 0,
                "pre_asia_event_count": 0,
                "pre_london_importance_sum": 0.0,
                "pre_asia_importance_sum": 0.0,
            })
            continue

        row = pair_events.select([
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
        ]).to_dicts()[0]
        row.update({"pair": pair, "date_ny": today_ny})
        rows.append(row)

    ctx = pl.DataFrame(rows).with_columns([
        pl.col("max_importance_24h").fill_null(0),
        pl.col("importance_sum_24h").fill_null(0.0),
        pl.col("max_abs_surprise_24h").fill_null(0.0),
        pl.col("avg_abs_surprise_24h").fill_null(0.0),
        pl.col("pre_london_importance_sum").fill_null(0.0),
        pl.col("pre_asia_importance_sum").fill_null(0.0),
    ])
    out = sess.join(ctx, on=["pair", "date_ny"], how="left")
    fill_zero_int = [
        "event_count_24h",
        "major_event_count_24h",
        "noisy_event_count_24h",
        "max_importance_24h",
        "has_avoid_asia_24h",
        "has_avoid_london_24h",
        "has_avoid_both_24h",
        "pre_london_event_count",
        "pre_asia_event_count",
    ]
    fill_zero_float = [
        "importance_sum_24h",
        "max_abs_surprise_24h",
        "avg_abs_surprise_24h",
        "pre_london_importance_sum",
        "pre_asia_importance_sum",
    ]
    return out.with_columns(
        [pl.col(c).cast(pl.Int64).fill_null(0) for c in fill_zero_int]
        + [pl.col(c).cast(pl.Float64).fill_null(0.0) for c in fill_zero_float]
    )


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    rows = build_features(now_utc)
    payload = {
        "generated_at_utc": now_utc.isoformat(),
        "session_name": infer_session_name(now_utc),
        "pairs": rows,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
