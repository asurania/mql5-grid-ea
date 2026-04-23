# Pair Risk Policy Contract

## Purpose

Defines the Python-to-MT5 handoff for pair/session risk gating.

This file tells the MT5 slave whether a pair is allowed to start new baskets at all, independent of entry direction and grid configuration.

## File location

### Development mirror
- `data/live/policy/pair_risk_policy.json`

### MT5 common-files relative target
- `ForexSlave\\pair_risk_policy.json`

## Schema

```json
{
  "generated_at_utc": "2026-04-22T00:00:00Z",
  "version": "pair_risk_policy_v1",
  "pairs": [
    {
      "pair": "GBPUSD",
      "enabled": true,
      "allow_new_entries": true,
      "policy_action": "allow_trading",
      "reason": "session_and_risk_ok",
      "expires_at_utc": "2026-04-22T00:15:00Z"
    }
  ]
}
```

## Per-pair fields
- `pair`: symbol
- `enabled`: row enabled flag
- `allow_new_entries`: whether slave may start new baskets
- `policy_action`: one of:
  - `allow_trading`
  - `soft_halt_new_entries`
  - `block_new_entries`
  - `block_new_entries_strong`
- `reason`: debug reason
- `expires_at_utc`: freshness deadline

## Slave rules
Reject new basket creation if:
- row missing
- row disabled
- stale row
- `allow_new_entries == false`
- `policy_action != allow_trading`

Existing basket management may continue according to the broader slave logic.
