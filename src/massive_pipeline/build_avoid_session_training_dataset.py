from __future__ import annotations

from pathlib import Path

import polars as pl

FEATURE_FILE = Path("data/processed/modeling/event_risk_training_dataset_with_price_context.parquet")
JOINED_FILE = Path("data/processed/joined/event_market_context_quantile_labeled.parquet")
OUT_DIR = Path("data/processed/modeling")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    feat = pl.read_parquet(FEATURE_FILE)
    joined = pl.read_parquet(JOINED_FILE).select(
        [
            "event_id",
            "pair",
            "avoid_session",
            "importance_score",
            "trend_danger_q",
            "whipsaw_danger_q",
            "volatility_expansion_q",
            "ret_180m",
        ]
    ).with_columns(
        [
            pl.col("ret_180m").abs().alias("abs_ret_180m"),
            pl.col("importance_score").fill_null(-1).alias("importance_score_filled_joined"),
        ]
    )

    joined = joined.with_columns(
        [
            pl.when(
                (pl.col("avoid_session") != "none")
                | (
                    (pl.col("trend_danger_q") == 1)
                    & (pl.col("abs_ret_180m") >= 0.0030)
                    & (pl.col("whipsaw_danger_q") == 0)
                )
                | (
                    (pl.col("volatility_expansion_q") == 1)
                    & (pl.col("abs_ret_180m") >= 0.0040)
                    & (pl.col("importance_score_filled_joined") >= 1)
                )
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .alias("y_avoid_session")
        ]
    ).select(["event_id", "pair", "y_avoid_session"])

    df = feat.join(joined, on=["event_id", "pair"], how="left")
    df = df.with_columns(pl.col("y_avoid_session").fill_null(0).cast(pl.Int8))

    out_file = OUT_DIR / "avoid_session_training_dataset.parquet"
    df.write_parquet(out_file)

    summary = pl.DataFrame(
        {
            "target": ["y_avoid_session"],
            "positive_rows": [df.filter(pl.col("y_avoid_session") == 1).height],
            "total_rows": [df.height],
        }
    ).with_columns((pl.col("positive_rows") / pl.col("total_rows")).alias("positive_rate"))
    summary.write_csv(OUT_DIR / "avoid_session_training_dataset_summary.csv")

    pair_summary = (
        df.group_by("pair")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("y_avoid_session").mean().alias("avoid_session_rate"),
            ]
        )
        .sort("pair")
    )
    pair_summary.write_csv(OUT_DIR / "avoid_session_training_dataset_pair_summary.csv")

    print(summary)
    print(pair_summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
