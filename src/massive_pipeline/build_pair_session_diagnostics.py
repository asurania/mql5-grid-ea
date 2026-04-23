from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKTEST_SUMMARY = ROOT / "data" / "backtest" / "legacy_parity" / "normalized_legacy_parity_7pair_summary.json"
POLICY_FILE = ROOT / "config" / "pair_session_policy.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "pair_session_diagnostics.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    summary = load_json(BACKTEST_SUMMARY)
    policy = load_json(POLICY_FILE)
    pair_policies = policy.get("pairs", {})
    default_policy = policy.get("default", {})

    diagnostics = []
    for row in summary.get("results", []):
        pair = row.get("pair")
        if row.get("missing_data"):
            diagnostics.append({
                "pair": pair,
                "missing_data": True,
            })
            continue
        pair_policy = pair_policies.get(pair, {})
        enabled_sessions = [name for name, cfg in pair_policy.items() if isinstance(cfg, dict) and cfg.get("enabled")]
        total_buy = float(row.get("total_buy_realized_pnl", 0.0))
        total_sell = float(row.get("total_sell_realized_pnl", 0.0))
        total = total_buy + total_sell
        side_bias = "sell" if total_sell > total_buy else "buy"
        segment_results = row.get("segment_results", [])
        forced_close_count = sum(1 for seg in segment_results if seg.get("buy_closed_reason") == "forced_session_close" or seg.get("sell_closed_reason") == "forced_session_close")
        diagnostics.append({
            "pair": pair,
            "missing_data": False,
            "enabled_sessions": enabled_sessions,
            "policy_default": default_policy,
            "pair_policy": pair_policy,
            "segments": row.get("segments", 0),
            "total_buy_realized_pnl": total_buy,
            "total_sell_realized_pnl": total_sell,
            "total_realized_pnl": total,
            "side_bias": side_bias,
            "forced_close_count": forced_close_count,
            "sample_segment_count": len(segment_results),
        })

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "diagnostics": diagnostics,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
