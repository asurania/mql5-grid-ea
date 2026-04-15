from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/joined/event_market_context.parquet")
OUT_DIR = Path("data/processed/joined/profile")


def write_csv(df: pl.DataFrame, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(OUT_DIR / name)


def main() -> None:
    df = pl.read_parquet(IN_FILE)

    overall = pl.DataFrame(
        {
            "metric": [
                "rows",
                "pairs",
                "events",
                "date_min",
                "date_max",
                "trend_danger_rows",
                "whipsaw_danger_rows",
                "volatility_expansion_rows",
                "post_news_session_risk_rows",
            ],
            "value": [
                str(df.height),
                str(df["pair"].n_unique()),
                str(df["event_id"].n_unique()),
                str(df["event_timestamp_utc"].min()),
                str(df["event_timestamp_utc"].max()),
                str(df.filter(pl.col("trend_danger")).height),
                str(df.filter(pl.col("whipsaw_danger")).height),
                str(df.filter(pl.col("volatility_expansion")).height),
                str(df.filter(pl.col("post_news_session_risk")).height),
            ],
        }
    )
    write_csv(overall, "overall_metrics.csv")

    label_summary = (
        df.group_by(["pair", "reaction_label"])
        .agg(pl.len().alias("rows"))
        .sort(["pair", "reaction_label"])
    )
    write_csv(label_summary, "reaction_label_summary.csv")

    risk_prior_cross = (
        df.group_by(["pair", "risk_prior", "reaction_label"])
        .agg(pl.len().alias("rows"))
        .sort(["pair", "risk_prior", "rows"], descending=[False, False, True])
    )
    write_csv(risk_prior_cross, "risk_prior_vs_reaction.csv")

    quantiles = (
        df.group_by("pair")
        .agg(
            [
                pl.col("ret_5m").abs().quantile(0.50).alias("abs_ret_5m_q50"),
                pl.col("ret_5m").abs().quantile(0.90).alias("abs_ret_5m_q90"),
                pl.col("ret_60m").abs().quantile(0.50).alias("abs_ret_60m_q50"),
                pl.col("ret_60m").abs().quantile(0.90).alias("abs_ret_60m_q90"),
                pl.col("ret_180m").abs().quantile(0.50).alias("abs_ret_180m_q50"),
                pl.col("ret_180m").abs().quantile(0.90).alias("abs_ret_180m_q90"),
                pl.col("trend_persistence_ratio").quantile(0.50).alias("trend_persistence_q50"),
                pl.col("trend_persistence_ratio").quantile(0.90).alias("trend_persistence_q90"),
                pl.col("max_abs_ret_60m").quantile(0.90).alias("max_abs_ret_60m_q90"),
            ]
        )
        .sort("pair")
    )
    write_csv(quantiles, "reaction_quantiles_by_pair.csv")

    by_category = (
        df.group_by(["pair", "event_category", "reaction_label"])
        .agg(pl.len().alias("rows"))
        .sort(["pair", "rows"], descending=[False, True])
    )
    write_csv(by_category, "reaction_by_category.csv")

    top_trend = (
        df.filter(pl.col("trend_danger"))
        .group_by(["pair", "event_category", "event_name"])
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("ret_180m").abs().mean().alias("avg_abs_ret_180m"),
                pl.col("trend_persistence_ratio").mean().alias("avg_trend_persistence"),
            ]
        )
        .sort(["rows", "avg_abs_ret_180m"], descending=[True, True])
        .head(100)
    )
    write_csv(top_trend, "top_trend_danger_events.csv")

    top_whipsaw = (
        df.filter(pl.col("whipsaw_danger"))
        .group_by(["pair", "event_category", "event_name"])
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("max_abs_ret_60m").mean().alias("avg_max_abs_ret_60m"),
            ]
        )
        .sort(["rows", "avg_max_abs_ret_60m"], descending=[True, True])
        .head(100)
    )
    write_csv(top_whipsaw, "top_whipsaw_danger_events.csv")

    suspicious = (
        df.filter((pl.col("risk_prior") == "safe") & (pl.col("reaction_label") != "normal"))
        .group_by(["pair", "event_category", "event_name", "reaction_label"])
        .agg(pl.len().alias("rows"))
        .sort("rows", descending=True)
        .head(100)
    )
    write_csv(suspicious, "safe_but_reactive_events.csv")

    print(overall)
    print(label_summary)
    print(quantiles)
    print(f"Profile written to {OUT_DIR}")


if __name__ == "__main__":
    main()
