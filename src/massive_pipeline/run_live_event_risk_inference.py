from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json

import polars as pl
import xgboost as xgb
import joblib

EVENTS_FILE = Path("data/processed/economic_calendar/events_with_session_avoidance.parquet")
PRICE_DIR = Path("data/processed/massive/fx_minute_bars")
XGB_MODEL_FILE = Path("data/models/avoid_session/xgb_y_avoid_session.json")
LGBM_MODEL_FILE = Path("data/models/avoid_session_lgbm/lgbm_y_avoid_session.joblib")
THRESHOLDS_FILE = Path("data/models/avoid_session/calibration/recommended_thresholds.json")
OUT_DIR = Path("data/live/event_risk")
TARGET_PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
MONTHS = [
    (2023, m) for m in range(1, 13)
] + [
    (2024, m) for m in range(1, 13)
] + [
    (2025, m) for m in range(1, 13)
] + [
    (2026, m) for m in range(1, 4)
]

PAIR_CONFIG = {
    "EURJPY": {"base": "EUR", "quote": "JPY"},
    "GBPJPY": {"base": "GBP", "quote": "JPY"},
    "GBPUSD": {"base": "GBP", "quote": "USD"},
    "NZDUSD": {"base": "NZD", "quote": "USD"},
}

CATEGORY_COLUMNS = [
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
]

FEATURE_COLUMNS = [
    "pair",
    "importance_score_filled",
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
    *CATEGORY_COLUMNS,
    "pair_eurjpy",
    "pair_gbpjpy",
    "pair_gbpusd",
    "pair_nzdusd",
    "ret_prev_5m",
    "ret_prev_15m",
    "ret_prev_60m",
    "ret_prev_240m",
    "rolling_std_5m_30",
    "rolling_std_15m_30",
    "avg_range_frac_60",
    "range_width_60",
    "dist_from_mean_60",
]


def load_thresholds() -> dict:
    return json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8"))


def action_from_score(score: float, thresholds: dict) -> tuple[str, str]:
    if score >= thresholds["very_high_confidence_threshold"]:
        return "avoid_session_strong", "very_high_confidence"
    if score >= thresholds["recommended_live_threshold"]:
        return "avoid_session", "standard_avoid"
    if score >= thresholds["fallback_review_threshold"]:
        return "review_or_halt_new_entries", "review_band"
    return "do_not_trigger_avoid_session", "safe_band"


def load_latest_prices() -> pl.DataFrame:
    paths = [PRICE_DIR / f"year={y:04d}" / f"month={m:02d}" / "data.parquet" for y, m in MONTHS]
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise SystemExit("No price parquet files found")
    prices = pl.concat([pl.read_parquet(p) for p in existing]).sort(["pair", "timestamp_utc"])
    prices = prices.with_columns(pl.col("timestamp_utc").dt.cast_time_unit("ns").alias("timestamp_utc"))
    prices = prices.with_columns(
        [
            (pl.col("close") / pl.col("close").shift(5).over("pair") - 1.0).alias("ret_prev_5m"),
            (pl.col("close") / pl.col("close").shift(15).over("pair") - 1.0).alias("ret_prev_15m"),
            (pl.col("close") / pl.col("close").shift(60).over("pair") - 1.0).alias("ret_prev_60m"),
            (pl.col("close") / pl.col("close").shift(240).over("pair") - 1.0).alias("ret_prev_240m"),
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_frac"),
        ]
    ).with_columns(
        [
            pl.col("ret_prev_5m").rolling_std(window_size=30, min_samples=10).over("pair").alias("rolling_std_5m_30"),
            pl.col("ret_prev_15m").rolling_std(window_size=30, min_samples=10).over("pair").alias("rolling_std_15m_30"),
            pl.col("bar_range_frac").rolling_mean(window_size=60, min_samples=20).over("pair").alias("avg_range_frac_60"),
            pl.col("high").rolling_max(window_size=60, min_samples=20).over("pair").alias("rolling_high_60"),
            pl.col("low").rolling_min(window_size=60, min_samples=20).over("pair").alias("rolling_low_60"),
            pl.col("close").rolling_mean(window_size=60, min_samples=20).over("pair").alias("rolling_mean_close_60"),
        ]
    ).with_columns(
        [
            ((pl.col("rolling_high_60") - pl.col("rolling_low_60")) / pl.col("close")).alias("range_width_60"),
            ((pl.col("close") - pl.col("rolling_mean_close_60")) / pl.col("close")).alias("dist_from_mean_60"),
        ]
    )
    return prices


def relevant_pairs(currency: str) -> list[str]:
    out = []
    for pair, cfg in PAIR_CONFIG.items():
        if currency in {cfg["base"], cfg["quote"]}:
            out.append(pair)
    return out


def build_event_pair_rows(events: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict] = []
    for event in events.iter_rows(named=True):
        currency = event["currency_norm"]
        for pair in relevant_pairs(currency):
            category = str(event.get("event_category") or "other")
            category = category if category in {
                "central_bank", "inflation", "employment", "gdp", "pmi", "retail_sales",
                "trade", "housing", "sentiment", "speech", "auction", "agriculture", "other"
            } else "other"
            rows.append(
                {
                    "event_id": event["event_id"],
                    "pair": pair,
                    "event_timestamp_utc": event["event_timestamp_utc"],
                    "event_name": event["event_name"],
                    "event_category": category,
                    "currency_norm": currency,
                    "importance_score_filled": int(event.get("importance_score") or -1),
                    "risk_prior": event.get("risk_prior") or "safe",
                    "avoid_session": event.get("avoid_session") or "none",
                    "event_year": event["event_timestamp_utc"].year,
                    "event_month": event["event_timestamp_utc"].month,
                    "event_weekday": event["event_timestamp_utc"].weekday(),
                    "event_hour": event["event_timestamp_utc"].hour,
                    "risk_prior_halt": 1 if (event.get("risk_prior") == "HALT") else 0,
                    "risk_prior_reduce": 1 if (event.get("risk_prior") == "REDUCE_RISK") else 0,
                    "avoid_asia": 1 if event.get("avoid_session") == "asia" else 0,
                    "avoid_london": 1 if event.get("avoid_session") == "london" else 0,
                    "avoid_both": 1 if event.get("avoid_session") == "both" else 0,
                    "is_jpy_event": 1 if currency == "JPY" else 0,
                    "is_gbp_event": 1 if currency == "GBP" else 0,
                    "is_usd_event": 1 if currency == "USD" else 0,
                    "is_eur_event": 1 if currency == "EUR" else 0,
                    "is_nzd_event": 1 if currency == "NZD" else 0,
                    "pair_is_jpy_cross": 1 if pair.endswith("JPY") else 0,
                    "pair_has_gbp_base": 1 if pair.startswith("GBP") else 0,
                    "pair_has_usd_quote": 1 if pair.endswith("USD") else 0,
                    "pair_eurjpy": 1 if pair == "EURJPY" else 0,
                    "pair_gbpjpy": 1 if pair == "GBPJPY" else 0,
                    "pair_gbpusd": 1 if pair == "GBPUSD" else 0,
                    "pair_nzdusd": 1 if pair == "NZDUSD" else 0,
                    **{col: 1 if col == f"cat_{category}" else 0 for col in CATEGORY_COLUMNS},
                }
            )
    return pl.DataFrame(rows) if rows else pl.DataFrame(schema={"event_id": pl.Utf8})


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    thresholds = load_thresholds()

    # Load both models for ensemble
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(str(XGB_MODEL_FILE))
    lgbm_model = joblib.load(str(LGBM_MODEL_FILE))

    now_utc = datetime.now(timezone.utc)
    events = pl.read_parquet(EVENTS_FILE).with_columns(
        pl.col("event_timestamp_utc").dt.cast_time_unit("ns").alias("event_timestamp_utc")
    )
    upcoming = events.filter(
        (pl.col("event_timestamp_utc") >= pl.lit(now_utc))
        & (pl.col("event_timestamp_utc") <= pl.lit(now_utc).dt.offset_by("2d"))
    )

    event_rows = build_event_pair_rows(upcoming)
    if event_rows.height == 0:
        out = {"generated_at_utc": now_utc.isoformat(), "rows": []}
        (OUT_DIR / "event_risk_actions.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return

    prices = load_latest_prices().select(
        [
            "pair",
            "timestamp_utc",
            "ret_prev_5m",
            "ret_prev_15m",
            "ret_prev_60m",
            "ret_prev_240m",
            "rolling_std_5m_30",
            "rolling_std_15m_30",
            "avg_range_frac_60",
            "range_width_60",
            "dist_from_mean_60",
        ]
    ).sort(["pair", "timestamp_utc"])

    joined = event_rows.join_asof(
        prices,
        left_on="event_timestamp_utc",
        right_on="timestamp_utc",
        by="pair",
        strategy="backward",
    ).rename({"timestamp_utc": "feature_bar_ts"})

    pdf = joined.to_pandas().sort_values(["event_timestamp_utc", "pair"]).reset_index(drop=True)
    pdf["pair"] = pdf["pair"].astype("category")

    # Ensemble: average XGBoost + LightGBM probabilities
    xgb_scores = xgb_model.predict_proba(pdf[FEATURE_COLUMNS])[:, 1]
    lgbm_scores = lgbm_model.predict_proba(pdf[FEATURE_COLUMNS])[:, 1]
    ensemble_scores = (xgb_scores + lgbm_scores) / 2.0

    pdf["score_xgb"] = xgb_scores
    pdf["score_lgbm"] = lgbm_scores
    pdf["score_avoid_session"] = ensemble_scores

    payload_rows = []
    for row in pdf.to_dict(orient="records"):
        action, band = action_from_score(float(row["score_avoid_session"]), thresholds)
        payload_rows.append(
            {
                "pair": row["pair"],
                "event_id": row["event_id"],
                "event_timestamp_utc": row["event_timestamp_utc"].isoformat(),
                "event_name": row["event_name"],
                "model": "ensemble_xgb_lgbm",
                "score_xgb": round(float(row["score_xgb"]), 6),
                "score_lgbm": round(float(row["score_lgbm"]), 6),
                "score_avoid_session": round(float(row["score_avoid_session"]), 6),
                "risk_action": action,
                "risk_band": band,
                "threshold_version": "avoid_session_ensemble_v1",
                "generated_at_utc": now_utc.isoformat(),
            }
        )

    out = {
        "generated_at_utc": now_utc.isoformat(),
        "model": "ensemble_xgb_lgbm",
        "threshold_version": "avoid_session_ensemble_v1",
        "rows": payload_rows,
    }
    (OUT_DIR / "event_risk_actions.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()