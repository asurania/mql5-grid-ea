from __future__ import annotations

from pathlib import Path

import polars as pl

FEATURE_FILE = Path("data/processed/modeling/event_risk_training_dataset_with_price_context.parquet")
JOINED_FILE = Path("data/processed/joined/event_market_context_quantile_labeled.parquet")
OUT_DIR = Path("data/processed/modeling")
TARGET = "y_trend_danger"
DROP_COLUMNS = {
    "event_id",
    "event_timestamp_utc",
    "feature_bar_ts",
    "event_name",
    "event_category",
    "currency_norm",
    "risk_prior",
    "avoid_session",
    "y_trend_danger",
    "y_whipsaw_danger",
    "y_volatility_expansion",
    "y_post_news_session_risk",
    "y_avoid_session",
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    feat = pl.read_parquet(FEATURE_FILE)
    joined = pl.read_parquet(JOINED_FILE).select(
        [
            "event_id",
            "pair",
            "trend_danger_q",
        ]
    ).rename({"trend_danger_q": "y_trend_danger"})

    df = feat.join(joined, on=["event_id", "pair"], how="left")
    df = df.with_columns(pl.col("y_trend_danger").fill_null(0).cast(pl.Int8))

    out_file = OUT_DIR / "trend_danger_training_dataset.parquet"
    df.write_parquet(out_file)

    summary = pl.DataFrame(
        {
            "target": ["y_trend_danger"],
            "positive_rows": [df.filter(pl.col("y_trend_danger") == 1).height],
            "total_rows": [df.height],
        }
    ).with_columns((pl.col("positive_rows") / pl.col("total_rows")).alias("positive_rate"))
    summary.write_csv(OUT_DIR / "trend_danger_training_dataset_summary.csv")

    pair_summary = (
        df.group_by("pair")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("y_trend_danger").mean().alias("trend_danger_rate"),
            ]
        )
        .sort("pair")
    )
    pair_summary.write_csv(OUT_DIR / "trend_danger_training_dataset_pair_summary.csv")

    print(summary)
    print(pair_summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()