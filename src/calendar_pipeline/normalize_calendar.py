from __future__ import annotations

import json
from pathlib import Path

import polars as pl

RAW_DIR = Path("data/raw/economic_calendar")
OUT_DIR = Path("data/processed/economic_calendar")
PAIR_MAP = {
    "EURJPY": {"EUR", "JPY"},
    "GBPJPY": {"GBP", "JPY"},
    "GBPUSD": {"GBP", "USD"},
    "NZDUSD": {"NZD", "USD"},
}
CURRENCY_NORMALIZATION = {
    "DEM": "EUR",
}
IMPORTANCE_MAP = {
    -1: "low_or_unknown",
    0: "low",
    1: "medium",
    2: "high",
}


def parse_numeric_expr(expr: pl.Expr) -> pl.Expr:
    return (
        expr.cast(pl.Utf8)
        .str.replace_all(",", "")
        .str.extract(r"(-?\d+(?:\.\d+)?)", 1)
        .cast(pl.Float64, strict=False)
    )


def discover_raw_files() -> list[Path]:
    return sorted(RAW_DIR.glob("20*/*.json"))


def load_records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = payload.get("body", {})
    result = body.get("result", []) if isinstance(body, dict) else []
    meta = payload.get("meta", {})
    for row in result:
        row["fetch_window"] = meta.get("window")
        row["request_path"] = meta.get("request_path")
    return result


def add_pair_relevance(df: pl.DataFrame) -> pl.DataFrame:
    pair_cols = []
    for pair, currencies in PAIR_MAP.items():
        pair_cols.append(
            pl.col("currency_norm").is_in(sorted(currencies)).alias(f"rel_{pair.lower()}")
        )
    return df.with_columns(pair_cols)


def main() -> None:
    raw_files = discover_raw_files()
    if not raw_files:
        raise SystemExit("No raw files found")

    records: list[dict] = []
    for path in raw_files:
        records.extend(load_records(path))

    df = pl.DataFrame(records)
    if df.is_empty():
        raise SystemExit("No records found in raw files")

    df = df.with_columns(
        [
            pl.col("date").str.to_datetime(strict=False, time_zone="UTC").alias("event_timestamp_utc"),
            pl.col("currency").cast(pl.Utf8).replace(CURRENCY_NORMALIZATION).alias("currency_norm"),
            pl.col("importance").cast(pl.Int64, strict=False).alias("importance_score"),
            pl.col("importance")
            .cast(pl.Int64, strict=False)
            .cast(pl.Utf8)
            .replace({str(k): v for k, v in IMPORTANCE_MAP.items()})
            .alias("importance_label"),
            pl.col("country").cast(pl.Utf8).alias("country_code"),
            pl.col("title").cast(pl.Utf8).alias("event_name"),
            pl.col("indicator").cast(pl.Utf8).alias("event_indicator"),
            parse_numeric_expr(pl.col("actual")).alias("actual_num"),
            parse_numeric_expr(pl.col("forecast")).alias("forecast_num"),
            parse_numeric_expr(pl.col("previous")).alias("previous_num"),
        ]
    )

    df = df.with_columns(
        [
            (pl.col("actual_num") - pl.col("forecast_num")).alias("surprise_raw"),
            pl.col("event_timestamp_utc").dt.date().alias("event_date_utc"),
            pl.col("event_timestamp_utc").dt.year().alias("year"),
            pl.col("event_timestamp_utc").dt.month().alias("month"),
        ]
    )

    df = add_pair_relevance(df)

    df = df.select(
        [
            "id",
            "event_timestamp_utc",
            "event_date_utc",
            "year",
            "month",
            "country_code",
            "currency",
            "currency_norm",
            "event_name",
            "event_indicator",
            "importance_score",
            "importance_label",
            "actual",
            "forecast",
            "previous",
            "actual_num",
            "forecast_num",
            "previous_num",
            "surprise_raw",
            "source",
            "unit",
            "scale",
            "period",
            "comment",
            "link",
            "fetch_window",
            "request_path",
            "rel_eurjpy",
            "rel_gbpjpy",
            "rel_gbpusd",
            "rel_nzdusd",
        ]
    ).sort(["event_timestamp_utc", "country_code", "event_name"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUT_DIR / "events.parquet")

    summary = (
        df.group_by(["year", "month"])
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("currency_norm").n_unique().alias("currency_count"),
                pl.col("event_name").n_unique().alias("event_name_count"),
            ]
        )
        .sort(["year", "month"])
    )
    summary.write_csv(OUT_DIR / "summary_by_month.csv")
    print(summary)
    print(f"Wrote {df.height} rows to {OUT_DIR / 'events.parquet'}")


if __name__ == "__main__":
    main()
