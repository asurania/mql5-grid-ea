from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json


def mt5_utc_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y.%m.%d %H:%M:%S")

ACTIONS_FILE = Path("data/live/event_risk/event_risk_actions.json")
OUT_DIR = Path("data/live/policy")
PAIR_ORDER = ["EURJPY", "GBPJPY", "GBPUSD", "NZDUSD"]
ACTION_PRIORITY = {
    "avoid_session_strong": 3,
    "avoid_session": 2,
    "review_or_halt_new_entries": 1,
    "do_not_trigger_avoid_session": 0,
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc)
    payload = json.loads(ACTIONS_FILE.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])

    pair_policies = []
    for pair in PAIR_ORDER:
        pair_rows = [r for r in rows if r.get("pair") == pair]
        if not pair_rows:
            pair_policies.append(
                {
                    "pair": pair,
                    "policy_action": "allow_trading",
                    "policy_band": "no_active_event_risk",
                    "max_score_avoid_session": 0.0,
                    "trigger_event_id": None,
                    "trigger_event_name": None,
                    "trigger_event_timestamp_utc": None,
                    "generated_at_utc": mt5_utc_timestamp(now_utc),
                }
            )
            continue

        best = max(
            pair_rows,
            key=lambda r: (
                ACTION_PRIORITY.get(r.get("risk_action"), -1),
                float(r.get("score_avoid_session", 0.0)),
            ),
        )

        action = best.get("risk_action")
        if action == "avoid_session_strong":
            policy_action = "block_new_entries_and_flag_strong_avoid"
        elif action == "avoid_session":
            policy_action = "block_new_entries"
        elif action == "review_or_halt_new_entries":
            policy_action = "soft_halt_new_entries"
        else:
            policy_action = "allow_trading"

        pair_policies.append(
            {
                "pair": pair,
                "policy_action": policy_action,
                "policy_band": best.get("risk_band"),
                "max_score_avoid_session": best.get("score_avoid_session", 0.0),
                "trigger_event_id": best.get("event_id"),
                "trigger_event_name": best.get("event_name"),
                "trigger_event_timestamp_utc": best.get("event_timestamp_utc"),
                "generated_at_utc": mt5_utc_timestamp(now_utc),
            }
        )

    out = {
        "generated_at_utc": mt5_utc_timestamp(now_utc),
        "source_model": payload.get("model", "xgb_y_avoid_session"),
        "threshold_version": payload.get("threshold_version", "avoid_session_v1"),
        "pair_policies": pair_policies,
    }
    (OUT_DIR / "pair_risk_policy.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
