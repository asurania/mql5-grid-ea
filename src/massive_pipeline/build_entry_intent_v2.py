from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import math

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

# Configuration thresholds
MIN_ALIGNMENT_SCORE = 0.5     # At least 2 of 3 timeframes agree
MIN_TREND_STRENGTH = 0.0002   # Minimum absolute return to consider directional
MAX_TREND_STRENGTH = 0.015     # Avoid entering in extreme moves
MIN_ATR_FRAC = 0.0003         # Minimum volatility to avoid dead chop
MAX_ATR_FRAC = 0.008           # Avoid entering in volatility spikes
INTENT_EXPIRY_MINUTES = 5


def load_latest_price_features() -> dict[str, dict]:
    """Load and compute price features from minute bars."""
    paths = [PRICE_DIR / f"year={y:04d}" / f"month={m:02d}" / "data.parquet" for y, m in MONTHS]
    existing = [p for p in paths if p.exists()]
    if not existing:
        return {}

    prices = pl.concat([pl.read_parquet(p) for p in existing]).sort(["pair", "timestamp_utc"])
    prices = prices.with_columns(pl.col("timestamp_utc").dt.cast_time_unit("ns"))

    prices = prices.with_columns(
        [
            # Multi-timeframe returns
            (pl.col("close") / pl.col("close").shift(5).over("pair") - 1.0).alias("ret_5m"),
            (pl.col("close") / pl.col("close").shift(15).over("pair") - 1.0).alias("ret_15m"),
            (pl.col("close") / pl.col("close").shift(60).over("pair") - 1.0).alias("ret_60m"),
            (pl.col("close") / pl.col("close").shift(240).over("pair") - 1.0).alias("ret_240m"),
            # ATR-like: rolling average of bar range
            ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_frac"),
        ]
    ).with_columns(
        [
            # Rolling volatility (now ret_5m and ret_15m exist)
            pl.col("ret_5m").rolling_std(window_size=30, min_samples=10).over("pair").alias("rvol_5m_30"),
            pl.col("ret_15m").rolling_std(window_size=20, min_samples=8).over("pair").alias("rvol_15m_20"),
            # Average range as fraction of price (ATR proxy)
            pl.col("bar_range_frac").rolling_mean(window_size=60, min_samples=20).over("pair").alias("atr_frac_60"),
            # Rolling mean close for distance calc
            pl.col("close").rolling_mean(window_size=60, min_samples=20).over("pair").alias("ma_60"),
        ]
    )

    # Get latest row per pair
    latest = prices.group_by("pair").tail(1)
    return {row["pair"]: row for row in latest.to_dicts()}


def compute_alignment_score(feat: dict) -> tuple[float, str]:
    """Score how aligned multi-timeframe returns are.
    Returns (score, direction) where score is 0-1.
    Score = fraction of timeframes pointing in the same direction.
    """
    r5 = float(feat.get("ret_5m") or 0.0)
    r15 = float(feat.get("ret_15m") or 0.0)
    r60 = float(feat.get("ret_60m") or 0.0)
    r240 = float(feat.get("ret_240m") or 0.0)

    # Weight longer timeframes more (they represent stronger trend)
    signals = [
        (1.0, r5),    # 5m: weight 1
        (2.0, r15),   # 15m: weight 2
        (3.0, r60),   # 60m: weight 3
        (4.0, r240),  # 240m: weight 4
    ]

    weighted_bullish = sum(w for w, r in signals if r > 0)
    weighted_bearish = sum(w for w, r in signals if r < 0)
    total_weight = sum(w for w, _ in signals)

    if total_weight == 0:
        return 0.0, "neutral"

    if weighted_bullish >= weighted_bearish:
        score = weighted_bullish / total_weight
        direction = "buy"
    else:
        score = weighted_bearish / total_weight
        direction = "sell"

    return score, direction


def compute_trend_strength(feat: dict) -> float:
    """Magnitude of the primary trend direction."""
    r60 = abs(float(feat.get("ret_60m") or 0.0))
    r240 = abs(float(feat.get("ret_240m") or 0.0))
    # Weighted combination: longer TF matters more
    return r60 * 0.4 + r240 * 0.6


def compute_volatility_regime(feat: dict) -> tuple[float, str]:
    """Assess current volatility regime.
    Returns (atr_frac, regime_label).
    """
    atr = float(feat.get("atr_frac_60") or 0.0)
    if atr < MIN_ATR_FRAC:
        return atr, "dead_chop"
    if atr > MAX_ATR_FRAC:
        return atr, "extreme_vol"
    return atr, "normal"


def choose_direction_v2(feat: dict | None) -> tuple[str, str, dict]:
    """V2 direction logic: weighted alignment + volatility regime filter.
    Returns (direction, reason, debug_info).
    """
    if not feat:
        return "none", "missing_price_context", {}

    debug = {}

    # 1. Check volatility regime
    atr_frac, vol_regime = compute_volatility_regime(feat)
    debug["atr_frac_60"] = round(atr_frac, 6)
    debug["vol_regime"] = vol_regime

    if vol_regime == "dead_chop":
        return "none", "vol_regime_dead_chop", debug
    if vol_regime == "extreme_vol":
        return "none", "vol_regime_extreme_vol", debug

    # 2. Compute alignment score
    alignment_score, direction = compute_alignment_score(feat)
    debug["alignment_score"] = round(alignment_score, 3)

    if alignment_score < MIN_ALIGNMENT_SCORE:
        return "none", f"insufficient_alignment_{alignment_score:.2f}", debug

    # 3. Check trend strength
    trend_strength = compute_trend_strength(feat)
    debug["trend_strength"] = round(trend_strength, 6)

    if trend_strength < MIN_TREND_STRENGTH:
        return "none", f"weak_trend_{trend_strength:.6f}", debug
    if trend_strength > MAX_TREND_STRENGTH:
        return "none", f"extreme_trend_{trend_strength:.6f}", debug

    # 4. Check direction consistency (5m shouldn't strongly oppose)
    r5 = float(feat.get("ret_5m") or 0.0)
    r15 = float(feat.get("ret_15m") or 0.0)
    r60 = float(feat.get("ret_60m") or 0.0)

    # If 5m strongly opposes the direction, skip (potential reversal)
    if direction == "buy" and r5 < -0.0003 and abs(r5) > abs(r15) * 0.5:
        return "none", "short_term_counter_buy", debug
    if direction == "sell" and r5 > 0.0003 and abs(r5) > abs(r15) * 0.5:
        return "none", "short_term_counter_sell", debug

    reason = f"v2_aligned_{direction}_str{trend_strength:.4f}_score{alignment_score:.2f}"
    return direction, reason, debug


def build_pair_intent(pair: str, policy_map: dict[str, dict], feature_map: dict[str, dict], now_utc: datetime) -> dict:
    policy = policy_map.get(pair, {})
    action = policy.get("policy_action", "allow_trading")

    should_enter = False
    direction = "none"
    entry_mode = "initial"
    suggested_lots = 0.01
    reason = "no_python_direction_signal"
    debug = {}

    if action != "allow_trading":
        should_enter = False
        reason = f"blocked_by_pair_policy:{action}"
    else:
        direction, reason, debug = choose_direction_v2(feature_map.get(pair))
        should_enter = direction in {"buy", "sell"}

    return {
        "pair": pair,
        "should_enter": should_enter,
        "direction": direction,
        "entry_mode": entry_mode,
        "suggested_lots": suggested_lots,
        "reason": reason,
        "expires_at_utc": (now_utc + timedelta(minutes=INTENT_EXPIRY_MINUTES)).isoformat(),
        "debug": debug,
    }


def main() -> int:
    now_utc = datetime.now(timezone.utc)
    pair_policy = json.loads(PAIR_POLICY_FILE.read_text(encoding="utf-8")) if PAIR_POLICY_FILE.exists() else {}
    policy_rows = pair_policy.get("pair_policies", [])
    policy_map = {row.get("pair"): row for row in policy_rows}

    feature_map = load_latest_price_features()

    payload = {
        "generated_at_utc": now_utc.isoformat(),
        "version": "entry_intent_v2",
        "pairs": [build_pair_intent(pair, policy_map, feature_map, now_utc) for pair in PAIRS],
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())