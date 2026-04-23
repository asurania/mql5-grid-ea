from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.backtest_pair_session_policy import (
    build_policy,
    build_risk,
    build_session_filter,
    load_json,
    load_price_frame,
    run_segment,
    segmented_rows,
)
from massive_pipeline.trading_config import load_config

ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_FILE = ROOT / "config" / "pair_session_portfolio_v3.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_v3_summary.json"


def main() -> int:
    config = load_config()
    portfolio = load_json(PORTFOLIO_FILE)
    results = []
    portfolio_total = 0.0
    portfolio_forced_close = 0

    for item in portfolio.get("portfolio", []):
        if not item.get("enabled", True):
            continue
        pair = item["pair"]
        session_name = item["session"]
        frame = load_price_frame(pair, 120000)
        session_filter = build_session_filter(portfolio, session_name)
        segments = [seg for seg in segmented_rows(frame, session_filter) if len(seg) >= 30]
        policy = build_policy(item)
        risk = build_risk(config, item)
        pip_size_map = config["pip_config"]["pip_size"]
        pip_value_map = config["pip_config"]["pip_value_per_001_lot"]
        pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith("JPY") else 0.0001))
        pip_value = float(pip_value_map.get(pair, pip_value_map.get("GBPUSD", 0.13)))
        runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments]
        total = sum(r["buy_realized_pnl"] + r["sell_realized_pnl"] for r in runs)
        forced = sum(1 for r in runs if r.get("buy_closed_reason") == "forced_session_close" or r.get("sell_closed_reason") == "forced_session_close")
        portfolio_total += total
        portfolio_forced_close += forced
        results.append({
            "pair": pair,
            "session": session_name,
            "segments": len(runs),
            "total_pnl": total,
            "forced_close_count": forced,
            "sample": runs[:10],
            "policy": item,
        })

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "portfolio_total_pnl": portfolio_total,
        "portfolio_forced_close_count": portfolio_forced_close,
        "results": results,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
