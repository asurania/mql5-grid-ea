from __future__ import annotations

from pathlib import Path

import json
import joblib
import pandas as pd
import polars as pl
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[2]
IN_FILE = ROOT / "data" / "processed" / "session_range" / "session_range_dataset.parquet"
OUT_DIR = ROOT / "data" / "models" / "session_range"
TARGET = "session_range_pips"
CATEGORICAL = ["pair", "session_name", "day_of_week", "month_num"]
DROP = {"date_ny", "session_open", "session_close", "session_high", "session_low", "session_body_pips", "session_ret_pips", "session_range_frac", "session_return_frac", TARGET}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pl.read_parquet(IN_FILE).sort(["date_ny", "pair", "session_name"])
    pdf = df.to_pandas()

    for col in CATEGORICAL:
        pdf[col] = pdf[col].astype("category")

    pdf["year"] = pd.to_datetime(pdf["date_ny"]).dt.year
    pdf["month"] = pd.to_datetime(pdf["date_ny"]).dt.month

    train = pdf[pdf["year"] <= 2024].copy()
    valid = pdf[(pdf["year"] == 2025) & (pdf["month"] <= 6)].copy()
    test = pdf[(pdf["year"] == 2025) & (pdf["month"] > 6)].copy()

    feature_cols = [c for c in pdf.columns if c not in DROP | {"year", "month"}]

    X_train = train[feature_cols]
    y_train = train[TARGET]
    X_valid = valid[feature_cols]
    y_valid = valid[TARGET]
    X_test = test[feature_cols]
    y_test = test[TARGET]

    model = lgb.LGBMRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        min_child_samples=20,
        random_state=42,
        verbose=-1,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_valid, y_valid)],
        eval_metric="l1",
        categorical_feature=[c for c in CATEGORICAL if c in feature_cols],
    )

    valid_pred = model.predict(X_valid)
    test_pred = model.predict(X_test)

    metrics = {
        "target": TARGET,
        "model_family": "LightGBMRegressor",
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "test_rows": int(len(test)),
        "valid_mae": float(mean_absolute_error(y_valid, valid_pred)),
        "valid_rmse": float(mean_squared_error(y_valid, valid_pred) ** 0.5),
        "test_mae": float(mean_absolute_error(y_test, test_pred)),
        "test_rmse": float(mean_squared_error(y_test, test_pred) ** 0.5),
    }

    feature_importance = (
        pl.DataFrame({"feature": feature_cols, "importance": model.feature_importances_.tolist()})
        .sort("importance", descending=True)
    )

    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    feature_importance.write_csv(OUT_DIR / "feature_importance.csv")
    joblib.dump({"model": model, "feature_cols": feature_cols, "categorical": CATEGORICAL}, OUT_DIR / "lgbm_session_range.joblib")

    print(json.dumps(metrics, indent=2))
    print(feature_importance.head(20))


if __name__ == "__main__":
    main()
