from __future__ import annotations

from pathlib import Path

import json
import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEATURE_FILE = ROOT / "data" / "live" / "policy" / "session_range_features.json"
MODEL_FILE = ROOT / "data" / "models" / "session_range" / "lgbm_session_range.joblib"
OUT_FILE = ROOT / "data" / "live" / "policy" / "session_range_predictions.json"


def main() -> None:
    if not FEATURE_FILE.exists():
        raise SystemExit(f"Missing live feature file: {FEATURE_FILE}")
    if not MODEL_FILE.exists():
        raise SystemExit(f"Missing session range model: {MODEL_FILE}")

    payload = json.loads(FEATURE_FILE.read_text(encoding="utf-8"))
    rows = payload.get("pairs", [])
    if not rows:
        raise SystemExit("No live session range feature rows found")

    bundle = joblib.load(MODEL_FILE)
    model = bundle["model"]
    feature_cols = bundle["feature_cols"]
    categorical = set(bundle.get("categorical", []))

    pdf = pd.DataFrame(rows)
    for col in categorical:
        if col in pdf.columns:
            pdf[col] = pdf[col].astype("category")

    pred = model.predict(pdf[feature_cols])
    out_rows = []
    for row, value in zip(rows, pred, strict=False):
        out_rows.append(
            {
                "pair": row["pair"],
                "session_name": row["session_name"],
                "predicted_range_pips": float(value),
                "avg_range_5": row.get("avg_range_5"),
                "avg_range_10": row.get("avg_range_10"),
                "std_range_10": row.get("std_range_10"),
            }
        )

    output = {
        "generated_at_utc": payload.get("generated_at_utc"),
        "session_name": payload.get("session_name"),
        "model": "lgbm_session_range_v1",
        "pairs": out_rows,
    }
    OUT_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
