from __future__ import annotations

from pathlib import Path

import polars as pl

IN_FILE = Path("data/processed/economic_calendar/events_with_risk_prior.parquet")
OUT_DIR = Path("data/processed/economic_calendar")
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]

HALT_WINDOWS = {
    "central_bank": (180, 180),
    "inflation": (90, 120),
    "employment": (90, 120),
    "gdp": (60, 90),
    "pmi": (45, 60),
    "retail_sales": (45, 60),
    "trade": (30, 30),
    "housing": (20, 20),
    "sentiment": (20, 20),
    "speech": (45, 90),
    "auction": (0, 0),
    "agriculture": (0, 0),
    "other": (15, 15),
}

REDUCE_WINDOWS = {
    "central_bank": (90, 120),
    "inflation": (45, 60),
    "employment": (45, 60),
    "gdp": (30, 45),
    "pmi": (20, 30),
    "retail_sales": (20, 30),
    "trade": (15, 15),
    "housing": (10, 10),
    "sentiment": (10, 10),
    "speech": (20, 45),
    "auction": (0, 0),
    "agriculture": (0, 0),
    "other": (10, 10),
}


def pair_multiplier(pair: str) -> float:
    if pair == "GBPJPY":
        return 1.35
    if pair in {"EURJPY", "GBPUSD"}:
        return 1.15
    return 1.0


def build_minutes_expr(mapping: dict[str, tuple[int, int]], idx: int, multiplier: float) -> pl.Expr:
    scalar_map = {k: int(v[idx] * multiplier) for k, v in mapping.items()}
    return (
        pl.col("event_category")
        .replace(scalar_map, default=scalar_map["other"])
        .cast(pl.Int64)
    )


def main() -> None:
    df = pl.read_parquet(IN_FILE)
    outputs = []
    summaries = []

    for pair in PAIRS:
        pair_lc = pair.lower()
        risk_col = f"risk_prior_{pair_lc}"
        mul = pair_multiplier(pair)
        halt_pre = build_minutes_expr(HALT_WINDOWS, 0, mul)
        halt_post = build_minutes_expr(HALT_WINDOWS, 1, mul)
        reduce_pre = build_minutes_expr(REDUCE_WINDOWS, 0, mul)
        reduce_post = build_minutes_expr(REDUCE_WINDOWS, 1, mul)

        window_df = (
            df.select(
                [
                    pl.lit(pair).alias("pair"),
                    pl.col("id"),
                    pl.col("event_timestamp_utc"),
                    pl.col("country_code"),
                    pl.col("currency_norm"),
                    pl.col("event_name"),
                    pl.col("event_category"),
                    pl.col("importance_score"),
                    pl.col(risk_col).alias("risk_prior"),
                    pl.when(pl.col(risk_col) == "halt")
                    .then(pl.col("event_timestamp_utc") - pl.duration(minutes=halt_pre))
                    .when(pl.col(risk_col) == "reduce_risk")
                    .then(pl.col("event_timestamp_utc") - pl.duration(minutes=reduce_pre))
                    .otherwise(pl.col("event_timestamp_utc"))
                    .alias("window_start_utc"),
                    pl.when(pl.col(risk_col) == "halt")
                    .then(pl.col("event_timestamp_utc") + pl.duration(minutes=halt_post))
                    .when(pl.col(risk_col) == "reduce_risk")
                    .then(pl.col("event_timestamp_utc") + pl.duration(minutes=reduce_post))
                    .otherwise(pl.col("event_timestamp_utc"))
                    .alias("window_end_utc"),
                    pl.when(pl.col(risk_col) == "halt")
                    .then(halt_pre)
                    .when(pl.col(risk_col) == "reduce_risk")
                    .then(reduce_pre)
                    .otherwise(pl.lit(0))
                    .alias("pre_event_minutes"),
                    pl.when(pl.col(risk_col) == "halt")
                    .then(halt_post)
                    .when(pl.col(risk_col) == "reduce_risk")
                    .then(reduce_post)
                    .otherwise(pl.lit(0))
                    .alias("post_event_minutes"),
                ]
            )
            .filter(pl.col("risk_prior") != "safe")
        )

        outputs.append(window_df)
        summary = (
            window_df.group_by(["pair", "risk_prior", "event_category"])
            .agg(pl.len().alias("rows"))
            .sort(["pair", "risk_prior", "rows"], descending=[False, False, True])
        )
        summaries.append(summary)

    all_windows = pl.concat(outputs).sort(["pair", "window_start_utc", "event_timestamp_utc"])
    all_windows.write_parquet(OUT_DIR / "event_windows.parquet")

    summary_df = pl.concat(summaries)
    summary_df.write_csv(OUT_DIR / "event_window_summary.csv")

    print(summary_df)
    print(f"Wrote {OUT_DIR / 'event_windows.parquet'}")
    print(f"Wrote {OUT_DIR / 'event_window_summary.csv'}")


if __name__ == "__main__":
    main()
