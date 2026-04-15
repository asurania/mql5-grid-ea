from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/joined/event_market_context_quantile_labeled.parquet")
OUT_DIR = Path("data/processed/modeling")

MAJOR_CATEGORIES = ["central_bank", "inflation", "employment", "gdp", "pmi", "retail_sales"]
SECONDARY_CATEGORIES = ["trade", "housing", "sentiment", "speech"]
ALL_CATEGORIES = MAJOR_CATEGORIES + SECONDARY_CATEGORIES + ["auction", "agriculture", "other"]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(IN_FILE)

    model_df = df.with_columns(
        [
            pl.col("event_timestamp_utc").dt.year().alias("event_year"),
            pl.col("event_timestamp_utc").dt.month().alias("event_month"),
            pl.col("event_timestamp_utc").dt.weekday().alias("event_weekday"),
            pl.col("event_timestamp_utc").dt.hour().alias("event_hour"),
            pl.col("importance_score").fill_null(-1).alias("importance_score_filled"),
            (pl.col("risk_prior") == "halt").cast(pl.Int8).alias("risk_prior_halt"),
            (pl.col("risk_prior") == "reduce_risk").cast(pl.Int8).alias("risk_prior_reduce"),
            (pl.col("avoid_session") == "asia").cast(pl.Int8).alias("avoid_asia"),
            (pl.col("avoid_session") == "london").cast(pl.Int8).alias("avoid_london"),
            (pl.col("avoid_session") == "both").cast(pl.Int8).alias("avoid_both"),
            (pl.col("currency_norm") == "JPY").cast(pl.Int8).alias("is_jpy_event"),
            (pl.col("currency_norm") == "GBP").cast(pl.Int8).alias("is_gbp_event"),
            (pl.col("currency_norm") == "USD").cast(pl.Int8).alias("is_usd_event"),
            (pl.col("currency_norm") == "EUR").cast(pl.Int8).alias("is_eur_event"),
            (pl.col("currency_norm") == "NZD").cast(pl.Int8).alias("is_nzd_event"),
            (pl.col("pair").str.ends_with("JPY")).cast(pl.Int8).alias("pair_is_jpy_cross"),
            (pl.col("pair").str.starts_with("GBP")).cast(pl.Int8).alias("pair_has_gbp_base"),
            (pl.col("pair").str.ends_with("USD")).cast(pl.Int8).alias("pair_has_usd_quote"),
            pl.col("ret_5m").abs().alias("abs_ret_5m"),
            pl.col("ret_15m").abs().alias("abs_ret_15m"),
            pl.col("ret_30m").abs().alias("abs_ret_30m"),
            pl.col("ret_60m").abs().alias("abs_ret_60m"),
            pl.col("ret_180m").abs().alias("abs_ret_180m"),
        ]
    )

    category_dummies = [
        (pl.col("event_category") == cat).cast(pl.Int8).alias(f"cat_{cat}") for cat in ALL_CATEGORIES
    ]
    pair_dummies = [
        (pl.col("pair") == pair).cast(pl.Int8).alias(f"pair_{pair.lower()}")
        for pair in ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
    ]
    label_dummies = [
        pl.col("trend_danger_q").cast(pl.Int8).alias("y_trend_danger"),
        pl.col("whipsaw_danger_q").cast(pl.Int8).alias("y_whipsaw_danger"),
        pl.col("volatility_expansion_q").cast(pl.Int8).alias("y_volatility_expansion"),
        pl.col("post_news_session_risk_q").cast(pl.Int8).alias("y_post_news_session_risk"),
    ]

    model_df = model_df.with_columns(category_dummies + pair_dummies + label_dummies)

    selected = model_df.select(
        [
            "event_id",
            "pair",
            "event_timestamp_utc",
            "event_name",
            "event_category",
            "currency_norm",
            "importance_score_filled",
            "risk_prior",
            "avoid_session",
            "event_year",
            "event_month",
            "event_weekday",
            "event_hour",
            "risk_prior_halt",
            "risk_prior_reduce",
            "avoid_asia",
            "avoid_london",
            "avoid_both",
            "is_jpy_event",
            "is_gbp_event",
            "is_usd_event",
            "is_eur_event",
            "is_nzd_event",
            "pair_is_jpy_cross",
            "pair_has_gbp_base",
            "pair_has_usd_quote",
            *[f"cat_{c}" for c in ALL_CATEGORIES],
            *[f"pair_{p.lower()}" for p in ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]],
            "ret_5m",
            "ret_15m",
            "ret_30m",
            "ret_60m",
            "ret_180m",
            "abs_ret_5m",
            "abs_ret_15m",
            "abs_ret_30m",
            "abs_ret_60m",
            "abs_ret_180m",
            "max_abs_ret_60m",
            "trend_persistence_ratio",
            "sign_flip_15_60",
            "sign_flip_30_180",
            "reaction_label_q",
            "y_trend_danger",
            "y_whipsaw_danger",
            "y_volatility_expansion",
            "y_post_news_session_risk",
        ]
    )

    out_file = OUT_DIR / "event_risk_model_table.parquet"
    selected.write_parquet(out_file)

    target_summary = pl.DataFrame(
        {
            "target": [
                "y_trend_danger",
                "y_whipsaw_danger",
                "y_volatility_expansion",
                "y_post_news_session_risk",
            ],
            "positive_rows": [
                selected.filter(pl.col("y_trend_danger") == 1).height,
                selected.filter(pl.col("y_whipsaw_danger") == 1).height,
                selected.filter(pl.col("y_volatility_expansion") == 1).height,
                selected.filter(pl.col("y_post_news_session_risk") == 1).height,
            ],
            "total_rows": [selected.height] * 4,
        }
    ).with_columns((pl.col("positive_rows") / pl.col("total_rows")).alias("positive_rate"))
    target_summary.write_csv(OUT_DIR / "event_risk_model_table_target_summary.csv")

    pair_target_summary = (
        selected.group_by("pair")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("y_trend_danger").mean().alias("trend_rate"),
                pl.col("y_whipsaw_danger").mean().alias("whipsaw_rate"),
                pl.col("y_volatility_expansion").mean().alias("vol_exp_rate"),
                pl.col("y_post_news_session_risk").mean().alias("session_risk_rate"),
            ]
        )
        .sort("pair")
    )
    pair_target_summary.write_csv(OUT_DIR / "event_risk_model_table_pair_summary.csv")

    print(target_summary)
    print(pair_target_summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
