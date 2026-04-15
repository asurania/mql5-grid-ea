from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/joined/event_market_context.parquet")
OUT_DIR = Path("data/processed/joined")


def main() -> None:
    df = pl.read_parquet(IN_FILE)

    thresholds = (
        df.group_by("pair")
        .agg(
            [
                pl.col("ret_60m").abs().quantile(0.85).alias("ret60_q85"),
                pl.col("ret_180m").abs().quantile(0.85).alias("ret180_q85"),
                pl.col("ret_180m").abs().quantile(0.92).alias("ret180_q92"),
                pl.col("max_abs_ret_60m").quantile(0.85).alias("maxabs60_q85"),
                pl.col("trend_persistence_ratio").quantile(0.80).alias("trend_ratio_q80"),
                pl.col("trend_persistence_ratio").quantile(0.90).alias("trend_ratio_q90"),
            ]
        )
        .sort("pair")
    )

    relabeled = df.join(thresholds, on="pair", how="left")

    relabeled = relabeled.with_columns(
        [
            pl.when(
                (
                    (pl.col("ret_180m").abs() >= pl.col("ret180_q85"))
                    & (pl.col("trend_persistence_ratio") >= pl.col("trend_ratio_q80"))
                    & (~pl.col("sign_flip_30_180"))
                )
                |
                (
                    (pl.col("ret_180m").abs() >= pl.col("ret180_q92"))
                    & (~pl.col("sign_flip_15_60"))
                )
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("trend_danger_q"),
            pl.when(
                (
                    (pl.col("max_abs_ret_60m") >= pl.col("maxabs60_q85"))
                    & (pl.col("sign_flip_15_60") | pl.col("sign_flip_30_180"))
                )
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("whipsaw_danger_q"),
            pl.when(
                (pl.col("ret_60m").abs() >= pl.col("ret60_q85"))
                | (pl.col("ret_180m").abs() >= pl.col("ret180_q85"))
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("volatility_expansion_q"),
        ]
    )

    relabeled = relabeled.with_columns(
        [
            pl.when(
                (pl.col("avoid_session") != "none")
                | pl.col("trend_danger_q")
                | ((pl.col("ret_180m").abs() >= pl.col("ret180_q85")) & (pl.col("risk_prior") != "safe"))
            )
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias("post_news_session_risk_q")
        ]
    )

    relabeled = relabeled.with_columns(
        [
            pl.when(pl.col("trend_danger_q")).then(pl.lit("trend_danger"))
            .when(pl.col("whipsaw_danger_q")).then(pl.lit("whipsaw_danger"))
            .when(pl.col("volatility_expansion_q")).then(pl.lit("volatility_expansion"))
            .otherwise(pl.lit("normal")).alias("reaction_label_q")
        ]
    )

    out_file = OUT_DIR / "event_market_context_quantile_labeled.parquet"
    relabeled.write_parquet(out_file)

    summary = (
        relabeled.group_by(["pair", "reaction_label_q"])
        .agg(pl.len().alias("rows"))
        .sort(["pair", "reaction_label_q"])
    )
    summary.write_csv(OUT_DIR / "event_market_context_quantile_summary.csv")
    thresholds.write_csv(OUT_DIR / "event_market_context_pair_thresholds.csv")

    print(thresholds)
    print(summary)
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
