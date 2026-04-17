from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import json

import polars as pl


def mt5_utc_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y.%m.%d %H:%M:%S")

ROOT = Path(__file__).resolve().parents[2]
PAIR_POLICY_FILE = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
ENTRY_INTENT_FILE = ROOT / "data" / "live" / "policy" / "entry_intent.json"
OUT_FILE = ROOT / "data" / "live" / "policy" / "grid_policy.json"
SESSION_RANGE_PREDICTIONS_FILE = ROOT / "data" / "live" / "policy" / "session_range_predictions.json"
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
EXPIRY_MINUTES = 15

DEFAULT_ACCOUNT_EQUITY = 10_000.0
DEFAULT_RISK_MODE = "medium"
RISK_BUDGET_PCT = {
    "low": 0.01,
    "medium": 0.015,
    "high": 0.02,
}
TARGET_PROFIT_PCT = {
    "low": 0.01,
    "medium": 0.015,
    "high": 0.02,
}
SESSION_WINDOWS_NY = {
    "asia": (17, 0, 0, 59),
    "london": (3, 0, 11, 59),
    "new_york": (8, 0, 17, 0),
}

# Session close times in UTC (for liquidation timing)
# These are the END of each trading session in UTC
SESSION_CLOSE_UTC = {
    "asia": (0, 59),     # Asia closes ~00:59 UTC (NY 19:59 previous day)
    "london": (11, 59),   # London closes ~11:59 UTC (NY 07:59)
    "new_york": (21, 0),  # NY closes ~21:00 UTC (NY 17:00 EST)
}
PIP_SIZE = {
    "EURJPY": 0.01,
    "GBPJPY": 0.01,
    "GBPUSD": 0.0001,
    "NZDUSD": 0.0001,
}
PIP_VALUE_PER_001_LOT = {
    "EURJPY": 0.09,
    "GBPJPY": 0.09,
    "GBPUSD": 0.13,
    "NZDUSD": 0.13,
}
SEARCH_STEP_PIPS = [6, 8, 10, 12, 15, 18, 22]
SEARCH_MULTIPLIERS = [1.03, 1.05, 1.08, 1.10, 1.12, 1.15, 1.20]
SEARCH_LEVELS = [2, 3, 4, 5, 6]
MIN_INITIAL_LOT = 0.01
MAX_INITIAL_LOT = 5.00
LOT_STEP = 0.01
MAX_BASKET_DD_PCT = {
    "low": 0.01,
    "medium": 0.015,
    "high": 0.02,
}
MAX_GROSS_LOTS_PCT_OF_EQUITY = 0.00004
MIN_STEP_TO_SPREAD_RATIO = {
    "low": 4.0,
    "medium": 3.0,
    "high": 2.5,
}
MIN_FREE_MARGIN_PERCENT = {
    "low": 85.0,
    "medium": 75.0,
    "high": 65.0,
}
ASSUMED_SPREAD_PIPS = {
    "EURJPY": 1.2,
    "GBPJPY": 1.8,
    "GBPUSD": 1.0,
    "NZDUSD": 1.4,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build grid policy from session-aware optimizer + fallbacks.")
    parser.add_argument("--account-equity", type=float, default=DEFAULT_ACCOUNT_EQUITY, help="Account equity used for risk sizing")
    parser.add_argument("--risk-mode", choices=sorted(RISK_BUDGET_PCT.keys()), default=DEFAULT_RISK_MODE, help="Risk mode for risk budget / target profit")
    parser.add_argument("--allow-gbpjpy-demo-override", action="store_true", help="Keep current GBPJPY fixed demo override active")
    return parser.parse_args()

# Static template library for v1.
# Later this will be selected by ML.
GRID_TEMPLATES = {
    "no_trade": {
        "allow_new_basket": False,
        "grid_mode": "both_sides",
        "seed_mode": "single_side",
        "step_pips": 0,
        "initial_lot": 0.0,
        "multiplier": 1.0,
        "max_trades_per_side": 0,
        "basket_tp_currency": 0.0,
        "max_gross_lots": 0.0,
        "max_basket_drawdown_currency": 0.0,
        "min_step_to_spread_ratio": 0.0,
        "min_free_margin_percent": 0.0,
        "flatten_on_strong_avoid": True,
        "confidence": 1.0,
        "reason": "no_trade_template",
    },
    "both_sides_conservative": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "seed_mode": "single_side",
        "step_pips": 18,
        "initial_lot": 0.01,
        "multiplier": 1.10,
        "max_trades_per_side": 3,
        "basket_tp_currency": 2.00,
        "max_gross_lots": 0.20,
        "max_basket_drawdown_currency": 100.0,
        "min_step_to_spread_ratio": 3.0,
        "min_free_margin_percent": 75.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.65,
        "reason": "static_both_sides_conservative",
    },
    "both_sides_normal": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "seed_mode": "single_side",
        "step_pips": 12,
        "initial_lot": 0.01,
        "multiplier": 1.20,
        "max_trades_per_side": 5,
        "basket_tp_currency": 3.00,
        "max_gross_lots": 0.25,
        "max_basket_drawdown_currency": 150.0,
        "min_step_to_spread_ratio": 3.0,
        "min_free_margin_percent": 75.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.65,
        "reason": "static_both_sides_normal",
    },
    "both_sides_wide_light": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "seed_mode": "both_sides",
        "step_pips": 22,
        "initial_lot": 0.01,
        "multiplier": 1.05,
        "max_trades_per_side": 4,
        "basket_tp_currency": 2.00,
        "max_gross_lots": 0.20,
        "max_basket_drawdown_currency": 120.0,
        "min_step_to_spread_ratio": 3.5,
        "min_free_margin_percent": 80.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.60,
        "reason": "static_both_sides_wide_light",
    },
    "classic_consolidation_light": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "seed_mode": "both_sides",
        "step_pips": 14,
        "initial_lot": 0.01,
        "multiplier": 1.10,
        "max_trades_per_side": 5,
        "basket_tp_currency": 2.50,
        "max_gross_lots": 0.20,
        "max_basket_drawdown_currency": 120.0,
        "min_step_to_spread_ratio": 3.0,
        "min_free_margin_percent": 75.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.68,
        "reason": "classic_consolidation_light",
    },
    "classic_consolidation_normal": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "seed_mode": "both_sides",
        "step_pips": 10,
        "initial_lot": 0.01,
        "multiplier": 1.20,
        "max_trades_per_side": 6,
        "basket_tp_currency": 3.00,
        "max_gross_lots": 0.25,
        "max_basket_drawdown_currency": 150.0,
        "min_step_to_spread_ratio": 3.0,
        "min_free_margin_percent": 75.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.70,
        "reason": "classic_consolidation_normal",
    },
    "classic_consolidation_dense": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "seed_mode": "both_sides",
        "step_pips": 8,
        "initial_lot": 0.01,
        "multiplier": 1.25,
        "max_trades_per_side": 7,
        "basket_tp_currency": 3.50,
        "max_gross_lots": 0.30,
        "max_basket_drawdown_currency": 180.0,
        "min_step_to_spread_ratio": 2.5,
        "min_free_margin_percent": 70.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.62,
        "reason": "classic_consolidation_dense",
    },
    "buy_only_conservative": {
        "allow_new_basket": True,
        "grid_mode": "buy_only",
        "seed_mode": "single_side",
        "step_pips": 15,
        "initial_lot": 0.01,
        "multiplier": 1.15,
        "max_trades_per_side": 4,
        "basket_tp_currency": 2.50,
        "max_gross_lots": 0.20,
        "max_basket_drawdown_currency": 120.0,
        "min_step_to_spread_ratio": 3.0,
        "min_free_margin_percent": 75.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.60,
        "reason": "static_buy_only_conservative",
    },
    "sell_only_conservative": {
        "allow_new_basket": True,
        "grid_mode": "sell_only",
        "seed_mode": "single_side",
        "step_pips": 15,
        "initial_lot": 0.01,
        "multiplier": 1.15,
        "max_trades_per_side": 4,
        "basket_tp_currency": 2.50,
        "max_gross_lots": 0.20,
        "max_basket_drawdown_currency": 120.0,
        "min_step_to_spread_ratio": 3.0,
        "min_free_margin_percent": 75.0,
        "flatten_on_strong_avoid": True,
        "confidence": 0.60,
        "reason": "static_sell_only_conservative",
    },
}


def infer_session_name(now_utc: datetime) -> str:
    ny = now_utc.astimezone(timezone(timedelta(hours=-4)))
    hm = ny.hour * 60 + ny.minute
    for session_name, (start_h, start_m, end_h, end_m) in SESSION_WINDOWS_NY.items():
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start <= end:
            if start <= hm <= end:
                return session_name
        else:
            if hm >= start or hm <= end:
                return session_name
    return "new_york"


def get_session_close_utc(now_utc: datetime, session_name: str) -> str:
    """Get the UTC close time for the current session as an MT5 timestamp."""
    close_h, close_m = SESSION_CLOSE_UTC.get(session_name, (21, 0))
    # Build the close time for today or tomorrow if we're already past it
    close_today = now_utc.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    # If we're already past the close time, it means next day's session
    if now_utc >= close_today:
        close_today += timedelta(days=1)
    return mt5_utc_timestamp(close_today)


def get_managed_close_utc(now_utc: datetime, session_name: str, minutes_before: int = 30) -> str:
    """Get the UTC time when managed close begins (N minutes before session close)."""
    close_h, close_m = SESSION_CLOSE_UTC.get(session_name, (21, 0))
    close_today = now_utc.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    if now_utc >= close_today:
        close_today += timedelta(days=1)
    managed_start = close_today - timedelta(minutes=minutes_before)
    return mt5_utc_timestamp(managed_start)


def get_liquidate_utc(now_utc: datetime, session_name: str, minutes_before: int = 10) -> str:
    """Get the UTC time when forced liquidation begins (N minutes before session close)."""
    close_h, close_m = SESSION_CLOSE_UTC.get(session_name, (21, 0))
    close_today = now_utc.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    if now_utc >= close_today:
        close_today += timedelta(days=1)
    liquidate_start = close_today - timedelta(minutes=minutes_before)
    return mt5_utc_timestamp(liquidate_start)


def load_session_range_predictions() -> dict[str, dict]:
    if not SESSION_RANGE_PREDICTIONS_FILE.exists():
        return {}
    payload = json.loads(SESSION_RANGE_PREDICTIONS_FILE.read_text(encoding="utf-8"))
    return {row.get("pair"): row for row in payload.get("pairs", [])}


def load_session_range_features(now_utc: datetime) -> dict[str, dict]:
    paths = sorted(PRICE_DIR.glob('year=*/month=*/data.parquet'))
    if not paths:
        flat_paths = sorted(PRICE_DIR.glob('*.parquet'))
        paths = flat_paths
    if not paths:
        return {}

    scan = pl.scan_parquet([str(p) for p in paths]).filter(pl.col('pair').is_in(PAIRS)).select(['pair', 'timestamp_utc', 'high', 'low'])
    data = scan.collect().sort(['pair', 'timestamp_utc']).with_columns(
        pl.col('timestamp_utc').dt.convert_time_zone('America/New_York').alias('ts_ny')
    ).with_columns([
        pl.col('ts_ny').dt.date().alias('date_ny'),
        pl.col('ts_ny').dt.hour().alias('hour_ny'),
        pl.col('ts_ny').dt.minute().alias('minute_ny'),
    ])
    if data.height == 0:
        return {}

    session_name = infer_session_name(now_utc)
    start_h, start_m, end_h, end_m = SESSION_WINDOWS_NY[session_name]
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    hm_expr = pl.col('hour_ny').cast(pl.Int32) * 60 + pl.col('minute_ny').cast(pl.Int32)
    if start <= end:
        session_filter = (hm_expr >= start) & (hm_expr <= end)
    else:
        session_filter = (hm_expr >= start) | (hm_expr <= end)

    sess = data.filter(session_filter).group_by(['pair', 'date_ny']).agg([
        pl.col('high').max().alias('session_high'),
        pl.col('low').min().alias('session_low'),
    ]).with_columns([
        ((pl.col('session_high') - pl.col('session_low')) / pl.col('pair').replace_strict(PIP_SIZE)).alias('range_pips')
    ])

    features = {}
    for pair in PAIRS:
        pair_df = sess.filter(pl.col('pair') == pair).sort('date_ny', descending=True)
        if pair_df.height == 0:
            continue
        recent = pair_df.head(10)
        features[pair] = {
            'session_name': session_name,
            'predicted_range_pips': float(recent['range_pips'].median()),
            'recent_avg_range_pips': float(recent['range_pips'].mean()),
            'recent_max_range_pips': float(recent['range_pips'].max()),
        }
    return features


def estimate_breakout_risk(entry_row: dict | None) -> float:
    if not entry_row:
        return 0.5
    debug = entry_row.get('debug', {}) or {}
    trend_strength = float(debug.get('trend_strength', 0.0) or 0.0)
    alignment = float(debug.get('alignment_score', 0.0) or 0.0)
    vol_regime = str(debug.get('vol_regime', 'normal'))

    risk = 0.35 + min(trend_strength / 0.01, 0.4) + max(alignment - 0.5, 0.0) * 0.3
    if vol_regime == 'extreme_vol':
        risk += 0.25
    if vol_regime == 'dead_chop':
        risk -= 0.15
    return max(0.05, min(0.95, risk))


def compute_candidate_drawdown(initial_lot: float, step_pips: float, multiplier: float, max_levels: int, pip_value_001: float) -> float:
    total = 0.0
    lots = initial_lot
    for level in range(max_levels):
        adverse_pips = step_pips * max(0, max_levels - 1 - level)
        total += lots / 0.01 * pip_value_001 * adverse_pips
        lots *= multiplier
    return total


def solve_initial_lot(step_pips: float, multiplier: float, max_levels: int, pip_value_001: float, risk_budget_currency: float, max_initial_lot: float = MAX_INITIAL_LOT) -> float:
    best = 0.0
    lot = MIN_INITIAL_LOT
    while lot <= min(MAX_INITIAL_LOT, max_initial_lot) + 1e-9:
        dd = compute_candidate_drawdown(lot, step_pips, multiplier, max_levels, pip_value_001)
        if dd <= risk_budget_currency:
            best = lot
            lot += LOT_STEP
        else:
            break
    return round(best, 2)


def build_optimized_policy(
    pair: str,
    entry_row: dict | None,
    session_features: dict[str, dict],
    *,
    account_equity: float,
    risk_mode: str,
) -> tuple[str, dict] | None:
    feat = session_features.get(pair)
    if not feat:
        return None

    predicted_range = max(20.0, float(feat.get('predicted_range_pips', 40.0)))
    breakout_risk = estimate_breakout_risk(entry_row)
    risk_budget = account_equity * RISK_BUDGET_PCT[risk_mode]
    target_profit = account_equity * TARGET_PROFIT_PCT[risk_mode]
    max_basket_dd = account_equity * MAX_BASKET_DD_PCT[risk_mode]
    max_gross_lots = max(MIN_INITIAL_LOT, round(account_equity * MAX_GROSS_LOTS_PCT_OF_EQUITY, 2))
    max_initial_lot = min(MAX_INITIAL_LOT, max_gross_lots * 0.5)  # never more than half gross cap
    min_step_to_spread_ratio = MIN_STEP_TO_SPREAD_RATIO[risk_mode]
    min_free_margin_percent = MIN_FREE_MARGIN_PERCENT[risk_mode]
    assumed_spread_pips = ASSUMED_SPREAD_PIPS[pair]
    pip_value_001 = PIP_VALUE_PER_001_LOT[pair]

    candidates = []
    for step_pips in SEARCH_STEP_PIPS:
        if step_pips > predicted_range * 0.45:
            continue
        if step_pips / max(assumed_spread_pips, 0.1) < min_step_to_spread_ratio:
            continue
        for multiplier in SEARCH_MULTIPLIERS:
            if breakout_risk > 0.7 and multiplier > 1.10:
                continue
            for max_levels in SEARCH_LEVELS:
                if step_pips * max_levels > predicted_range * 1.35:
                    continue
                initial_lot = solve_initial_lot(step_pips, multiplier, max_levels, pip_value_001, risk_budget, max_initial_lot)
                if initial_lot < MIN_INITIAL_LOT:
                    continue
                dd = compute_candidate_drawdown(initial_lot, step_pips, multiplier, max_levels, pip_value_001)
                gross_lots = sum(initial_lot * (multiplier ** level) for level in range(max_levels))
                if gross_lots > max_gross_lots:
                    continue
                if dd > max_basket_dd:
                    continue
                # Expected capture scales with depth and lot size
                expected_capture = min(target_profit, predicted_range * pip_value_001 * (initial_lot / 0.01) * 0.35)

                # Penalize shallow grids (1-2 levels is barely a grid)
                depth_penalty = 0.0
                if max_levels < 3:
                    depth_penalty = (3 - max_levels) * 80.0  # very heavy penalty for 1-2 levels
                elif max_levels < 4:
                    depth_penalty = 15.0  # moderate penalty for 3 levels
                elif max_levels < 5:
                    depth_penalty = 3.0  # mild penalty for 4 levels

                # Reward using a reasonable fraction of the DD budget (50-85% is ideal)
                dd_fraction = dd / max_basket_dd if max_basket_dd > 0 else 0.0
                budget_efficiency = 0.0
                if 0.40 <= dd_fraction <= 0.85:
                    budget_efficiency = 15.0  # reward for using budget well
                elif dd_fraction < 0.25:
                    budget_efficiency = -(0.25 - dd_fraction) * 60.0  # penalize under-using budget
                elif dd_fraction > 0.95:
                    budget_efficiency = -20.0  # penalize near-max DD

                utility = expected_capture - 0.55 * dd - breakout_risk * 40.0 - max(0, step_pips - predicted_range * 0.18) * 0.4 - depth_penalty + budget_efficiency
                candidates.append({
                    'step_pips': step_pips,
                    'multiplier': multiplier,
                    'max_trades_per_side': max_levels,
                    'initial_lot': initial_lot,
                    'expected_dd': dd,
                    'expected_capture': expected_capture,
                    'utility': utility,
                    'predicted_range_pips': predicted_range,
                    'breakout_risk': breakout_risk,
                    'session_name': feat.get('session_name', 'unknown'),
                    'gross_lots': gross_lots,
                    'max_basket_dd': max_basket_dd,
                    'max_gross_lots': max_gross_lots,
                    'min_step_to_spread_ratio': min_step_to_spread_ratio,
                    'min_free_margin_percent': min_free_margin_percent,
                })

    if not candidates:
        return None

    best = max(candidates, key=lambda x: x['utility'])
    grid_mode = 'both_sides' if breakout_risk < 0.6 else ('buy_only' if (entry_row or {}).get('direction') == 'buy' else 'sell_only')
    seed_mode = 'both_sides' if grid_mode == 'both_sides' else 'single_side'
    policy_id = f"session_optimizer_{feat.get('session_name', 'session')}_{pair.lower()}_{risk_mode}"
    return policy_id, {
        'allow_new_basket': True,
        'grid_mode': grid_mode,
        'seed_mode': seed_mode,
        'step_pips': int(best['step_pips']) if float(best['step_pips']).is_integer() else best['step_pips'],
        'initial_lot': best['initial_lot'],
        'multiplier': round(best['multiplier'], 2),
        'max_trades_per_side': int(best['max_trades_per_side']),
        'basket_tp_currency': round(best['expected_capture'], 2),
        'max_gross_lots': round(best['max_gross_lots'], 2),
        'max_basket_drawdown_currency': round(best['max_basket_dd'], 2),
        'min_step_to_spread_ratio': round(best['min_step_to_spread_ratio'], 2),
        'min_free_margin_percent': round(best['min_free_margin_percent'], 1),
        'flatten_on_strong_avoid': True,
        'confidence': round(max(0.45, min(0.9, 1.0 - best['breakout_risk'] * 0.5)), 2),
        'reason': f"session_opt_{feat.get('session_name')}_range{best['predicted_range_pips']:.1f}_dd{best['expected_dd']:.1f}_tp{best['expected_capture']:.1f}_{risk_mode}",
    }


def choose_template(
    pair: str,
    pair_row: dict | None,
    entry_row: dict | None,
    session_features: dict[str, dict],
    *,
    account_equity: float,
    risk_mode: str,
    allow_gbpjpy_demo_override: bool,
) -> tuple[str, dict]:
    """Session-aware selector.

    First try the risk-budget optimizer, then fall back to legacy templates.
    """
    # Keep current GBPJPY demo override until we explicitly remove the live validation path.
    if allow_gbpjpy_demo_override and pair == "GBPJPY":
        return "gbpjpy_demo_fast_expansion", {
            "allow_new_basket": True,
            "grid_mode": "both_sides",
            "seed_mode": "both_sides",
            "step_pips": 8,
            "initial_lot": 0.01,
            "multiplier": 1.10,
            "max_trades_per_side": 4,
            "basket_tp_currency": 3.00,
            "max_gross_lots": 0.20,
            "max_basket_drawdown_currency": 150.0,
            "min_step_to_spread_ratio": 2.5,
            "min_free_margin_percent": 75.0,
            "flatten_on_strong_avoid": True,
            "confidence": 0.70,
            "reason": "persistent_demo_override_fast_expansion",
        }

    optimized = build_optimized_policy(
        pair,
        entry_row,
        session_features,
        account_equity=account_equity,
        risk_mode=risk_mode,
    )
    if optimized is not None:
        return optimized

    # 1. If pair policy blocks trading, no trade
    if not pair_row:
        return "no_trade", GRID_TEMPLATES["no_trade"]

    policy_action = pair_row.get("policy_action", "allow_trading")
    if policy_action != "allow_trading":
        return "no_trade", {
            **GRID_TEMPLATES["no_trade"],
            "reason": f"blocked_by_pair_policy:{policy_action}",
        }

    # 2. If no entry intent, be conservative and allow both sides
    if not entry_row:
        return "both_sides_conservative", {
            **GRID_TEMPLATES["both_sides_conservative"],
            "reason": "missing_entry_intent_default_conservative",
        }

    should_enter = bool(entry_row.get("should_enter", False))
    direction = entry_row.get("direction", "none")
    reason = str(entry_row.get("reason", ""))
    debug = entry_row.get("debug", {}) or {}

    # 3. If entry intent says no, but pair is tradable, use conservative both-sides if market isn't blocked.
    # Reason: two-sided grid can still mean-revert even if directional signal is weak.
    # But if the reason is dead chop or extreme vol, be more cautious.
    if not should_enter or direction == "none":
        if reason.startswith("vol_regime_dead_chop"):
            # Classic grid shines in consolidation, so prefer explicit consolidation templates
            atr_frac = float(debug.get("atr_frac_60", 0.0) or 0.0)
            if atr_frac <= 0.00022:
                return "classic_consolidation_dense", {
                    **GRID_TEMPLATES["classic_consolidation_dense"],
                    "reason": "dead_chop_dense_classic_consolidation",
                }
            if atr_frac <= 0.00035:
                return "classic_consolidation_normal", {
                    **GRID_TEMPLATES["classic_consolidation_normal"],
                    "reason": "dead_chop_normal_classic_consolidation",
                }
            return "classic_consolidation_light", {
                **GRID_TEMPLATES["classic_consolidation_light"],
                "reason": "dead_chop_light_classic_consolidation",
            }
        if reason.startswith("vol_regime_extreme_vol"):
            return "no_trade", {
                **GRID_TEMPLATES["no_trade"],
                "reason": "entry_signal_extreme_vol_no_trade",
            }
        return "both_sides_conservative", {
            **GRID_TEMPLATES["both_sides_conservative"],
            "reason": "no_direction_signal_but_pair_allowed",
        }

    # 4. Directional signal exists. Use one-sided conservative when signal is strong enough.
    alignment = float(debug.get("alignment_score", 0.0) or 0.0)
    trend_strength = float(debug.get("trend_strength", 0.0) or 0.0)

    # Strong directional signal: one-sided conservative
    if alignment >= 0.75 and trend_strength >= 0.0008:
        if direction == "buy":
            return "buy_only_conservative", {
                **GRID_TEMPLATES["buy_only_conservative"],
                "reason": f"strong_buy_signal_align{alignment:.2f}_trend{trend_strength:.4f}",
            }
        if direction == "sell":
            return "sell_only_conservative", {
                **GRID_TEMPLATES["sell_only_conservative"],
                "reason": f"strong_sell_signal_align{alignment:.2f}_trend{trend_strength:.4f}",
            }

    # Moderate directional signal: both sides normal
    return "both_sides_normal", {
        **GRID_TEMPLATES["both_sides_normal"],
        "reason": f"moderate_signal_keep_both_sides_align{alignment:.2f}",
    }


def main() -> int:
    args = parse_args()
    now_utc = datetime.now(timezone.utc)
    pair_policy = json.loads(PAIR_POLICY_FILE.read_text(encoding="utf-8")) if PAIR_POLICY_FILE.exists() else {}
    entry_intent = json.loads(ENTRY_INTENT_FILE.read_text(encoding="utf-8")) if ENTRY_INTENT_FILE.exists() else {}
    session_features = load_session_range_predictions() or load_session_range_features(now_utc)

    pair_map = {row.get("pair"): row for row in pair_policy.get("pair_policies", [])}
    entry_map = {row.get("pair"): row for row in entry_intent.get("pairs", [])}

    rows = []
    for pair in PAIRS:
        template_id, template = choose_template(
            pair,
            pair_map.get(pair),
            entry_map.get(pair),
            session_features,
            account_equity=args.account_equity,
            risk_mode=args.risk_mode,
            allow_gbpjpy_demo_override=args.allow_gbpjpy_demo_override,
        )
        rows.append(
            {
                "pair": pair,
                "allow_new_basket": template["allow_new_basket"],
                "policy_id": template_id,
                "grid_mode": template["grid_mode"],
                "seed_mode": template["seed_mode"],
                "step_pips": template["step_pips"],
                "initial_lot": template["initial_lot"],
                "multiplier": template["multiplier"],
                "max_trades_per_side": template["max_trades_per_side"],
                "basket_tp_currency": template["basket_tp_currency"],
                "max_gross_lots": template.get("max_gross_lots", 0.0),
                "max_basket_drawdown_currency": template.get("max_basket_drawdown_currency", 0.0),
                "min_step_to_spread_ratio": template.get("min_step_to_spread_ratio", 0.0),
                "min_free_margin_percent": template.get("min_free_margin_percent", 0.0),
                "flatten_on_strong_avoid": template["flatten_on_strong_avoid"],
                "confidence": template["confidence"],
                "reason": template["reason"],
                "session_name": session_features.get(pair, {}).get("session_name"),
                "predicted_range_pips": session_features.get(pair, {}).get("predicted_range_pips"),
                "recent_avg_range_pips": session_features.get(pair, {}).get("recent_avg_range_pips"),
                "expires_at_utc": mt5_utc_timestamp(now_utc + timedelta(minutes=EXPIRY_MINUTES)),
            }
        )

    payload = {
        "generated_at_utc": mt5_utc_timestamp(now_utc),
        "version": "grid_policy_v2",
        "model": "session_risk_optimizer_v1",
        "risk_mode": args.risk_mode,
        "account_equity": args.account_equity,
        "risk_budget_currency": round(args.account_equity * RISK_BUDGET_PCT[args.risk_mode], 2),
        "target_profit_currency": round(args.account_equity * TARGET_PROFIT_PCT[args.risk_mode], 2),
        "allow_gbpjpy_demo_override": args.allow_gbpjpy_demo_override,
        "session_name": infer_session_name(now_utc),
        "session_close_utc": get_session_close_utc(now_utc, infer_session_name(now_utc)),
        "managed_close_utc": get_managed_close_utc(now_utc, infer_session_name(now_utc), 30),
        "liquidate_utc": get_liquidate_utc(now_utc, infer_session_name(now_utc), 10),
        "pairs": rows,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
