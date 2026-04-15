from __future__ import annotations

from pathlib import Path

import json
import polars as pl
import xgboost as xgb
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score

IN_FILE = Path("data/processed/regime/fx_regime_dataset.parquet")
OUT_DIR = Path("data/models/regime")
FEATURE_COLS = [
    "ret_5m", "ret_15m", "ret_30m", "ret_60m", "ret_240m",
    "rvol_5m_20", "rvol_5m_60",
    "avg_range_20", "avg_range_60",
    "channel_width_60", "channel_width_240",
    "dist_from_ma60", "dist_from_ma240",
    "trend_consistency_20",
    "bar_range_frac",
]
PAIR_DUMMIES = ["pair_eurjpy", "pair_gbpjpy", "pair_gbpusd", "pair_nzdusd"]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(IN_FILE)

    # Binary: is this trending or not?
    # Trend = regime_label == "trend", everything else = not trending
    df = df.with_columns(
        [
            (pl.col("regime_label") == "trend").cast(pl.Int8).alias("y_trending"),
            (pl.col("pair") == "EURJPY").cast(pl.Int8).alias("pair_eurjpy"),
            (pl.col("pair") == "GBPJPY").cast(pl.Int8).alias("pair_gbpjpy"),
            (pl.col("pair") == "GBPUSD").cast(pl.Int8).alias("pair_gbpusd"),
            (pl.col("pair") == "NZDUSD").cast(pl.Int8).alias("pair_nzdusd"),
        ]
    )

    # Time split
    df = df.with_columns(pl.col("timestamp_utc").dt.year().alias("year"))
    train = df.filter(pl.col("year") <= 2024)
    valid = df.filter((pl.col("year") == 2025) & (pl.col("timestamp_utc").dt.month() <= 6))
    test = df.filter((pl.col("year") == 2025) & (pl.col("timestamp_utc").dt.month() > 6))

    all_features = FEATURE_COLS + PAIR_DUMMIES
    TARGET = "y_trending"

    X_train = train.select(all_features).fill_null(0).to_numpy()
    y_train = train.select(TARGET).to_numpy().ravel()
    X_valid = valid.select(all_features).fill_null(0).to_numpy()
    y_valid = valid.select(TARGET).to_numpy().ravel()
    X_test = test.select(all_features).fill_null(0).to_numpy()
    y_test = test.select(TARGET).to_numpy().ravel()

    pos = max(int(y_train.sum()), 1)
    neg = max(int((1 - y_train).sum()), 1)
    scale_pos_weight = neg / pos

    model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        min_child_weight=10,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=42,
        scale_pos_weight=scale_pos_weight,
    )

    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)

    valid_proba = model.predict_proba(X_valid)[:, 1]
    test_proba = model.predict_proba(X_test)[:, 1]
    valid_pred = (valid_proba >= 0.5).astype(int)
    test_pred = (test_proba >= 0.5).astype(int)

    valid_report = classification_report(y_valid, valid_pred, target_names=["not_trending", "trending"], zero_division=0)
    test_report = classification_report(y_test, test_pred, target_names=["not_trending", "trending"], zero_division=0)
    valid_roc = roc_auc_score(y_valid, valid_proba)
    test_roc = roc_auc_score(y_test, test_proba)
    valid_pr = average_precision_score(y_valid, valid_proba)
    test_pr = average_precision_score(y_test, test_proba)

    fi = pl.DataFrame({"feature": all_features, "importance": model.feature_importances_.tolist()}).sort("importance", descending=True)

    metrics = {
        "target": TARGET,
        "train_rows": int(len(y_train)),
        "valid_rows": int(len(y_valid)),
        "test_rows": int(len(y_test)),
        "train_trending_rate": float(y_train.mean()),
        "valid_trending_rate": float(y_valid.mean()),
        "test_trending_rate": float(y_test.mean()),
        "valid_roc_auc": float(valid_roc),
        "valid_pr_auc": float(valid_pr),
        "test_roc_auc": float(test_roc),
        "test_pr_auc": float(test_pr),
        "scale_pos_weight": float(scale_pos_weight),
    }

    (OUT_DIR / "metrics_binary.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (OUT_DIR / "validation_report_binary.txt").write_text(valid_report, encoding="utf-8")
    (OUT_DIR / "test_report_binary.txt").write_text(test_report, encoding="utf-8")
    fi.write_csv(OUT_DIR / "feature_importance_binary.csv")
    model.save_model(str(OUT_DIR / "xgb_trending_classifier.json"))

    print(json.dumps(metrics, indent=2))
    print("=== Validation ===")
    print(valid_report)
    print("=== Test ===")
    print(test_report)
    print(fi.head(15))


if __name__ == "__main__":
    main()