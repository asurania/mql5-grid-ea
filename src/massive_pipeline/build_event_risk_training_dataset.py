from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/modeling/event_risk_model_table.parquet")
OUT_DIR = Path("data/processed/modeling")

SAFE_FEATURE_COLUMNS = [
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
    "cat_central_bank",
    "cat_inflation",
    "cat_employment",
    "cat_gdp",
    "cat_pmi",
    "cat_retail_sales",
    "cat_trade",
    "cat_housing",
    "cat_sentiment",
    "cat_speech",
    "cat_auction",
    "cat_agriculture",
    "cat_other",
    "pair_eurjpy",
    "pair_gbpjpy",
    "pair_gbpusd",
    "pair_nzdusd",
    "y_trend_danger",
    "y_whipsaw_danger",
    "y_volatility_expansion",
    "y_post_news_session_risk",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(IN_FILE)
    train_df = df.select(SAFE_FEATURE_COLUMNS).sort(["event_timestamp_utc", "pair", "event_id"])

    out_file = OUT_DIR / "event_risk_training_dataset.parquet"
    train_df.write_parquet(out_file)

    feature_columns = [
        c for c in train_df.columns if c not in {
            "event_id",
            "pair",
            "event_timestamp_utc",
            "event_name",
            "event_category",
            "currency_norm",
            "risk_prior",
            "avoid_session",
            "y_trend_danger",
            "y_whipsaw_danger",
            "y_volatility_expansion",
            "y_post_news_session_risk",
        }
    ]

    metadata = pl.DataFrame(
        {
            "kind": ["feature"] * len(feature_columns)
            + ["target"] * 4,
            "column": feature_columns
            + [
                "y_trend_danger",
                "y_whipsaw_danger",
                "y_volatility_expansion",
                "y_post_news_session_risk",
            ],
        }
    )
    metadata.write_csv(OUT_DIR / "event_risk_training_dataset_columns.csv")

    target_summary = pl.DataFrame(
        {
            "target": [
                "y_trend_danger",
                "y_whipsaw_danger",
                "y_volatility_expansion",
                "y_post_news_session_risk",
            ],
            "positive_rows": [
                train_df.filter(pl.col("y_trend_danger") == 1).height,
                train_df.filter(pl.col("y_whipsaw_danger") == 1).height,
                train_df.filter(pl.col("y_volatility_expansion") == 1).height,
                train_df.filter(pl.col("y_post_news_session_risk") == 1).height,
            ],
            "total_rows": [train_df.height] * 4,
        }
    ).with_columns((pl.col("positive_rows") / pl.col("total_rows")).alias("positive_rate"))
    target_summary.write_csv(OUT_DIR / "event_risk_training_dataset_target_summary.csv")

    print(metadata)
    print(target_summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
