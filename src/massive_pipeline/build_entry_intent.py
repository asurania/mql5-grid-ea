from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

ROOT = Path(__file__).resolve().parents[2]
PAIR_POLICY_FILE = ROOT / "data" / "live" / "policy" / "pair_risk_policy.json"
OUT_FILE = ROOT / "data" / "live" / "policy" / "entry_intent.json"
PAIRS = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]


def build_pair_intent(pair: str, policy_map: dict[str, dict], now_utc: datetime) -> dict:
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

    payload = {
        "generated_at_utc": now_utc.isoformat(),
        "version": "entry_intent_v1",
        "pairs": [build_pair_intent(pair, policy_map, now_utc) for pair in PAIRS],
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
