from __future__ import annotations

from pathlib import Path

import json
import joblib
import polars as pl
import xgboost as xgb
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score

IN_FILE = Path("data/processed/modeling/avoid_session_training_dataset.parquet")
XGB_MODEL = Path("data/models/avoid_session/xgb_y_avoid_session.json")
LGBM_MODEL = Path("data/models/avoid_session_lgbm/lgbm_y_avoid_session.joblib")
OUT_DIR = Path("data/models/avoid_session_ensemble")
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
    "y_trend_danger_right",
    "y_whipsaw_danger",
    "y_volatility_expansion",
    "y_post_news_session_risk",
    "y_avoid_session",
    "is_train",
    "is_valid",
    "is_test",
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

    valid_df = pdf[pdf["is_valid"]].copy()
    test_df = pdf[pdf["is_test"]].copy()

    X_valid = valid_df[feature_cols]
    y_valid = valid_df[TARGET]
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET]

    # Load both models
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(str(XGB_MODEL))

    lgbm_model = joblib.load(str(LGBM_MODEL))

    # Score both
    xgb_valid = xgb_model.predict_proba(X_valid)[:, 1]
    xgb_test = xgb_model.predict_proba(X_test)[:, 1]
    lgbm_valid = lgbm_model.predict_proba(X_valid)[:, 1]
    lgbm_test = lgbm_model.predict_proba(X_test)[:, 1]

    # Ensemble: average probabilities
    ens_valid = (xgb_valid + lgbm_valid) / 2.0
    ens_test = (xgb_test + lgbm_test) / 2.0

    # Also compute individual model metrics for comparison
    results = {
        "ensemble_method": "probability_average",
        "models": ["xgb_y_avoid_session", "lgbm_y_avoid_session"],
        "xgboost": {
            "valid_roc_auc": float(roc_auc_score(y_valid, xgb_valid)),
            "valid_pr_auc": float(average_precision_score(y_valid, xgb_valid)),
            "test_roc_auc": float(roc_auc_score(y_test, xgb_test)),
            "test_pr_auc": float(average_precision_score(y_test, xgb_test)),
        },
        "lightgbm": {
            "valid_roc_auc": float(roc_auc_score(y_valid, lgbm_valid)),
            "valid_pr_auc": float(average_precision_score(y_valid, lgbm_valid)),
            "test_roc_auc": float(roc_auc_score(y_test, lgbm_test)),
            "test_pr_auc": float(average_precision_score(y_test, lgbm_test)),
        },
        "ensemble": {
            "valid_roc_auc": float(roc_auc_score(y_valid, ens_valid)),
            "valid_pr_auc": float(average_precision_score(y_valid, ens_valid)),
            "test_roc_auc": float(roc_auc_score(y_test, ens_test)),
            "test_pr_auc": float(average_precision_score(y_test, ens_test)),
        },
    }

    # Calibration at key thresholds for the ensemble
    import numpy as np
    from sklearn.metrics import precision_recall_fscore_support

    threshold_rows = []
    for threshold in np.arange(0.10, 0.96, 0.05):
        pred = (ens_test >= threshold).astype(int)
        precision, recall, f1, _ = precision_recall_fscore_support(y_test, pred, average="binary", zero_division=0)
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

    # Strong-avoid analysis
    strong_pred = (ens_test >= 0.75).astype(int)
    strong_tp = int(((strong_pred == 1) & (y_test == 1)).sum())
    strong_fp = int(((strong_pred == 1) & (y_test == 0)).sum())
    strong_precision = strong_tp / max(strong_tp + strong_fp, 1)

    results["strong_avoid_analysis"] = {
        "threshold": 0.75,
        "true_positives": strong_tp,
        "false_positives": strong_fp,
        "precision": round(strong_precision, 4),
    }

    standard_pred = (ens_test >= 0.60).astype(int)
    std_tp = int(((standard_pred == 1) & (y_test == 1)).sum())
    std_fp = int(((standard_pred == 1) & (y_test == 0)).sum())
    std_precision = std_tp / max(std_tp + std_fp, 1)

    results["standard_avoid_analysis"] = {
        "threshold": 0.60,
        "true_positives": std_tp,
        "false_positives": std_fp,
        "precision": round(std_precision, 4),
    }

    (OUT_DIR / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Classification reports
    ens_valid_pred = (ens_valid >= 0.5).astype(int)
    ens_test_pred = (ens_test >= 0.5).astype(int)
    (OUT_DIR / "validation_report.txt").write_text(classification_report(y_valid, ens_valid_pred), encoding="utf-8")
    (OUT_DIR / "test_report.txt").write_text(classification_report(y_test, ens_test_pred), encoding="utf-8")

    print(json.dumps(results, indent=2))
    print(threshold_df)


if __name__ == "__main__":
    main()