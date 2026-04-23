from __future__ import annotations

import json
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
    segmented_rows,
)
from massive_pipeline.legacy_grid_parity import GridPolicy, VariableEAConfig
from massive_pipeline.trading_config import load_config

ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_v1.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_stressed_slot_retune.json"
TARGETS = [("NZDUSD", "new_york"), ("GBPJPY", "london"), ("GBPUSD", "new_york")]
FORCED_CLOSE_PENALTY = 60.0


def build_policy(session_cfg: dict) -> GridPolicy:
    return GridPolicy(
        step_mode="fixed",
        fixed_step_pips=float(session_cfg.get("step_pips", 10.0)),
        variable_steps_pips=(float(session_cfg.get("step_pips", 10.0)),),
        multiplier=float(session_cfg.get("multiplier", 1.1)),
        initial_lot=float(session_cfg.get("initial_lot", 0.01)),
        max_lot=5.0,
        max_levels_buy=int(session_cfg.get("grid_levels", 6)),
        max_levels_sell=int(session_cfg.get("grid_levels", 6)),
        tp_pips_buy=float(session_cfg.get("tp_pips", 4.0)),
        tp_pips_sell=float(session_cfg.get("tp_pips", 4.0)),
        sl_pips=float(session_cfg.get("sl_pips", 50.0)),
        variable_ea=VariableEAConfig(enabled=False, mode="managed", step_windows=(), tp_windows=()),
    )


def evaluate(pair: str, session_name: str, session_cfg: dict, config: dict, portfolio_root: dict) -> dict:
    frame = load_price_frame(pair, 120000)
    session_filter = build_session_filter(portfolio_root, session_name)
    segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= 30]
    pip_size_map = config["pip_config"]["pip_size"]
    pip_value_map = config["pip_config"]["pip_value_per_001_lot"]
    pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith("JPY") else 0.0001))
    pip_value = float(pip_value_map.get(pair, pip_value_map.get("GBPUSD", 0.13)))
    policy = build_policy(session_cfg)
    risk = build_risk(config, session_cfg)
    runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
    total = sum(r["buy_realized_pnl"] + r["sell_realized_pnl"] for r in runs)
    forced = sum(1 for r in runs if r.get("buy_closed_reason") == "forced_session_close" or r.get("sell_closed_reason") == "forced_session_close")
    return {
        "pair": pair,
        "session": session_name,
        "params": session_cfg,
        "segments": len(runs),
        "total_pnl": total,
        "forced_close_count": forced,
        "score": total - forced * FORCED_CLOSE_PENALTY,
    }


def variants(cfg: dict):
    step = float(cfg.get("step_pips", 10.0))
    tp = float(cfg.get("tp_pips", 4.0))
    mult = float(cfg.get("multiplier", 1.1))
    levels = int(cfg.get("grid_levels", 6))
    for step_scale in (0.85, 0.95, 1.0, 1.1, 1.2):
        for tp_scale in (0.8, 0.9, 1.0, 1.1):
            for mult_delta in (-0.04, -0.02, 0.0, 0.02):
                for level_delta in (-2, -1, 0, 1):
                    out = dict(cfg)
                    out["step_pips"] = round(max(1.0, step * step_scale), 2)
                    out["tp_pips"] = round(max(0.5, tp * tp_scale), 2)
                    out["multiplier"] = round(max(1.01, mult + mult_delta), 3)
                    out["grid_levels"] = max(2, levels + level_delta)
                    yield out


def main() -> int:
    config = load_config()
    portfolio_root = load_json(PORTFOLIO_FILE)
    items = {(x['pair'], x['session']): x for x in portfolio_root['portfolio']}
    out = []
    for pair, session_name in TARGETS:
        base = items[(pair, session_name)]
        trials = [evaluate(pair, session_name, v, config, portfolio_root) for v in variants(base)]
        trials.sort(key=lambda x: x['score'], reverse=True)
        out.append({
            'pair': pair,
            'session': session_name,
            'best': trials[:5],
        })
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'forced_close_penalty': FORCED_CLOSE_PENALTY,
        'results': out,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
