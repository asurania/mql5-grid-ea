# core_v1.1 Guarded Execution Bridge Contract

## Purpose

Defines how the Python research layer should hand off the validated `core_v1.1_guarded` portfolio to the MT5 slave execution layer.

This contract is specifically for the current guarded research baseline:
- NZDUSD New York
- GBPJPY London
- GBPUSD New York

It extends the existing ideas in:
- `docs/mql5_slave_architecture.md`
- `docs/grid_policy_contract.md`

## Design intent

Python remains the control plane.
MT5 remains the execution plane.

Python owns:
- session selection
- pair enablement
- grid parameters
- lot sizing resolution
- guardrail publication
- policy freshness/expiry

MT5 owns:
- reading policy files
- validating freshness
- order placement
- basket execution
- local broker safety
- hard enforcement of published limits

## Operational baseline

Current research-grade operational baseline is `core_v1.1_guarded`.

### Core slots
- `NZDUSD:new_york`
- `GBPJPY:london`
- `GBPUSD:new_york`

### Guardrail intent
- preserve most of unguarded performance
- reduce forced-close stress materially
- protect GBPJPY London from fat-tail segment losses
- protect GBPUSD New York with earlier managed-close behavior

## Recommended handoff files

Use three Python-owned handoff files:

1. `pair_risk_policy.json`
   - whether a pair/session is allowed right now
   - stale/fresh blocking semantics

2. `entry_intent.json`
   - direction authorization for first basket entry
   - optional confidence/reason

3. `core_portfolio_policy.json`
   - current guarded execution configuration for each active pair/session slot

This document defines `core_portfolio_policy.json`.

## File location

### Development mirror
- `data/live/policy/core_portfolio_policy.json`

### MT5 common-files relative target
- `ForexSlave\\core_portfolio_policy.json`

## Top-level schema

```json
{
  "generated_at_utc": "2026-04-22T00:00:00Z",
  "version": "core_portfolio_policy_v1",
  "source": "core_v1.1_guarded",
  "account": {
    "equity_reference": 10000.0,
    "lot_sizing_mode": "equity_scaled"
  },
  "guardrails": {
    "max_active_slots": 3,
    "max_total_initial_lots": 0.04,
    "max_total_drawdown_currency": 300.0,
    "daily_loss_cap_currency": 220.0,
    "session_loss_cap_currency": 120.0,
    "flatten_on_account_breach": true,
    "block_new_entries_after_daily_cap": true
  },
  "pairs": []
}
```

## Per-pair session row schema

```json
{
  "pair": "GBPUSD",
  "session_name": "new_york",
  "enabled": true,
  "allow_new_basket": true,
  "grid_mode": "both_sides",
  "seed_mode": "single_side",
  "step_pips": 5.78,
  "initial_lot": 0.01,
  "initial_lot_mode": "equity_scaled",
  "base_equity": 10000.0,
  "multiplier": 1.13,
  "max_trades_per_side": 4,
  "basket_tp_pips": 2.04,
  "basket_sl_pips": 40.0,
  "max_basket_drawdown_currency": 110.0,
  "max_slot_drawdown_currency": 110.0,
  "managed_close_minutes": 75,
  "session_close_behavior": "managed_close_only",
  "flatten_on_account_breach": true,
  "expires_at_utc": "2026-04-22T00:15:00Z",
  "reason": "core_v1.1_guarded_gbpusd_ny"
}
```

## Field semantics

### Shared execution fields
- `pair`: broker symbol identity
- `session_name`: `asia|london|new_york`
- `enabled`: whether this slot is active in the current portfolio
- `allow_new_basket`: whether MT5 may start a new basket
- `grid_mode`: currently use `both_sides` for parity-style execution unless explicitly changed later
- `seed_mode`: `single_side` by default, direction comes from Python entry intent
- `step_pips`: grid spacing
- `initial_lot`: resolved first lot size for the current equity context
- `initial_lot_mode`: published for traceability
- `base_equity`: anchor used by Python for lot scaling
- `multiplier`: next-leg lot progression multiplier
- `max_trades_per_side`: hard side depth cap after all slot guardrails applied
- `basket_tp_pips`: weighted basket TP target
- `basket_sl_pips`: weighted basket SL distance
- `max_basket_drawdown_currency`: pair basket floating-loss ceiling
- `max_slot_drawdown_currency`: execution-time alias for slot-specific DD stop
- `managed_close_minutes`: minutes before session end when MT5 must stop aggressive management and shift into managed close
- `session_close_behavior`: expected value for current design is `managed_close_only`
- `flatten_on_account_breach`: if account-level guardrail trips, flatten this slot
- `expires_at_utc`: freshness deadline
- `reason`: debug lineage string

### Optional slot-protection fields
- `tail_loss_guard_currency`: especially for GBPJPY London
- `forced_close_rate_warn`: especially for GBPUSD New York
- `no_new_entries_after_utc`: optional future field for hard late-session entry suppression

## Current recommended published rows

### NZDUSD New York
- enabled
- standard guarded core settings
- no special behavior override beyond slot DD cap

### GBPJPY London
- enabled
- max trades per side should publish as `8`
- publish tighter drawdown ceiling
- publish `tail_loss_guard_currency: 90.0`

### GBPUSD New York
- enabled
- publish `managed_close_minutes: 75`
- keep max trades per side at `4`
- publish tighter slot DD cap
- optionally publish `forced_close_rate_warn: 0.45` for telemetry/monitoring only

## MT5 slave enforcement expectations

MT5 should reject or block a row if:
- policy is stale or missing
- `enabled == false`
- `allow_new_basket == false`
- `expires_at_utc` has passed
- `step_pips <= 0`
- `initial_lot <= 0`
- `multiplier < 1.0`
- `max_trades_per_side < 1`
- `max_basket_drawdown_currency <= 0`
- `managed_close_minutes < 0`

Even with a valid row, MT5 may still block for:
- spread too wide
- free margin too low
- broker volume step invalid
- symbol unavailable
- local hard fail-safe limits exceeded

## Execution order of operations

For each managed pair/session:

1. read `pair_risk_policy.json`
2. read `entry_intent.json`
3. read `core_portfolio_policy.json`
4. validate freshness and pair/session alignment
5. check local broker/risk overlay
6. allow or deny new basket creation
7. continue management for existing baskets according to current slot policy
8. shift to managed-close behavior when `managed_close_minutes` threshold is reached

## Current implementation recommendation

### Phase 1
Publish `core_portfolio_policy.json` from Python only.
Do not implement any extra inferred logic inside MT5.

### Phase 2
Teach MT5 slave to:
- read slot rows
- enforce max depth
- enforce basket DD cap
- honor `managed_close_minutes`
- deny new baskets when blocked by risk or stale policy

### Phase 3
Add optional fields for:
- hard no-new-entry cutoff late in session
- reduced multiplier in late-session mode
- dynamic slot disable after repeated stress

## Current practical next build step

Implement a Python exporter that transforms `pair_session_portfolio_core_v1_1_guarded.json` into `data/live/policy/core_portfolio_policy.json` in this contract shape.

That exporter should:
- resolve current equity-scaled initial lots
- apply slot guardrails before publishing
- stamp `generated_at_utc` and `expires_at_utc`
- emit only active slots
