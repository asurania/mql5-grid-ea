from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/economic_calendar/events.parquet")
OUT_DIR = Path("data/processed/economic_calendar/profile")


def write_csv(df: pl.DataFrame, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(OUT_DIR / name)


def main() -> None:
    df = pl.read_parquet(IN_FILE)

    overall = pl.DataFrame(
        {
            "metric": [
                "rows",
                "unique_event_names",
                "unique_event_ids",
                "date_min",
                "date_max",
                "null_actual_num",
                "null_forecast_num",
                "null_previous_num",
                "surprise_non_null",
            ],
            "value": [
                str(df.height),
                str(df["event_name"].n_unique()),
                str(df["id"].n_unique()),
                str(df["event_timestamp_utc"].min()),
                str(df["event_timestamp_utc"].max()),
                str(df.filter(pl.col("actual_num").is_null()).height),
                str(df.filter(pl.col("forecast_num").is_null()).height),
                str(df.filter(pl.col("previous_num").is_null()).height),
                str(df.filter(pl.col("surprise_raw").is_not_null()).height),
            ],
        }
    )
    write_csv(overall, "overall_metrics.csv")

    by_currency = (
        df.group_by("currency_norm")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("event_name").n_unique().alias("unique_events"),
                pl.col("importance_score").mean().alias("avg_importance"),
            ]
        )
        .sort("rows", descending=True)
    )
    write_csv(by_currency, "by_currency.csv")

    by_country = (
        df.group_by("country_code")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("event_name").n_unique().alias("unique_events"),
                pl.col("currency_norm").n_unique().alias("currency_count"),
            ]
        )
        .sort("rows", descending=True)
    )
    write_csv(by_country, "by_country.csv")

    by_importance = (
        df.group_by(["importance_score", "importance_label"])
        .agg(pl.len().alias("rows"))
        .sort("importance_score")
    )
    write_csv(by_importance, "by_importance.csv")

    top_events = (
        df.group_by(["event_name", "currency_norm", "importance_label"])
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("forecast_num").is_not_null().sum().alias("forecast_non_null"),
                pl.col("actual_num").is_not_null().sum().alias("actual_non_null"),
                pl.col("previous_num").is_not_null().sum().alias("previous_non_null"),
            ]
        )
        .sort(["rows", "forecast_non_null"], descending=[True, True])
        .head(100)
    )
    write_csv(top_events, "top_events.csv")

    top_high_events = (
        df.filter(pl.col("importance_label") == "high")
        .group_by(["event_name", "currency_norm"])
        .agg(pl.len().alias("rows"))
        .sort("rows", descending=True)
        .head(100)
    )
    write_csv(top_high_events, "top_high_events.csv")

    missingness = pl.DataFrame(
        {
            "field": ["actual_num", "forecast_num", "previous_num", "source", "comment", "unit"],
            "null_rows": [
                df.filter(pl.col("actual_num").is_null()).height,
                df.filter(pl.col("forecast_num").is_null()).height,
                df.filter(pl.col("previous_num").is_null()).height,
                df.filter(pl.col("source").is_null() | (pl.col("source") == "")).height,
                df.filter(pl.col("comment").is_null() | (pl.col("comment") == "")).height,
                df.filter(pl.col("unit").is_null() | (pl.col("unit") == "")).height,
            ],
        }
    ).with_columns((pl.col("null_rows") / df.height).alias("null_ratio"))
    write_csv(missingness, "missingness.csv")

    monthly = (
        df.group_by(["year", "month", "currency_norm"])
        .agg(pl.len().alias("rows"))
        .sort(["year", "month", "currency_norm"])
    )
    write_csv(monthly, "monthly_currency_counts.csv")

    pair_relevance = pl.DataFrame(
        {
            "pair": ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"],
            "relevant_rows": [
                df.filter(pl.col("rel_eurjpy")).height,
                df.filter(pl.col("rel_gbpjpy")).height,
                df.filter(pl.col("rel_gbpusd")).height,
                df.filter(pl.col("rel_nzdusd")).height,
            ],
        }
    ).with_columns((pl.col("relevant_rows") / df.height).alias("share_of_total"))
    write_csv(pair_relevance, "pair_relevance.csv")

    print(overall)
    print(by_currency)
    print(by_importance)
    print(missingness)
    print(pair_relevance)
    print(f"Profile written to {OUT_DIR}")


if __name__ == "__main__":
    main()
