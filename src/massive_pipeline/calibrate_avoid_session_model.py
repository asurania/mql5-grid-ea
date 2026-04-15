from __future__ import annotations

from pathlib import Path

import json
import numpy as np
import polars as pl
import xgboost as xgb
from sklearn.metrics import precision_recall_fscore_support

DATA_FILE = Path("data/processed/modeling/avoid_session_training_dataset.parquet")
MODEL_FILE = Path("data/models/avoid_session/xgb_y_avoid_session.json")
OUT_DIR = Path("data/models/avoid_session/calibration")
TARGET = "y_avoid_session"
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
    TARGET,
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

    threshold_rows = []
    for threshold in np.arange(0.10, 0.96, 0.05):
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

    operating_points = pl.DataFrame(
        [
            {
                "policy": "balanced",
                "threshold": 0.45,
                "intent": "moderate false positive tolerance, decent recall",
            },
            {
                "policy": "conservative",
                "threshold": 0.60,
                "intent": "higher precision, better for costly avoid-session decisions",
            },
            {
                "policy": "very_conservative",
                "threshold": 0.75,
                "intent": "very high confidence only",
            },
        ]
    )
    operating_points.write_csv(OUT_DIR / "operating_points.csv")

    recommendation = {
        "recommended_live_threshold": 0.60,
        "fallback_review_threshold": 0.45,
        "very_high_confidence_threshold": 0.75,
        "live_rule": {
            "if_score_gte_0_75": "avoid_session_strong",
            "elif_score_gte_0_60": "avoid_session",
            "elif_score_gte_0_45": "review_or_halt_new_entries",
            "else": "do_not_trigger_avoid_session",
        },
        "notes": [
            "Use 0.60 as the default live cutoff because session avoidance has meaningful opportunity cost.",
            "Use 0.45 as a softer review band when other regime controls also look bad.",
            "Use 0.75 for very high-confidence avoidance when you want maximum precision.",
        ],
    }
    (OUT_DIR / "recommended_thresholds.json").write_text(json.dumps(recommendation, indent=2), encoding="utf-8")

    print(threshold_df)
    print(operating_points)
    print(json.dumps(recommendation, indent=2))


if __name__ == "__main__":
    main()
