# Entry Intent Contract

## Purpose

Defines the Python-to-MT5 handoff for first-entry directional authorization.

This file is separate from:
- pair risk policy
- core portfolio policy

It answers:
- whether a first basket may be started now
- which side is authorized
- how fresh the intent is

## File location

### Development mirror
- `data/live/policy/entry_intent.json`

### MT5 common-files relative target
- `ForexSlave\\entry_intent.json`

## Schema

```json
{
  "generated_at_utc": "2026-04-22T00:00:00Z",
  "version": "entry_intent_v1",
  "pairs": [
    {
      "pair": "GBPUSD",
      "enabled": true,
      "allow_first_entry": true,
      "direction": "buy",
      "confidence": 0.71,
      "reason": "python_entry_intent_buy_alignment",
      "expires_at_utc": "2026-04-22T00:15:00Z"
    }
  ]
}
```

## Per-pair fields
- `pair`: symbol
- `enabled`: whether this row is active
- `allow_first_entry`: whether a new first basket may be started
- `direction`: `buy` or `sell`
- `confidence`: optional debug/confidence field
- `reason`: human/debug reason
- `expires_at_utc`: freshness deadline

## Slave rules
MT5 should reject a row if:
- pair missing
- row disabled
- `allow_first_entry == false`
- direction invalid
- expiry invalid or expired

If row is stale or invalid:
- do not start a new basket
- continue safe management of existing positions
