from __future__ import annotations

from pathlib import Path

import polars as pl

RAW_DIR = Path("data/raw/massive/forex/minute_aggs")
OUT_DIR = Path("data/processed/massive/fx_minute_bars")
PAIR_MAP = {
    "C:EUR-USD": "EURUSD",
    "C:USD-JPY": "USDJPY",
    "C:GBP-USD": "GBPUSD",
    "C:USD-CHF": "USDCHF",
    "C:AUD-USD": "AUDUSD",
    "C:USD-CAD": "USDCAD",
    "C:NZD-USD": "NZDUSD",
    "C:EUR-GBP": "EURGBP",
    "C:EUR-JPY": "EURJPY",
    "C:EUR-CHF": "EURCHF",
    "C:EUR-AUD": "EURAUD",
    "C:EUR-CAD": "EURCAD",
    "C:EUR-NZD": "EURNZD",
    "C:GBP-JPY": "GBPJPY",
    "C:GBP-CHF": "GBPCHF",
    "C:GBP-AUD": "GBPAUD",
    "C:GBP-CAD": "GBPCAD",
    "C:GBP-NZD": "GBPNZD",
    "C:AUD-JPY": "AUDJPY",
    "C:AUD-CHF": "AUDCHF",
    "C:AUD-CAD": "AUDCAD",
    "C:AUD-NZD": "AUDNZD",
    "C:CAD-JPY": "CADJPY",
    "C:CAD-CHF": "CADCHF",
    "C:CHF-JPY": "CHFJPY",
    "C:NZD-JPY": "NZDJPY",
    "C:NZD-CHF": "NZDCHF",
    "C:NZD-CAD": "NZDCAD",
}


def session_label_expr() -> pl.Expr:
    h = pl.col("timestamp_utc").dt.hour()
    return (
        pl.when((h >= 0) & (h < 8)).then(pl.lit("asia"))
        .when((h >= 7) & (h < 16)).then(pl.lit("london"))
        .when((h >= 12) & (h < 21)).then(pl.lit("newyork"))
        .otherwise(pl.lit("other"))
        .alias("session_label")
    )


def month_paths() -> list[Path]:
    return sorted(
        p for p in RAW_DIR.glob("20[0-9][0-9]/[0-1][0-9]")
        if p.is_dir()
    )


def normalize_month(month_dir: Path) -> tuple[int, int, int]:
    files = sorted(month_dir.glob("*.csv.gz"))
    if not files:
        return (0, 0, 0)

    dfs = []
    schema_overrides = {
        "ticker": pl.Utf8,
        "volume": pl.Float64,
        "open": pl.Float64,
        "close": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "window_start": pl.Int64,
        "transactions": pl.Int64,
    }
    for path in files:
        dfs.append(pl.read_csv(path, schema_overrides=schema_overrides))

    df = pl.concat(dfs)
    df = df.filter(pl.col("ticker").is_in(list(PAIR_MAP.keys())))
    df = df.with_columns(
        [
            pl.col("ticker").replace(PAIR_MAP).alias("pair"),
            pl.from_epoch(pl.col("window_start"), time_unit="ns").dt.replace_time_zone("UTC").alias("timestamp_utc"),
        ]
    )
    df = df.with_columns(
        [
            pl.col("timestamp_utc").dt.date().alias("date_utc"),
            pl.col("timestamp_utc").dt.year().alias("year"),
            pl.col("timestamp_utc").dt.month().alias("month"),
            pl.col("timestamp_utc").dt.day().alias("day"),
            pl.col("timestamp_utc").dt.hour().alias("hour"),
            pl.col("timestamp_utc").dt.minute().alias("minute"),
            session_label_expr(),
        ]
    )
    if df.height == 0:
        return (0, 0, 0)

    df = df.select(
        [
            "pair",
            "ticker",
            "timestamp_utc",
            "date_utc",
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "session_label",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "transactions",
        ]
    ).sort(["pair", "timestamp_utc"])

    year = int(month_dir.parent.name)
    month = int(month_dir.name)
    out_dir = OUT_DIR / f"year={year:04d}" / f"month={month:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_dir / "data.parquet")
    return (year, month, df.height)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for month_dir in month_paths():
        year, month, count = normalize_month(month_dir)
        if count > 0:
            rows.append({"year": year, "month": month, "rows": count})
            print(year, month, count)

    summary = pl.DataFrame(rows).sort(["year", "month"])
    summary.write_csv(OUT_DIR / "summary_by_month.csv")
    print(summary)


if __name__ == "__main__":
    main()
