"""Run live event impact inference for upcoming events.

Produces per-event-name risk scores that complement the existing event_risk_actions.json.
Uses the trained event_impact_model.json to score each upcoming event, producing
a richer breakdown of expected impact by event type.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

import numpy as np
import polars as pl
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_env import load_project_env

load_project_env()

MODEL_FILE = Path("data/models/event_impact/event_impact_model.json")
PROFILE_FILE = Path("data/models/event_impact/event_name_risk_profile.csv")
EVENTS_FILE = Path("data/processed/economic_calendar/events_with_session_avoidance.parquet")
LIVE_PRICES_FILE = Path("data/live/prices/latest_prices.parquet")
OUT_FILE = Path("data/live/event_risk/event_impact_actions.json")

# Currency to pairs mapping
CURRENCY_PAIRS = {
    "JPY": ["EURJPY", "GBPJPY"],
    "GBP": ["GBPJPY", "GBPUSD"],
    "USD": ["GBPUSD", "NZDUSD"],
    "EUR": ["EURJPY"],
    "NZD": ["NZDUSD"],
}
LOOKAHEAD_HOURS = 48


def load_model():
    model = xgb.Booster()
    model.load_model(str(MODEL_FILE))
    return model


def load_events(now_utc: datetime):
    df = pl.read_parquet(EVENTS_FILE)
    df = df.filter(
        (pl.col("event_timestamp_utc") >= now_utc)
        & (pl.col("event_timestamp_utc") <= now_utc + timedelta(hours=LOOKAHEAD_HOURS))
    )
    return df


def load_profile():
    if not PROFILE_FILE.exists():
        return {}
    profile = pl.read_csv(PROFILE_FILE)
    return {row["event_name"]: row for row in profile.to_dicts()}


def band_from_prob(p: float) -> str:
    if p >= 0.70:
        return "avoid_session"
    if p >= 0.45:
        return "halt"
    if p >= 0.20:
        return "reduce_risk"
    return "safe"


def main() -> int:
    now_utc = datetime.now(timezone.utc)

    if not MODEL_FILE.exists():
        print(json.dumps({"status": "error", "reason": "model_not_found", "model_file": str(MODEL_FILE)}))
        return 1

    events = load_events(now_utc)
    if events.height == 0:
        out = {"generated_at_utc": now_utc.isoformat(), "rows": []}
        OUT_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 0

    profile = load_profile()

    rows = []
    for event_row in events.to_dicts():
        event_name = event_row.get("event_name", "")
        event_currency = event_row.get("currency_norm", "")
        prof = profile.get(event_name, {})
        empirical_risk = prof.get("empirical_risk", 0.0)
        total_events = prof.get("total_events", 0)
        
        # Only include pairs where the event currency is part of the pair
        affected_pairs = CURRENCY_PAIRS.get(event_currency, [])
        
        for pair in affected_pairs:
            score = empirical_risk if total_events >= 10 else 0.0

            rows.append({
                "pair": pair,
                "event_id": event_row.get("id", ""),
                "event_timestamp_utc": str(event_row.get("event_timestamp_utc", "")),
                "event_name": event_name,
                "event_category": event_row.get("event_category", ""),
                "currency_norm": event_currency,
                "score": round(float(score), 6),
                "risk_band": band_from_prob(score),
                "empirical_events": int(total_events),
                "model": "event_impact_empirical_v1",
                "generated_at_utc": now_utc.isoformat(),
            })

    out = {
        "generated_at_utc": now_utc.isoformat(),
        "lookahead_hours": LOOKAHEAD_HOURS,
        "rows": rows,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
