"""Build per-event impact learning model.

Trains a model to predict per-event session risk (y_post_news_session_risk) using
historical outcomes. Produces event_name-level risk profiles that the live pipeline
can use for sharper event-specific thresholds.

Inputs:
  data/processed/modeling/event_risk_training_dataset_with_price_context.parquet

Outputs:
  data/models/event_impact/event_impact_model.json           (XGB model)
  data/models/event_impact/event_name_risk_profile.csv     (per-event-name empirical risk)
  data/live/event_risk/event_impact_score.json              (live inference output)
"""
from __future__ import annotations

from pathlib import Path

import json
import numpy as np
import polars as pl
import xgboost as xgb
from sklearn.metrics import roc_auc_score, precision_recall_fscore_support

DATA_FILE = Path("data/processed/modeling/event_risk_training_dataset_with_price_context.parquet")
MODEL_DIR = Path("data/models/event_impact")
MODEL_FILE = MODEL_DIR / "event_impact_model.json"
PROFILE_FILE = MODEL_DIR / "event_name_risk_profile.csv"
OUT_DIR = Path("data/live/event_risk")
LIVE_FILE = OUT_DIR / "event_impact_score.json"

TARGET = "y_post_news_session_risk"
DROP_COLS = {
    "event_id",
    "event_timestamp_utc",
    "feature_bar_ts",
    "event_name",
    "event_category",
    "currency_norm",
    "risk_prior",
    "avoid_session",
    "is_train",
    "is_valid",
    "is_test",
    "y_trend_danger",
    "y_whipsaw_danger",
    "y_volatility_expansion",
    "y_post_news_session_risk",
}

TRAIN_END = (2025, 6)
VALID_END = (2025, 12)


def add_splits(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        [
            (
                (pl.col("event_year") < TRAIN_END[0])
                | (
                    (pl.col("event_year") == TRAIN_END[0])
                    & (pl.col("event_month") <= TRAIN_END[1])
                )
            ).alias("is_train"),
            (
                (
                    (pl.col("event_year") > TRAIN_END[0])
                    | (
                        (pl.col("event_year") == TRAIN_END[0])
                        & (pl.col("event_month") > TRAIN_END[1])
                    )
                )
                & (
                    (pl.col("event_year") < VALID_END[0])
                    | (
                        (pl.col("event_year") == VALID_END[0])
                        & (pl.col("event_month") <= VALID_END[1])
                    )
                )
            ).alias("is_valid"),
        ]
    )
    return df.with_columns((~pl.col("is_train") & ~pl.col("is_valid")).alias("is_test"))


def build_event_name_profile(df: pl.DataFrame) -> pl.DataFrame:
    """Empirical risk rate per event_name across all pairs."""
    return (
        df.group_by("event_name")
        .agg(
            [
                pl.len().alias("total_events"),
                pl.col("y_post_news_session_risk").mean().alias("empirical_risk"),
                pl.col("y_post_news_session_risk").std().alias("risk_std"),
                pl.col("y_volatility_expansion").mean().alias("vol_expansion_rate"),
                pl.col("y_trend_danger").mean().alias("trend_danger_rate"),
                pl.n_unique("pair").alias("affected_pairs"),
                pl.col("event_category").first().alias("event_category"),
            ]
        )
        .filter(pl.col("total_events") >= 10)
        .sort("empirical_risk", descending=True)
    )


def band_from_prob(p: float) -> str:
    if p >= 0.70:
        return "avoid_session"
    if p >= 0.45:
        return "halt"
    if p >= 0.20:
        return "reduce_risk"
    return "safe"


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = add_splits(pl.read_parquet(DATA_FILE))
    pdf = df.to_pandas().sort_values(["event_timestamp_utc", "pair"]).reset_index(drop=True)
    pdf["pair"] = pdf["pair"].astype("category")

    # Build event name risk profile
    profile = build_event_name_profile(df)
    profile.write_csv(PROFILE_FILE)
    print("=== Event Name Risk Profile (top-20) ===")
    print(profile.head(20))
    print()

    # Train model
    feature_cols = [c for c in pdf.columns if c not in DROP_COLS]
    print(f"Training with {len(feature_cols)} features")

    train_x = pdf[pdf["is_train"]][feature_cols]
    train_y = pdf[pdf["is_train"]][TARGET]
    valid_x = pdf[pdf["is_valid"]][feature_cols]
    valid_y = pdf[pdf["is_valid"]][TARGET]
    test_x = pdf[pdf["is_test"]][feature_cols]
    test_y = pdf[pdf["is_test"]][TARGET]

    dtrain = xgb.DMatrix(train_x, label=train_y, enable_categorical=True)
    dvalid = xgb.DMatrix(valid_x, label=valid_y, enable_categorical=True)
    dtest = xgb.DMatrix(test_x, label=test_y, enable_categorical=True)

    model = xgb.train(
        {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "eta": 0.05,
            "max_depth": 5,
            "min_child_weight": 10,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "scale_pos_weight": float(len(train_y) - train_y.sum()) / float(train_y.sum()),
        },
        dtrain,
        num_boost_round=2000,
        evals=[(dtrain, "train"), (dvalid, "valid")],
        early_stopping_rounds=50,
        verbose_eval=False,
    )

    model.save_model(str(MODEL_FILE))
    print(f"Model saved to {MODEL_FILE}")

    # Evaluate
    for name, dx, dy in [("valid", dvalid, valid_y), ("test", dtest, test_y)]:
        pred = model.predict(dx)
        auc = roc_auc_score(dy, pred)
        band_pred = [band_from_prob(p) for p in pred]
        band_actual = [band_from_prob(y) for y in dy]
        print(f"\n{name.upper()} AUC={auc:.4f}")

        for band in ["safe", "reduce_risk", "halt", "avoid_session"]:
            mask = dy == (1 if band in ["halt", "avoid_session"] else 0)
            if mask.sum() == 0:
                continue
            print(f"  {band}: mean_pred={pred[mask].mean():.4f}, mean_actual={dy[mask].mean():.4f}")

    # Feature importance
    importance = model.get_score(importance_type="gain")
    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    print(f"\nTop-15 features by gain:")
    for name, score in sorted_imp[:15]:
        print(f"  {name}: {score:.1f}")

    # Write live inference file for the next run
    live_out = {
        "model_file": str(MODEL_FILE),
        "profile_file": str(PROFILE_FILE),
        "generated_at_utc": str(pl.datetime(2026, 4, 22, 5, 40, 0)),
        "feature_count": len(feature_cols),
        "top_risk_events": profile.head(10).to_dicts(),
    }
    LIVE_FILE.write_text(json.dumps(live_out, indent=2, default=str), encoding="utf-8")
    print(f"\nLive inference metadata written to {LIVE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
