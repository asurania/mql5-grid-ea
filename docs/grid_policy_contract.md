# Grid Policy Contract

## Purpose

Defines the Python-to-MQL5 handoff for basket/grid configuration.

This contract is separate from:
- pair event-risk policy
- entry intent

It answers:
- if a new basket is allowed
- whether the basket may be buy-only, sell-only, or both-sides
- what grid settings should be used for the basket

---

## Ownership

### Python master owns
- grid policy selection
- policy expiry
- policy versioning
- ML or rule-based selection logic

### MQL5 slave owns
- execution and basket management
- rejecting stale or invalid policy
- enforcing local hard safety caps

---

## File location

### Development mirror
- `runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json`

### MT5 common-files relative path
- `ForexSlave\\grid_policy.json`

---

## Schema

```json
{
  "generated_at_utc": "2026-04-15T21:00:00Z",
  "version": "grid_policy_v1",
  "model": "grid_policy_classifier_v1",
  "pairs": [
    {
      "pair": "GBPJPY",
      "allow_new_basket": true,
      "policy_id": "both_sides_conservative",
      "grid_mode": "both_sides",
      "step_pips": 18,
      "initial_lot": 0.01,
      "multiplier": 1.10,
      "max_trades_per_side": 3,
      "confidence": 0.72,
      "reason": "ml_grid_policy_both_sides_conservative",
      "expires_at_utc": "2026-04-15T21:05:00Z"
    }
  ]
}
```

---

## Top-level fields

- `generated_at_utc`: generation timestamp
- `version`: schema version
- `model`: source selector name (`static_templates_v1`, `grid_policy_classifier_v1`, etc.)
- `pairs`: per-pair policy rows

---

## Per-pair fields

- `pair`: trading symbol
- `allow_new_basket`: whether Python authorizes starting a new basket
- `policy_id`: selected template or model policy label
- `grid_mode`: one of:
  - `both_sides`
  - `buy_only`
  - `sell_only`
- `step_pips`: distance between grid entries
- `initial_lot`: first trade lot size
- `multiplier`: lot multiplier for subsequent trades on that side
- `max_trades_per_side`: maximum ladder depth for buy side and sell side independently
- `confidence`: optional probability/confidence score
- `reason`: human/debug explanation
- `expires_at_utc`: freshness deadline

---

## Slave enforcement rules

MQL5 should reject the policy row if:
- `pair` missing
- `allow_new_basket == false`
- `grid_mode` invalid
- `step_pips <= 0`
- `initial_lot <= 0`
- `multiplier < 1.0`
- `max_trades_per_side < 1`
- `expires_at_utc` invalid or expired

Even with a valid row, MQL5 may still reject execution if:
- spread too wide
- pair risk policy blocks new entries
- entry intent missing or contradictory
- local exposure caps exceeded
- broker rejects size or volume step

---

## Recommended local hard caps

Even if Python requests larger values, MQL5 should enforce configured upper bounds, for example:
- `step_pips >= InpMinGridStepPips`
- `initial_lot <= InpMaxInitialLot`
- `multiplier <= InpMaxGridMultiplier`
- `max_trades_per_side <= InpMaxTradesPerSide`

This preserves fail-safe behavior.

---

## Interaction with other Python-owned files

### Pair risk policy
If pair risk policy blocks entries, grid policy should be ignored for new basket creation.

### Entry intent
Entry intent decides directional authorization for first basket entry.
Grid policy decides basket configuration.

Recommended order for first-entry creation:
1. load pair risk policy
2. load entry intent
3. load grid policy
4. validate all are fresh and mutually compatible
5. apply local risk overlay
6. submit order(s)

---

## V1 simplification

For v1:
- use one policy row per pair
- one `multiplier` shared by both sides
- one `step_pips` shared by both sides
- one `max_trades_per_side`
- no separate TP mode yet

Later versions may add:
- `buy_step_pips`
- `sell_step_pips`
- `buy_multiplier`
- `sell_multiplier`
- `basket_tp_currency`
- `max_gross_lots`
- `time_stop_minutes`

---

## Recommended immediate implementation

Before ML selection exists, Python can publish a static template-based `grid_policy.json` so the MQL5 side can be built and tested now.
