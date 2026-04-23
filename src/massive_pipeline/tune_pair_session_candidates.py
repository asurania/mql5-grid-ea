from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.backtest_pair_session_policy import (
    build_risk,
    build_session_filter,
    load_json,
    load_price_frame,
    run_segment,
    to_windows,
)
from massive_pipeline.legacy_grid_parity import GridPolicy, VariableEAConfig
from massive_pipeline.trading_config import load_config

ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "config" / "pair_session_policy_pruned.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "pair_session_tuning_candidates.json"
TARGETS = [
    ("AUDNZD", "london"),
    ("GBPJPY", "asia"),
    ("GBPJPY", "london"),
    ("GBPUSD", "london"),
    ("GBPUSD", "new_york"),
    ("NZDUSD", "asia"),
    ("NZDUSD", "new_york"),
    ("AUDUSD", "new_york"),
    ("USDJPY", "new_york"),
]


def segmented_rows(frame: pl.DataFrame, session_filter) -> list[list[dict]]:
    from massive_pipeline.backtest_pair_session_policy import segmented_rows as _seg
    return _seg(frame, session_filter)


def build_policy(session_cfg: dict) -> GridPolicy:
    step_mode = session_cfg.get("step_mode", "fixed")
    step_pips = float(session_cfg.get("step_pips", 10.0))
    variable_steps = tuple(float(x["value"]) for x in session_cfg.get("variable_step_schedule", [])) or (step_pips,)
    return GridPolicy(
        step_mode="fixed" if step_mode == "fixed" else "variable",
        fixed_step_pips=step_pips,
        variable_steps_pips=variable_steps,
        multiplier=float(session_cfg.get("multiplier", 1.1)),
        initial_lot=float(session_cfg.get("initial_lot", 0.01)),
        max_lot=5.0,
        max_levels_buy=int(session_cfg.get("grid_levels", 6)),
        max_levels_sell=int(session_cfg.get("grid_levels", 6)),
        tp_pips_buy=float(session_cfg.get("tp_pips", 4.0)),
        tp_pips_sell=float(session_cfg.get("tp_pips", 4.0)),
        sl_pips=float(session_cfg.get("sl_pips", 50.0)),
        variable_ea=VariableEAConfig(
            enabled=bool(session_cfg.get("variable_step_schedule") or session_cfg.get("variable_tp_schedule")),
            mode="managed",
            step_windows=to_windows(session_cfg.get("variable_step_schedule", [])),
            tp_windows=to_windows(session_cfg.get("variable_tp_schedule", [])),
        ),
    )


def evaluate(pair: str, session_name: str, session_cfg: dict, config: dict, policy_root: dict, max_rows: int = 120000) -> dict:
    frame = load_price_frame(pair, max_rows)
    session_filter = build_session_filter(policy_root, session_name)
    segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= 30]
    pip_size_map = config["pip_config"]["pip_size"]
    pip_value_map = config["pip_config"]["pip_value_per_001_lot"]
    pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith("JPY") else 0.0001))
    pip_value = float(pip_value_map.get(pair, pip_value_map.get("GBPUSD", 0.13)))
    policy = build_policy(session_cfg)
    risk = build_risk(config, session_cfg)
    results = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
    total = sum(r["buy_realized_pnl"] + r["sell_realized_pnl"] for r in results)
    forced = sum(1 for r in results if r.get("buy_closed_reason") == "forced_session_close" or r.get("sell_closed_reason") == "forced_session_close")
    return {
        "pair": pair,
        "session": session_name,
        "params": session_cfg,
        "segments": len(results),
        "total_pnl": total,
        "forced_close_count": forced,
        "score": total - forced * 25.0,
    }


def variants(cfg: dict):
    step = float(cfg.get("step_pips", 10.0))
    tp = float(cfg.get("tp_pips", 4.0))
    mult = float(cfg.get("multiplier", 1.1))
    levels = int(cfg.get("grid_levels", 6))
    dd = float(cfg.get("drawdown_limit_currency", 150.0))
    for step_scale in (0.85, 1.0, 1.15):
        for tp_scale in (0.85, 1.0, 1.15):
            for mult_delta in (-0.03, 0.0, 0.03):
                for level_delta in (-1, 0, 1):
                    out = dict(cfg)
                    out["step_pips"] = round(max(1.0, step * step_scale), 2)
                    out["tp_pips"] = round(max(0.5, tp * tp_scale), 2)
                    out["multiplier"] = round(max(1.01, mult + mult_delta), 3)
                    out["grid_levels"] = max(2, levels + level_delta)
                    out["drawdown_limit_currency"] = round(dd, 2)
                    yield out


def main() -> int:
    config = load_config()
    policy_root = load_json(POLICY_FILE)
    best = []
    for pair, session_name in TARGETS:
        session_cfg = policy_root["pairs"][pair][session_name]
        trials = [evaluate(pair, session_name, v, config, policy_root) for v in variants(session_cfg)]
        trials.sort(key=lambda x: x["score"], reverse=True)
        best.append({
            "pair": pair,
            "session": session_name,
            "best": trials[:5],
        })
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidates": best,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
