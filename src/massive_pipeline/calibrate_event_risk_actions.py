from __future__ import annotations

from pathlib import Path

import json
import numpy as np
import pandas as pd
import polars as pl
import xgboost as xgb
from sklearn.metrics import precision_recall_fscore_support

DATA_FILE = Path("data/processed/modeling/event_risk_training_dataset_with_price_context.parquet")
MODEL_FILE = Path("data/models/event_risk_with_price_context/xgb_y_post_news_session_risk_with_price_context.json")
OUT_DIR = Path("data/models/event_risk_with_price_context/calibration")
TARGET = "y_post_news_session_risk"
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
    "is_train",
    "is_valid",
    "is_test",
}
TRAIN_END = (2025, 6)
VALID_END = (2025, 12)


def add_splits(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        [
            ((pl.col("event_year") < TRAIN_END[0]) | ((pl.col("event_year") == TRAIN_END[0]) & (pl.col("event_month") <= TRAIN_END[1]))).alias("is_train"),
            (
                ((pl.col("event_year") > TRAIN_END[0]) | ((pl.col("event_year") == TRAIN_END[0]) & (pl.col("event_month") > TRAIN_END[1])))
                & ((pl.col("event_year") < VALID_END[0]) | ((pl.col("event_year") == VALID_END[0]) & (pl.col("event_month") <= VALID_END[1])))
            ).alias("is_valid"),
        ]
    )
    return df.with_columns((~pl.col("is_train") & ~pl.col("is_valid")).alias("is_test"))


def band_from_prob(p: float) -> str:
    if p >= 0.70:
        return "avoid_session"
    if p >= 0.45:
        return "halt"
    if p >= 0.20:
        return "reduce_risk"
    return "safe"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = add_splits(pl.read_parquet(DATA_FILE))
    pdf = df.to_pandas().sort_values(["event_timestamp_utc", "pair"]).reset_index(drop=True)
    pdf["pair"] = pdf["pair"].astype("category")

    feature_cols = [c for c in pdf.columns if c not in DROP_COLUMNS]

    model = xgb.XGBClassifier()
    model.load_model(str(MODEL_FILE))

    valid_df = pdf[pdf["is_valid"]].copy()
    test_df = pdf[pdf["is_test"]].copy()

    valid_df["score"] = model.predict_proba(valid_df[feature_cols])[:, 1]
    test_df["score"] = model.predict_proba(test_df[feature_cols])[:, 1]
    valid_df["action_band"] = valid_df["score"].map(band_from_prob)
    test_df["action_band"] = test_df["score"].map(band_from_prob)

    bands = []
    for name, subset in [("valid", valid_df), ("test", test_df)]:
        for band in ["safe", "reduce_risk", "halt", "avoid_session"]:
            ss = subset[subset["action_band"] == band]
            pos_rate = float(ss[TARGET].mean()) if len(ss) else float("nan")
            bands.append({"split": name, "band": band, "rows": int(len(ss)), "positive_rate": pos_rate})
    band_df = pl.DataFrame(bands)
    band_df.write_csv(OUT_DIR / "action_band_summary.csv")

    threshold_rows = []
    for threshold in np.arange(0.1, 0.91, 0.05):
        pred = (test_df["score"] >= threshold).astype(int)
        precision, recall, f1, _ = precision_recall_fscore_support(test_df[TARGET], pred, average="binary", zero_division=0)
        threshold_rows.append(
            {
                "threshold": round(float(threshold), 4),
                "precision": float(precision),
                "recall": float(recall),
                "f1": float(f1),
                "positive_predictions": int(pred.sum()),
            }
        )
    threshold_df = pl.DataFrame(threshold_rows)
    threshold_df.write_csv(OUT_DIR / "threshold_grid_test.csv")

    recommendation = {
        "safe_lt": 0.20,
        "reduce_risk_gte": 0.20,
        "halt_gte": 0.45,
        "avoid_session_gte": 0.70,
        "notes": [
            "Use conservative action bands because this target is session-risk oriented, not a direct execution signal.",
            "Prefer avoid_session only at high probability because false positives are expensive in opportunity cost.",
            "Halt is the default strong action for elevated risk when confidence is moderate-high.",
        ],
    }
    (OUT_DIR / "recommended_action_thresholds.json").write_text(json.dumps(recommendation, indent=2), encoding="utf-8")

    print(band_df)
    print(threshold_df)
    print(json.dumps(recommendation, indent=2))


if __name__ == "__main__":
    main()
