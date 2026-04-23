from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/economic_calendar/events_with_risk_prior.parquet")
OUT_DIR = Path("data/processed/economic_calendar")
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]

CALGARY_TZ = "America/Edmonton"
ASIA_START_HOUR = 16
ASIA_END_HOUR = 21
LONDON_START_HOUR = 21
LONDON_END_HOUR = 4
NEW_YORK_START_HOUR = 4
NEW_YORK_END_HOUR = 12

PAIR_CURRENCIES = {
    "EURJPY": {"EUR", "JPY"},
    "GBPJPY": {"GBP", "JPY"},
    "GBPUSD": {"GBP", "USD"},
    "NZDUSD": {"NZD", "USD"},
}

SESSION_MAJOR_CATEGORIES = {"central_bank", "inflation", "employment", "gdp", "pmi", "retail_sales"}
SESSION_AVOID_STRICT_CATEGORIES = {"central_bank", "inflation", "employment", "gdp"}


def session_label_expr() -> pl.Expr:
    local_ts = pl.col("event_timestamp_utc").dt.convert_time_zone(CALGARY_TZ)
    h = local_ts.dt.hour()
    return (
        pl.when((h >= ASIA_START_HOUR) & (h < ASIA_END_HOUR))
        .then(pl.lit("asia"))
        .when((h >= LONDON_START_HOUR) | (h < LONDON_END_HOUR))
        .then(pl.lit("london"))
        .when((h >= NEW_YORK_START_HOUR) & (h < NEW_YORK_END_HOUR))
        .then(pl.lit("new_york"))
        .otherwise(pl.lit("other"))
        .alias("event_session")
    )


def avoid_expr(pair: str) -> pl.Expr:
    pair_lc = pair.lower()
    risk_col = pl.col(f"risk_prior_{pair_lc}")
    currency = pl.col("currency_norm")
    category = pl.col("event_category")
    session = pl.col("event_session")
    importance = pl.col("importance_score").fill_null(-1)

    pair_ccy = PAIR_CURRENCIES[pair]
    is_primary = currency.is_in(sorted(pair_ccy))
    is_major = category.is_in(sorted(SESSION_MAJOR_CATEGORIES))
    is_strict = category.is_in(sorted(SESSION_AVOID_STRICT_CATEGORIES))
    is_jpy_cross = pl.lit("JPY" in pair)
    is_gbp_pair = pl.lit("GBP" in pair)

    avoid_asia = (
        (session == "asia")
        & is_primary
        & is_major
        & (
            (risk_col == "halt")
            | (is_jpy_cross & (currency == "JPY") & is_strict)
            | ((currency == "NZD") & is_strict & (importance >= 1))
            | ((currency == "USD") & (pair == "NZDUSD") & is_strict & (importance >= 1))
        )
    )

    avoid_london = (
        (session == "london")
        & is_primary
        & is_major
        & (
            (risk_col == "halt")
            | (is_gbp_pair & (currency == "GBP") & is_strict)
            | ((currency == "USD") & is_strict & (importance >= 1))
            | ((currency == "EUR") & (pair == "EURJPY") & is_strict & (importance >= 1))
        )
    )

    return (
        pl.when(avoid_asia & avoid_london)
        .then(pl.lit("both"))
        .when(avoid_asia)
        .then(pl.lit("asia"))
        .when(avoid_london)
        .then(pl.lit("london"))
        .otherwise(pl.lit("none"))
        .alias(f"avoid_session_{pair_lc}")
    )


def main() -> None:
    df = pl.read_parquet(IN_FILE)
    df = df.with_columns([session_label_expr()])
    df = df.with_columns([avoid_expr(pair) for pair in PAIRS])

    out_file = OUT_DIR / "events_with_session_avoidance.parquet"
    df.write_parquet(out_file)

    summaries = []
    for pair in PAIRS:
        pair_lc = pair.lower()
        summary = (
            df.filter(pl.col(f"avoid_session_{pair_lc}") != "none")
            .group_by([f"avoid_session_{pair_lc}", "event_session", "event_category"])
            .agg(pl.len().alias("rows"))
            .with_columns(pl.lit(pair).alias("pair"))
            .rename({f"avoid_session_{pair_lc}": "avoid_session"})
            .select(["pair", "avoid_session", "event_session", "event_category", "rows"])
            .sort(["pair", "avoid_session", "rows"], descending=[False, False, True])
        )
        summaries.append(summary)

    summary_df = pl.concat(summaries)
    summary_df.write_csv(OUT_DIR / "session_avoidance_summary.csv")

    actionable = df.filter(
        pl.any_horizontal([
            pl.col("avoid_session_eurjpy") != "none",
            pl.col("avoid_session_gbpjpy") != "none",
            pl.col("avoid_session_gbpusd") != "none",
            pl.col("avoid_session_nzdusd") != "none",
        ])
    ).sort(["event_timestamp_utc", "currency_norm", "event_name"])
    actionable.write_parquet(OUT_DIR / "session_avoidance_events.parquet")

    print(summary_df)
    print(f"Wrote {out_file}")
    print(f"Wrote {OUT_DIR / 'session_avoidance_events.parquet'}")


if __name__ == "__main__":
    main()
