from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAG_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_core_v1_diagnostics.json"
GUARDED_FILE = ROOT / "config" / "pair_session_portfolio_core_v1_guarded.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "portfolio_core_v1_guardrail_plan.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    diag = load_json(DIAG_FILE)
    guarded = load_json(GUARDED_FILE)
    slot_diag = diag.get('slot_diagnostics', {})
    overrides = guarded.get('guardrails', {}).get('slot_overrides', {})

    recommendations = []
    for slot, metrics in slot_diag.items():
        slot_override = overrides.get(slot, {})
        notes = []
        if metrics.get('forced_close_rate', 0.0) >= 0.45:
            notes.append('high_forced_close_rate')
        if metrics.get('worst_segment_pnl', 0.0) <= -90.0:
            notes.append('fat_tail_segment_loss')
        if slot_override:
            notes.append('guardrail_override_present')
        recommendations.append({
            'slot': slot,
            'forced_close_rate': metrics.get('forced_close_rate', 0.0),
            'worst_segment_pnl': metrics.get('worst_segment_pnl', 0.0),
            'override': slot_override,
            'notes': notes,
        })

    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'global_guardrails': guarded.get('guardrails', {}),
        'slot_recommendations': recommendations,
        'next_actions': [
            'apply slot-level caps in execution bridge and future portfolio simulators',
            'block new entries after daily loss cap breach',
            'limit simultaneous active slots to reduce correlated stress',
        ],
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
