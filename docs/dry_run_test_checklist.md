# Dry-Run Integration Checklist

## Purpose

Use this checklist to validate the Python-master to MQL5-slave control loop before enabling live trading.

Assumption:
- `InpEnableLiveTrading = false`

That means the EA should log dry-run intent instead of sending real orders.

## Test objective

Confirm that the full pipeline behaves correctly across:
- pair risk policy generation
- entry intent generation
- grid policy generation
- MT5 handoff publishing for all 3 files
- MQL5 pair policy loading
- MQL5 entry intent loading
- MQL5 grid policy loading
- execution gate decisions
- risk overlay decisions
- dry-run first-entry decisions
- dry-run basket expansion decisions
- dry-run basket exit / flatten decisions

---

## Pre-test setup

### Python side
Run:

```bash
/home/asurani/.openclaw/workspace/.venv-forex/bin/python src/massive_pipeline/run_event_risk_master.py
```

Confirm artifacts exist:

### Live policy outputs
- `data/live/policy/pair_risk_policy.json`
- `data/live/policy/entry_intent.json`
- `data/live/policy/grid_policy.json`

### MT5 handoff mirror
- `runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json`

### Validate artifact freshness
Check that all 3 files:
- have recent `generated_at_utc`
- have per-pair rows for all 4 pairs
- have valid `expires_at_utc` values where applicable

### MQL5 side
Confirm:
- EA attached to chart
- `InpEnableLiveTrading = false`
- `InpPolicyFilePath = ForexSlave\\pair_risk_policy.json`
- terminal can access common files path being used for the test
- `entry_intent.json` and `grid_policy.json` are in the same common-files folder

---

## Test cases

## A. File handoff and freshness

### 1. Happy path, all files present and fresh
Goal:
- all 3 published files are present
- all parse correctly
- pair policy allows trading
- entry intent gives a valid direction
- grid policy is valid
- risk overlay passes
- no open basket exists

Expected result:
- no real trade sent
- logs contain:
  - `ALLOW_NEW_TRADE`
  - `GRID_FIRST_ENTRY_SIGNAL`
  - `GRID_DRY_RUN_ENTRY`
- first-entry log should include:
  - direction
  - lots
  - policy_id
  - grid_mode
  - step_pips
  - multiplier
  - max_trades_per_side

### 2. Missing pair policy file
Goal:
- temporarily remove or rename published `pair_risk_policy.json`

Expected result:
- policy reader reports missing/invalid state
- execution gate blocks new trades
- log indicates fail-closed reason
- no dry-run entry log

### 3. Missing entry intent file
Goal:
- temporarily remove or rename published `entry_intent.json`

Expected result:
- first entry is skipped
- log shows entry intent unavailable or expired/missing
- no dry-run entry log

### 4. Missing grid policy file
Goal:
- temporarily remove or rename published `grid_policy.json`

Expected result:
- first entry is skipped
- log shows `grid policy invalid` or missing reason
- no dry-run entry log
- basket expansion should also be blocked

### 5. Expired entry intent
Goal:
- force `expires_at_utc` in `entry_intent.json` to a past time

Expected result:
- `EntryIntentReader` rejects intent
- `GridManager` logs skip reason related to expired intent
- no dry-run entry log

### 6. Expired grid policy
Goal:
- force `expires_at_utc` in `grid_policy.json` to a past time

Expected result:
- `GridPolicyReader` rejects the row
- first entry is skipped
- basket management is skipped
- log shows grid policy expired

---

## B. First-entry behavior

### 7. Direction missing or `none`
Goal:
- use an intent row with `should_enter = true` but `direction = none`

Expected result:
- slave refuses first entry
- log shows skip reason for missing/invalid direction
- no dry-run entry log

### 8. Policy block
Goal:
- pair policy set to `block_new_entries` or stronger

Expected result:
- log contains:
  - `BLOCK_NEW_TRADE`
  - `GRID_SKIP_NEW_ENTRY`
- no dry-run entry log
- no real trade sent

### 9. Grid mode mismatch: buy_only vs sell signal
Goal:
- set `grid_mode = buy_only` in `grid_policy.json`
- set entry intent direction to `sell`

Expected result:
- first entry skipped
- log says grid policy buy_only but signal is not buy

### 10. Grid mode mismatch: sell_only vs buy signal
Goal:
- set `grid_mode = sell_only` in `grid_policy.json`
- set entry intent direction to `buy`

Expected result:
- first entry skipped
- log says grid policy sell_only but signal is not sell

### 11. Risk overlay spread block
Goal:
- set max spread very low or test during wide spread conditions

Expected result:
- risk overlay blocks first entry
- log shows `GRID_SKIP_NEW_ENTRY` with spread reason
- no dry-run entry log

### 12. Risk overlay exposure block
Goal:
- simulate open positions beyond configured limits

Expected result:
- risk overlay blocks new entry
- log shows `GRID_SKIP_NEW_ENTRY` with exposure reason
- basket management path may still run

### 13. Existing basket prevents first entry
Goal:
- ensure at least one open position exists for the pair

Expected result:
- log shows `GRID_DEFER_NEW_ENTRY`
- no first-entry dry-run for that pair
- basket management path logs instead

---

## C. Basket expansion behavior

### 14. Buy-side expansion dry-run
Goal:
- create or simulate an existing buy position on a pair
- configure `grid_mode = both_sides` or `buy_only`
- move/observe Bid below `last_buy_open_price - step_pips`

Expected result:
- log shows `GRID_EXPANSION_SIGNAL`
- followed by `GRID_DRY_RUN_EXPANSION`
- lots should reflect `average_side_lot * multiplier`

### 15. Sell-side expansion dry-run
Goal:
- create or simulate an existing sell position on a pair
- configure `grid_mode = both_sides` or `sell_only`
- move/observe Ask above `last_sell_open_price + step_pips`

Expected result:
- log shows `GRID_EXPANSION_SIGNAL`
- followed by `GRID_DRY_RUN_EXPANSION`

### 16. Expansion waits when trigger not reached
Goal:
- existing basket present but market has not reached step trigger

Expected result:
- log shows `GRID_WAIT_EXPANSION`
- includes market price, trigger price, and step_pips
- no dry-run expansion

### 17. Max trades per side cap
Goal:
- create or simulate side count equal to `max_trades_per_side`

Expected result:
- log shows `GRID_SKIP_EXPANSION`
- reason: max trades reached

### 18. Grid mode enforcement during expansion
Goal:
- `grid_mode = buy_only` with both buy and sell exposure present

Expected result:
- only buy-side expansion is evaluated
- sell-side expansion is skipped entirely

---

## D. Basket exit / recovery behavior

### 19. Basket take-profit dry-run
Goal:
- existing pair basket floating PnL >= `basket_tp_currency`

Expected result:
- log shows `GRID_BASKET_TP_SIGNAL`
- followed by `GRID_DRY_RUN_CLOSE_PAIR`
- no real close orders while dry-run enabled

### 20. Strong-avoid flatten dry-run
Goal:
- existing pair basket present
- pair policy set to `POLICY_BLOCK_NEW_ENTRIES_STRONG`
- `flatten_on_strong_avoid = true`

Expected result:
- log shows `GRID_STRONG_AVOID_ACTIVE`
- followed by `GRID_DRY_RUN_CLOSE_PAIR`

### 21. Strong-avoid flatten disabled
Goal:
- existing pair basket present
- strong avoid active
- `flatten_on_strong_avoid = false`

Expected result:
- no flatten action taken
- basket management continues normally
- useful to confirm Python-owned exit behavior is respected

### 22. Invalid grid policy values
Goal:
- test one invalid field at a time:
  - `step_pips <= 0`
  - `initial_lot <= 0`
  - `multiplier < 1.0`
  - `max_trades_per_side < 1`
  - `basket_tp_currency < 0`

Expected result:
- `GridPolicyReader` rejects row
- first entry skipped
- expansion skipped
- log shows clear invalid reason

---

## What good logs look like

### Allowed dry-run first-entry case
You want to see a sequence like:
- policy state logged with fresh status
- `ALLOW_NEW_TRADE`
- `GRID_FIRST_ENTRY_SIGNAL`
- `GRID_DRY_RUN_ENTRY`

### Allowed dry-run basket expansion
You want to see:
- `GRID_MANAGE_BASKET`
- `GRID_EXPANSION_SIGNAL`
- `GRID_DRY_RUN_EXPANSION`

### Allowed dry-run basket exit
You want to see:
- `GRID_BASKET_TP_SIGNAL` or `GRID_STRONG_AVOID_ACTIVE`
- `GRID_DRY_RUN_CLOSE_PAIR`

### Correctly blocked case
You want to see one of:
- `BLOCK_NEW_TRADE`
- `GRID_SKIP_NEW_ENTRY`
- `GRID_SKIP_MANAGEMENT`
- `GRID_SKIP_EXPANSION`
- `GRID_DEFER_NEW_ENTRY`

with a reason that makes sense.

---

## What bad signs look like

Investigate immediately if you see:
- dry-run entry when pair policy should block
- dry-run entry with expired entry intent
- dry-run entry with invalid/expired grid policy
- buy entry under `sell_only` mode or sell entry under `buy_only`
- expansion beyond `max_trades_per_side`
- basket flatten when `flatten_on_strong_avoid = false`
- missing reason strings
- repeated malformed-file errors without fail-closed behavior
- real orders while `InpEnableLiveTrading = false`

---

## Recommended test order

1. happy-path first entry
2. missing / expired file cases
3. policy block cases
4. grid mode mismatch cases
5. existing basket case
6. basket expansion cases
7. max-trades cap case
8. basket TP case
9. strong-avoid flatten case
10. invalid grid policy values

This order moves from simplest to more stateful cases.

---

## Exit criteria before live enable

Do not enable live trading until:
- all 3 handoff files are stable and fresh
- all missing/stale/invalid file behavior is fail-closed
- first-entry behavior matches pair policy + entry intent + grid policy
- expansion behavior matches `step_pips`, `multiplier`, and `max_trades_per_side`
- buy_only / sell_only / both_sides behavior is correct
- basket TP and strong-avoid flatten logic behave as expected
- no real trade can occur in dry-run mode
- log reasons are clear and auditable

---

## Recommendation after checklist passes

Only then consider a limited live pilot with:
- one pair
- tiny lot size
- strong logging
- tight supervision
- MT5 terminal visible during the test
