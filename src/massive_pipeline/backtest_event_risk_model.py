from __future__ import annotations

from pathlib import Path

import polars as pl
import xgboost as xgb
import numpy as np
import json

FEATURE_FILE = Path("data/processed/modeling/avoid_session_training_dataset.parquet")
MODEL_FILE = Path("data/models/avoid_session/xgb_y_avoid_session.json")
THRESHOLDS_FILE = Path("data/models/avoid_session/calibration/recommended_thresholds.json")
OUT_DIR = Path("data/backtest/event_risk")
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
CATEGORICAL_COLUMNS = ["pair"]
TRAIN_END = (2025, 6)
VALID_END = (2025, 12)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    thresholds = json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8"))
    model = xgb.XGBClassifier()
    model.load_model(str(MODEL_FILE))

    df = pl.read_parquet(FEATURE_FILE)
    df = df.with_columns(
        [
            (
                (pl.col("event_year") < TRAIN_END[0])
                | ((pl.col("event_year") == TRAIN_END[0]) & (pl.col("event_month") <= TRAIN_END[1]))
            ).alias("is_train"),
            (
                ((pl.col("event_year") > TRAIN_END[0]) | ((pl.col("event_year") == TRAIN_END[0]) & (pl.col("event_month") > TRAIN_END[1])))
                & ((pl.col("event_year") < VALID_END[0]) | ((pl.col("event_year") == VALID_END[0]) & (pl.col("event_month") <= VALID_END[1])))
            ).alias("is_valid"),
        ]
    )
    df = df.with_columns((~pl.col("is_train") & ~pl.col("is_valid")).alias("is_test"))

    feature_cols = [c for c in df.columns if c not in DROP_COLUMNS]

    pdf = df.to_pandas().sort_values(["event_timestamp_utc", "pair"]).reset_index(drop=True)
    pdf[CATEGORICAL_COLUMNS] = pdf[CATEGORICAL_COLUMNS].astype("category")

    test_df = pdf[pdf["is_test"]].copy()
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET]
    scores = model.predict_proba(X_test)[:, 1]

    test_df["score"] = scores
    test_df["pred_avoid"] = (scores >= thresholds["recommended_live_threshold"]).astype(int)
    test_df["pred_strong_avoid"] = (scores >= thresholds["very_high_confidence_threshold"]).astype(int)

    # Load joined data for realized outcome context
    joined = pl.read_parquet("data/processed/joined/event_market_context_quantile_labeled.parquet").select(
        [
            "event_id",
            "pair",
            "ret_180m",
            "max_abs_ret_60m",
            "trend_danger_q",
            "whipsaw_danger_q",
            "volatility_expansion_q",
            "post_news_session_risk_q",
        ]
    ).to_pandas()

    merged = test_df.merge(joined, on=["event_id", "pair"], how="left")

    # === Overall confusion matrix style summary ===
    tp = int(((merged["pred_avoid"] == 1) & (merged[TARGET] == 1)).sum())
    fp = int(((merged["pred_avoid"] == 1) & (merged[TARGET] == 0)).sum())
    fn = int(((merged["pred_avoid"] == 0) & (merged[TARGET] == 1)).sum())
    tn = int(((merged["pred_avoid"] == 0) & (merged[TARGET] == 0)).sum())

    # === Realized P&L proxy ===
    # Simplified: if we avoid a session that was truly dangerous, we "saved" the drawdown
    # If we avoid a session that was safe, we "lost" potential profit
    # Use ret_180m as a proxy for what a grid bot would have experienced
    merged["abs_ret_180m"] = merged["ret_180m"].abs().fillna(0)

    avoided_sessions = merged[merged["pred_avoid"] == 1]
    not_avoided_sessions = merged[merged["pred_avoid"] == 0]

    # True positives: avoided dangerous sessions
    tp_sessions = avoided_sessions[avoided_sessions[TARGET] == 1]
    tp_avg_drawdown = float(tp_sessions["abs_ret_180m"].mean()) if len(tp_sessions) > 0 else 0.0
    tp_total_drawdown = float(tp_sessions["abs_ret_180m"].sum()) if len(tp_sessions) > 0 else 0.0

    # False positives: avoided safe sessions (opportunity cost)
    fp_sessions = avoided_sessions[avoided_sessions[TARGET] == 0]
    fp_avg_ret = float(fp_sessions["abs_ret_180m"].mean()) if len(fp_sessions) > 0 else 0.0
    fp_count = len(fp_sessions)

    # False negatives: did not avoid dangerous sessions
    fn_sessions = not_avoided_sessions[not_avoided_sessions[TARGET] == 1]
    fn_avg_drawdown = float(fn_sessions["abs_ret_180m"].mean()) if len(fn_sessions) > 0 else 0.0
    fn_total_drawdown = float(fn_sessions["abs_ret_180m"].sum()) if len(fn_sessions) > 0 else 0.0

    # True negatives: correctly let safe sessions trade
    tn_sessions = not_avoided_sessions[not_avoided_sessions[TARGET] == 0]
    tn_count = len(tn_sessions)

    # === By-pair breakdown ===
    pair_rows = []
    for pair in sorted(merged["pair"].unique()):
        pair_df = merged[merged["pair"] == pair]
        p_tp = int(((pair_df["pred_avoid"] == 1) & (pair_df[TARGET] == 1)).sum())
        p_fp = int(((pair_df["pred_avoid"] == 1) & (pair_df[TARGET] == 0)).sum())
        p_fn = int(((pair_df["pred_avoid"] == 0) & (pair_df[TARGET] == 1)).sum())
        p_tn = int(((pair_df["pred_avoid"] == 0) & (pair_df[TARGET] == 0)).sum())

        p_tp_sessions = pair_df[(pair_df["pred_avoid"] == 1) & (pair_df[TARGET] == 1)]
        p_fn_sessions = pair_df[(pair_df["pred_avoid"] == 0) & (pair_df[TARGET] == 1)]
        p_fp_sessions = pair_df[(pair_df["pred_avoid"] == 1) & (pair_df[TARGET] == 0)]

        pair_rows.append(
            {
                "pair": pair,
                "total_events": int(len(pair_df)),
                "true_positives": p_tp,
                "false_positives": p_fp,
                "false_negatives": p_fn,
                "true_negatives": p_tn,
                "precision": p_tp / max(p_tp + p_fp, 1),
                "recall": p_tp / max(p_tp + p_fn, 1),
                "avg_drawdown_avoided": float(p_tp_sessions["abs_ret_180m"].mean()) if len(p_tp_sessions) > 0 else 0.0,
                "avg_drawdown_missed": float(p_fn_sessions["abs_ret_180m"].mean()) if len(p_fn_sessions) > 0 else 0.0,
                "opportunity_cost_count": p_fp,
            }
        )

    pair_summary = pl.DataFrame(pair_rows).sort("pair")

    # === Strong-avoid only analysis ===
    strong_avoided = merged[merged["pred_strong_avoid"] == 1]
    sa_tp = int(((strong_avoided["pred_strong_avoid"] == 1) & (strong_avoided[TARGET] == 1)).sum())
    sa_fp = int(((strong_avoided["pred_strong_avoid"] == 1) & (strong_avoided[TARGET] == 0)).sum())
    sa_precision = sa_tp / max(sa_tp + sa_fp, 1)

    sa_tp_sessions = strong_avoided[strong_avoided[TARGET] == 1]
    sa_avg_drawdown = float(sa_tp_sessions["abs_ret_180m"].mean()) if len(sa_tp_sessions) > 0 else 0.0

    # === Save outputs ===
    results = {
        "threshold_used": thresholds["recommended_live_threshold"],
        "strong_avoid_threshold": thresholds["very_high_confidence_threshold"],
        "test_period": "2025-07 to 2026-03",
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
        },
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
        "realized_impact": {
            "avg_drawdown_correctly_avoided": round(tp_avg_drawdown, 6),
            "total_drawdown_correctly_avoided": round(tp_total_drawdown, 6),
            "avg_drawdown_missed_false_negatives": round(fn_avg_drawdown, 6),
            "total_drawdown_missed_false_negatives": round(fn_total_drawdown, 6),
            "opportunity_cost_false_positive_count": fp_count,
            "avg_return_in_false_positive_sessions": round(fp_avg_ret, 6),
            "correctly_traded_safe_sessions": tn_count,
        },
        "strong_avoid_analysis": {
            "true_positives": sa_tp,
            "false_positives": sa_fp,
            "precision": round(sa_precision, 4),
            "avg_drawdown_correctly_avoided": round(sa_avg_drawdown, 6),
        },
    }

    (OUT_DIR / "event_risk_backtest_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    pair_summary.write_csv(OUT_DIR / "event_risk_backtest_pair_summary.csv")

    # Save per-event detail for inspection
    detail = merged[[
        "event_id", "pair", "event_timestamp_utc", "score",
        "pred_avoid", "pred_strong_avoid", TARGET,
        "ret_180m", "abs_ret_180m", "trend_danger_q", "whipsaw_danger_q",
        "volatility_expansion_q", "post_news_session_risk_q",
    ]].copy()
    detail.to_parquet(OUT_DIR / "event_risk_backtest_detail.parquet", index=False)

    print(json.dumps(results, indent=2))
    print(pair_summary)


if __name__ == "__main__":
    main()