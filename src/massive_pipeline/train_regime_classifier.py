from __future__ import annotations

from pathlib import Path

import json
import polars as pl
import xgboost as xgb
from sklearn.metrics import classification_report

IN_FILE = Path("data/processed/regime/fx_regime_dataset.parquet")
OUT_DIR = Path("data/models/regime")
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
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

    # Add pair dummies
    df = df.with_columns(
        [
            (pl.col("pair") == "EURJPY").cast(pl.Int8).alias("pair_eurjpy"),
            (pl.col("pair") == "GBPJPY").cast(pl.Int8).alias("pair_gbpjpy"),
            (pl.col("pair") == "GBPUSD").cast(pl.Int8).alias("pair_gbpusd"),
            (pl.col("pair") == "NZDUSD").cast(pl.Int8).alias("pair_nzdusd"),
        ]
    )

    # Map regime_label to numeric
    label_map = {"range": 0, "neutral": 1, "trend": 2}
    df = df.with_columns(
        pl.col("regime_label").replace(label_map).cast(pl.Int8).alias("regime_target")
    )

    # Time split
    df = df.with_columns(pl.col("timestamp_utc").dt.year().alias("year"))
    train = df.filter(pl.col("year") <= 2024)
    valid = df.filter((pl.col("year") == 2025) & (pl.col("timestamp_utc").dt.month() <= 6))
    test = df.filter((pl.col("year") == 2025) & (pl.col("timestamp_utc").dt.month() > 6))

    all_features = FEATURE_COLS + PAIR_DUMMIES

    X_train = train.select(all_features).fill_null(0).to_numpy()
    y_train = train.select("regime_target").to_numpy().ravel()
    X_valid = valid.select(all_features).fill_null(0).to_numpy()
    y_valid = valid.select("regime_target").to_numpy().ravel()
    X_test = test.select(all_features).fill_null(0).to_numpy()
    y_test = test.select("regime_target").to_numpy().ravel()

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        min_child_weight=10,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        tree_method="hist",
        random_state=42,
    )

    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)

    valid_pred = model.predict(X_valid)
    test_pred = model.predict(X_test)

    valid_report = classification_report(y_valid, valid_pred, target_names=["range", "neutral", "trend"], zero_division=0)
    test_report = classification_report(y_test, test_pred, target_names=["range", "neutral", "trend"], zero_division=0)

    # Feature importance
    fi = pl.DataFrame({"feature": all_features, "importance": model.feature_importances_.tolist()}).sort("importance", descending=True)

    # Save
    metrics = {
        "train_rows": int(len(y_train)),
        "valid_rows": int(len(y_valid)),
        "test_rows": int(len(y_test)),
        "train_label_dist": {k: int((y_train == v).sum()) for k, v in label_map.items()},
        "valid_label_dist": {k: int((y_valid == v).sum()) for k, v in label_map.items()},
        "test_label_dist": {k: int((y_test == v).sum()) for k, v in label_map.items()},
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (OUT_DIR / "validation_report.txt").write_text(valid_report, encoding="utf-8")
    (OUT_DIR / "test_report.txt").write_text(test_report, encoding="utf-8")
    fi.write_csv(OUT_DIR / "feature_importance.csv")
    model.save_model(str(OUT_DIR / "xgb_regime_classifier.json"))

    print(json.dumps(metrics, indent=2))
    print("=== Validation ===")
    print(valid_report)
    print("=== Test ===")
    print(test_report)
    print(fi.head(15))


if __name__ == "__main__":
    main()