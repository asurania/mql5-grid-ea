from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/economic_calendar/events.parquet")
OUT_DIR = Path("data/processed/economic_calendar")

PAIR_RULES = {
    "EURJPY": {"primary": {"EUR", "JPY"}, "jpy_cross": True, "gbp_pair": False, "usd_pair": False},
    "GBPJPY": {"primary": {"GBP", "JPY"}, "jpy_cross": True, "gbp_pair": True, "usd_pair": False},
    "GBPUSD": {"primary": {"GBP", "USD"}, "jpy_cross": False, "gbp_pair": True, "usd_pair": True},
    "NZDUSD": {"primary": {"NZD", "USD"}, "jpy_cross": False, "gbp_pair": False, "usd_pair": True},
}

CATEGORY_RULES = [
    ("central_bank", ["rate decision", "interest rate", "boj", "boe", "ecb", "fomc", "fed chair", "governor", "minutes", "monetary policy"]),
    ("inflation", ["cpi", "inflation", "ppi", "core pce", "pce", "price index"]),
    ("employment", ["nonfarm", "nfp", "payroll", "employment", "jobless", "unemployment", "claim", "earnings", "labor"]),
    ("gdp", ["gdp", "gross domestic product"]),
    ("pmi", ["pmi", "ism", "manufacturing", "services", "composite", "business outlook"]),
    ("retail_sales", ["retail sales", "consumer spending"]),
    ("trade", ["trade balance", "current account", "imports", "exports"]),
    ("housing", ["house price", "housing", "building permits", "housing starts"]),
    ("auction", ["bill auc", "bond auction", "auction", "btc*", "hap*", "hr*", "ta*"]),
    ("agriculture", ["soybean", "corn", "wheat", "crop", "bean oil", "soy crush"]),
    ("sentiment", ["confidence", "sentiment", "expectations"]),
    ("speech", ["speech", "testimony", "remarks"]),
]

MAJOR_CATEGORIES = {"central_bank", "inflation", "employment", "gdp", "pmi", "retail_sales"}
NOISY_CATEGORIES = {"auction", "agriculture"}


def category_expr() -> pl.Expr:
    expr = pl.lit("other")
    title = pl.col("event_name").fill_null("").str.to_lowercase()
    indicator = pl.col("event_indicator").fill_null("").str.to_lowercase()
    combined = pl.concat_str([title, pl.lit(" "), indicator])
    for category, patterns in CATEGORY_RULES:
        pattern = "|".join(pl.Series(patterns).to_list())
        expr = pl.when(combined.str.contains(pattern, literal=False)).then(pl.lit(category)).otherwise(expr)
    return expr.alias("event_category")


def risk_for_pair_expr(pair: str) -> pl.Expr:
    pair_cfg = PAIR_RULES[pair]
    pair_lc = pair.lower()
    rel_col = pl.col(f"rel_{pair_lc}")
    currency = pl.col("currency_norm")
    importance = pl.col("importance_score").fill_null(-1)
    category = pl.col("event_category")

    is_primary = rel_col
    is_major = category.is_in(sorted(MAJOR_CATEGORIES))
    is_noisy = category.is_in(sorted(NOISY_CATEGORIES))
    is_jpy = currency == "JPY"
    is_gbp = currency == "GBP"
    is_usd = currency == "USD"
    is_medium_or_high = importance >= 1
    is_high = importance >= 2

    halt_condition = (
        is_primary
        & (
            (is_major & is_high)
            | (is_jpy & pl.lit(pair_cfg["jpy_cross"]) & is_major)
            | (is_gbp & pl.lit(pair_cfg["gbp_pair"]) & is_major)
            | (category == pl.lit("central_bank"))
        )
    )

    caution_condition = (
        is_primary
        & ~halt_condition
        & (
            (is_major & (importance >= 0))
            | (is_jpy & pl.lit(pair_cfg["jpy_cross"]))
            | (is_gbp & pl.lit(pair_cfg["gbp_pair"]))
            | (is_usd & pl.lit(pair_cfg["usd_pair"]) & is_medium_or_high)
            | ((category == pl.lit("speech")) & (importance >= 0))
        )
    )

    return (
        pl.when(~is_primary)
        .then(pl.lit("safe"))
        .when(is_noisy & (importance <= 0))
        .then(pl.lit("safe"))
        .when(halt_condition)
        .then(pl.lit("halt"))
        .when(caution_condition)
        .then(pl.lit("reduce_risk"))
        .otherwise(pl.lit("safe"))
        .alias(f"risk_prior_{pair_lc}")
    )


def main() -> None:
    df = pl.read_parquet(IN_FILE)

    df = df.with_columns([category_expr()])
    df = df.with_columns(
        [
            pl.col("event_category").is_in(sorted(MAJOR_CATEGORIES)).alias("is_major_macro"),
            pl.col("event_category").is_in(sorted(NOISY_CATEGORIES)).alias("is_noisy_macro"),
        ]
    )

    risk_cols = [risk_for_pair_expr(pair) for pair in PAIR_RULES]
    df = df.with_columns(risk_cols)

    out_file = OUT_DIR / "events_with_risk_prior.parquet"
    df.write_parquet(out_file)

    summary_frames = []
    for pair in PAIR_RULES:
        pair_lc = pair.lower()
        summary = (
            df.group_by(f"risk_prior_{pair_lc}")
            .agg(pl.len().alias("rows"))
            .with_columns(pl.lit(pair).alias("pair"))
            .select(["pair", f"risk_prior_{pair_lc}", "rows"])
            .rename({f"risk_prior_{pair_lc}": "risk_prior"})
        )
        summary_frames.append(summary)
    risk_summary = pl.concat(summary_frames).sort(["pair", "risk_prior"])
    risk_summary.write_csv(OUT_DIR / "risk_prior_summary.csv")

    major_events = (
        df.filter(pl.col("is_major_macro") | pl.any_horizontal([pl.col(c).eq("halt") | pl.col(c).eq("reduce_risk") for c in [
            "risk_prior_eurjpy", "risk_prior_gbpjpy", "risk_prior_gbpusd", "risk_prior_nzdusd"
        ]]))
        .sort(["event_timestamp_utc", "currency_norm", "event_name"])
    )
    major_events.write_parquet(OUT_DIR / "major_or_risky_events.parquet")

    print(risk_summary)
    print(f"Wrote {out_file}")
    print(f"Wrote {OUT_DIR / 'major_or_risky_events.parquet'}")


if __name__ == "__main__":
    main()
