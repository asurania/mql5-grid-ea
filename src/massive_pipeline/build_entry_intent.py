from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
PAIR_POLICY_FILE = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
OUT_FILE = ROOT / "data" / "live" / "policy" / "entry_intent.json"
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
MONTHS = [
    (2023, m) for m in range(1, 13)
] + [
    (2024, m) for m in range(1, 13)
] + [
    (2025, m) for m in range(1, 13)
] + [
    (2026, m) for m in range(1, 4)
]


def load_latest_price_features() -> dict[str, dict]:
    paths = [PRICE_DIR / f"year={y:04d}" / f"month={m:02d}" / "data.parquet" for y, m in MONTHS]
    existing = [p for p in paths if p.exists()]
    if not existing:
        return {}

    prices = pl.concat([pl.read_parquet(p) for p in existing]).sort(["pair", "timestamp_utc"])
    prices = prices.with_columns(
        [
            (pl.col("close") / pl.col("close").shift(15).over("pair") - 1.0).alias("ret_prev_15m"),
            (pl.col("close") / pl.col("close").shift(60).over("pair") - 1.0).alias("ret_prev_60m"),
            (pl.col("close") / pl.col("close").shift(240).over("pair") - 1.0).alias("ret_prev_240m"),
        ]
    )
    latest = prices.group_by("pair").tail(1).select(["pair", "ret_prev_15m", "ret_prev_60m", "ret_prev_240m"])
    return {row["pair"]: row for row in latest.to_dicts()}


def choose_direction(feat: dict | None) -> tuple[str, str]:
    if not feat:
        return "none", "missing_price_context"

    r15 = float(feat.get("ret_prev_15m") or 0.0)
    r60 = float(feat.get("ret_prev_60m") or 0.0)
    r240 = float(feat.get("ret_prev_240m") or 0.0)

    if r15 > 0 and r60 > 0 and r240 > 0:
        return "buy", "v1_trend_alignment_long"
    if r15 < 0 and r60 < 0 and r240 < 0:
        return "sell", "v1_trend_alignment_short"
    return "none", "no_v1_direction_alignment"


def build_pair_intent(pair: str, policy_map: dict[str, dict], feature_map: dict[str, dict], now_utc: datetime) -> dict:
    policy = policy_map.get(pair, {})
    action = policy.get("policy_action", "allow_trading")

    should_enter = action == "allow_trading"
    direction = "none"
    reason = "no_python_direction_signal_v1"
    entry_mode = "initial"
    suggested_lots = 0.01

    if action != "allow_trading":
        should_enter = False
        reason = f"blocked_by_pair_policy:{action}"
    else:
        direction, reason = choose_direction(feature_map.get(pair))
        should_enter = direction in {"buy", "sell"}

    return {
        "pair": pair,
        "should_enter": should_enter,
        "direction": direction,
        "entry_mode": entry_mode,
        "suggested_lots": suggested_lots,
        "reason": reason,
        "expires_at_utc": (now_utc + timedelta(minutes=5)).isoformat(),
    }


def main() -> int:
    now_utc = datetime.now(timezone.utc)
    pair_policy = json.loads(PAIR_POLICY_FILE.read_text(encoding="utf-8")) if PAIR_POLICY_FILE.exists() else {}
    policy_rows = pair_policy.get("pair_policies", [])
    policy_map = {row.get("pair"): row for row in policy_rows}
    feature_map = load_latest_price_features()

    payload = {
        "generated_at_utc": now_utc.isoformat(),
        "version": "entry_intent_v1",
        "pairs": [build_pair_intent(pair, policy_map, feature_map, now_utc) for pair in PAIRS],
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
