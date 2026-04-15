from __future__ import annotations

from pathlib import Path

import json
import polars as pl
import xgboost as xgb
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score

IN_FILE = Path("data/processed/modeling/trend_danger_training_dataset_v2.parquet")
OUT_DIR = Path("data/models/trend_danger_v2")
TARGET = "y_trend_danger"
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
    "y_trend_danger_right",
    "y_whipsaw_danger",
    "y_volatility_expansion",
    "y_post_news_session_risk",
    "y_avoid_session",
    "is_train",
    "is_valid",
    "is_test",
    "timestamp_utc",
}
CATEGORICAL_COLUMNS = ["pair"]
TRAIN_END = (2025, 6)
VALID_END = (2025, 12)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(IN_FILE)

    df = df.with_columns(
        [
            ((pl.col("event_year") < TRAIN_END[0]) | ((pl.col("event_year") == TRAIN_END[0]) & (pl.col("event_month") <= TRAIN_END[1]))).alias("is_train"),
            (
                ((pl.col("event_year") > TRAIN_END[0]) | ((pl.col("event_year") == TRAIN_END[0]) & (pl.col("event_month") > TRAIN_END[1])))
                & ((pl.col("event_year") < VALID_END[0]) | ((pl.col("event_year") == VALID_END[0]) & (pl.col("event_month") <= VALID_END[1])))
            ).alias("is_valid"),
        ]
    )
    df = df.with_columns((~pl.col("is_train") & ~pl.col("is_valid")).alias("is_test"))

    feature_cols = [c for c in df.columns if c not in DROP_COLUMNS | {"is_train", "is_valid", "is_test"}]

    pdf = df.to_pandas().sort_values(["event_timestamp_utc", "pair"]).reset_index(drop=True)
    pdf[CATEGORICAL_COLUMNS] = pdf[CATEGORICAL_COLUMNS].astype("category")

    train_df = pdf[pdf["is_train"]].copy()
    valid_df = pdf[pdf["is_valid"]].copy()
    test_df = pdf[pdf["is_test"]].copy()

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    X_valid = valid_df[feature_cols]
    y_valid = valid_df[TARGET]
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET]

    pos = max(int(y_train.sum()), 1)
    neg = max(int((1 - y_train).sum()), 1)
    scale_pos_weight = neg / pos

    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        min_child_weight=5,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=42,
        scale_pos_weight=scale_pos_weight,
        enable_categorical=True,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_valid, y_valid)],
        verbose=False,
    )

    valid_proba = model.predict_proba(X_valid)[:, 1]
    test_proba = model.predict_proba(X_test)[:, 1]
    valid_pred = (valid_proba >= 0.5).astype(int)
    test_pred = (test_proba >= 0.5).astype(int)

    metrics = {
        "target": TARGET,
        "version": "v2_with_atr_momentum_surprise",
        "train_rows": int(len(train_df)),
        "valid_rows": int(len(valid_df)),
        "test_rows": int(len(test_df)),
        "train_positive_rate": float(y_train.mean()),
        "valid_positive_rate": float(y_valid.mean()),
        "test_positive_rate": float(y_test.mean()),
        "valid_roc_auc": float(roc_auc_score(y_valid, valid_proba)),
        "valid_pr_auc": float(average_precision_score(y_valid, valid_proba)),
        "test_roc_auc": float(roc_auc_score(y_test, test_proba)),
        "test_pr_auc": float(average_precision_score(y_test, test_proba)),
        "scale_pos_weight": float(scale_pos_weight),
        "new_features": [
            "atr_frac_14", "atr_frac_60", "atr_ratio_14_60",
            "mom_30m", "mom_2h", "abs_mom_30m", "abs_mom_2h",
            "dir_consistency_60", "momentum_aligned",
            "hist_mean_abs_surprise", "hist_surprise_std",
            "hist_surprise_hit_rate", "hist_surprise_count",
        ],
    }

    feature_importance = (
        pl.DataFrame(
            {
                "feature": feature_cols,
                "importance": model.feature_importances_.tolist(),
            }
        )
        .sort("importance", descending=True)
    )

    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    feature_importance.write_csv(OUT_DIR / "feature_importance.csv")
    (OUT_DIR / "validation_report.txt").write_text(classification_report(y_valid, valid_pred), encoding="utf-8")
    (OUT_DIR / "test_report.txt").write_text(classification_report(y_test, test_pred), encoding="utf-8")
    model.save_model(str(OUT_DIR / "xgb_y_trend_danger_v2.json"))

    print(json.dumps(metrics, indent=2))
    print(feature_importance.head(20))


if __name__ == "__main__":
    main()