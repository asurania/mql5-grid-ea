from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

ROOT = Path(__file__).resolve().parents[2]
PAIR_POLICY_FILE = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
ENTRY_INTENT_FILE = ROOT / "data" / "live" / "policy" / "entry_intent.json"
OUT_FILE = ROOT / "data" / "live" / "policy" / "grid_policy.json"
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
EXPIRY_MINUTES = 5

# Static template library for v1.
# Later this will be selected by ML.
GRID_TEMPLATES = {
    "no_trade": {
        "allow_new_basket": False,
        "grid_mode": "both_sides",
        "step_pips": 0,
        "initial_lot": 0.0,
        "multiplier": 1.0,
        "max_trades_per_side": 0,
        "confidence": 1.0,
        "reason": "no_trade_template",
    },
    "both_sides_conservative": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "step_pips": 18,
        "initial_lot": 0.01,
        "multiplier": 1.10,
        "max_trades_per_side": 3,
        "confidence": 0.65,
        "reason": "static_both_sides_conservative",
    },
    "both_sides_normal": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "step_pips": 12,
        "initial_lot": 0.01,
        "multiplier": 1.20,
        "max_trades_per_side": 5,
        "confidence": 0.65,
        "reason": "static_both_sides_normal",
    },
    "both_sides_wide_light": {
        "allow_new_basket": True,
        "grid_mode": "both_sides",
        "step_pips": 22,
        "initial_lot": 0.01,
        "multiplier": 1.05,
        "max_trades_per_side": 4,
        "confidence": 0.60,
        "reason": "static_both_sides_wide_light",
    },
    "buy_only_conservative": {
        "allow_new_basket": True,
        "grid_mode": "buy_only",
        "step_pips": 15,
        "initial_lot": 0.01,
        "multiplier": 1.15,
        "max_trades_per_side": 4,
        "confidence": 0.60,
        "reason": "static_buy_only_conservative",
    },
    "sell_only_conservative": {
        "allow_new_basket": True,
        "grid_mode": "sell_only",
        "step_pips": 15,
        "initial_lot": 0.01,
        "multiplier": 1.15,
        "max_trades_per_side": 4,
        "confidence": 0.60,
        "reason": "static_sell_only_conservative",
    },
}


def choose_template(pair_row: dict | None, entry_row: dict | None) -> tuple[str, dict]:
    """Simple rule-based template selector for v1.

    Uses pair risk policy + entry intent to pick a static template.
    This is a bridge until ML selection exists.
    """
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
            return "both_sides_wide_light", {
                **GRID_TEMPLATES["both_sides_wide_light"],
                "reason": "entry_signal_dead_chop_use_wide_light",
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
    now_utc = datetime.now(timezone.utc)
    pair_policy = json.loads(PAIR_POLICY_FILE.read_text(encoding="utf-8")) if PAIR_POLICY_FILE.exists() else {}
    entry_intent = json.loads(ENTRY_INTENT_FILE.read_text(encoding="utf-8")) if ENTRY_INTENT_FILE.exists() else {}

    pair_map = {row.get("pair"): row for row in pair_policy.get("pair_policies", [])}
    entry_map = {row.get("pair"): row for row in entry_intent.get("pairs", [])}

    rows = []
    for pair in PAIRS:
        template_id, template = choose_template(pair_map.get(pair), entry_map.get(pair))
        rows.append(
            {
                "pair": pair,
                "allow_new_basket": template["allow_new_basket"],
                "policy_id": template_id,
                "grid_mode": template["grid_mode"],
                "step_pips": template["step_pips"],
                "initial_lot": template["initial_lot"],
                "multiplier": template["multiplier"],
                "max_trades_per_side": template["max_trades_per_side"],
                "confidence": template["confidence"],
                "reason": template["reason"],
                "expires_at_utc": (now_utc + timedelta(minutes=EXPIRY_MINUTES)).isoformat(),
            }
        )

    payload = {
        "generated_at_utc": now_utc.isoformat(),
        "version": "grid_policy_v1",
        "model": "static_templates_v1",
        "pairs": rows,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
