# Dry-Run Integration Checklist

## Purpose

Use this checklist to validate the Python-master to MQL5-slave control loop before enabling live trading.

Assumption:
- `InpEnableLiveTrading = false`

That means the EA should log dry-run intent instead of sending real orders.

## Test objective

Confirm that the full pipeline behaves correctly across:
- policy generation
- entry intent generation
- MT5 handoff publishing
- MQL5 policy loading
- MQL5 entry intent loading
- execution gate decisions
- risk overlay decisions
- dry-run first-entry decisions

## Pre-test setup

### Python side
Run:

```bash
/home/asurani/.openclaw/workspace/.venv-forex/bin/python src/massive_pipeline/run_event_risk_master.py
```

Confirm artifacts exist:
- `data/live/policy/pair_risk_policy.json`
- `data/live/policy/entry_intent.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json`

### MQL5 side
Confirm:
- EA attached to chart
- `InpEnableLiveTrading = false`
- `InpPolicyFilePath = ForexSlave\\pair_risk_policy.json`
- terminal can access common files path being used for the test

## Test cases

### 1. Happy path, dry-run first entry
Goal:
- policy allows trading
- entry intent says `buy` or `sell`
- risk overlay passes
- no open basket exists

Expected result:
- no real trade sent
- log contains:
  - `ALLOW_NEW_TRADE`
  - `GRID_FIRST_ENTRY_SIGNAL`
  - `GRID_DRY_RUN_ENTRY`

### 2. Policy block
Goal:
- pair policy set to `block_new_entries` or stronger

Expected result:
- log contains:
  - `BLOCK_NEW_TRADE`
  - `GRID_SKIP_NEW_ENTRY`
- no dry-run entry log
- no real trade sent

### 3. Missing policy file
Goal:
- temporarily remove or rename published `pair_risk_policy.json`

Expected result:
- policy reader reports missing/invalid state
- execution gate blocks new trades
- log should indicate fail-closed reason
- no dry-run entry log

### 4. Expired entry intent
Goal:
- force `expires_at_utc` in `entry_intent.json` to a past time

Expected result:
- `EntryIntentReader` rejects intent
- `GridManager` logs skip reason related to expired intent
- no dry-run entry log

### 5. Direction missing or `none`
Goal:
- use an intent row with `should_enter = true` but `direction = none`

Expected result:
- slave refuses first entry
- log shows skip reason for missing/invalid direction
- no dry-run entry log

### 6. Risk overlay spread block
Goal:
- set `m_maxSpreadPoints` very low or test during wide spread conditions

Expected result:
- risk overlay blocks first entry
- log shows `GRID_SKIP_NEW_ENTRY` with spread reason
- no dry-run entry log

### 7. Risk overlay exposure block
Goal:
- simulate open positions beyond configured limits

Expected result:
- risk overlay blocks new entry
- log shows `GRID_SKIP_NEW_ENTRY` with exposure reason
- basket management path may still run

### 8. Existing basket prevents first entry
Goal:
- ensure at least one open position exists for the pair

Expected result:
- log shows `GRID_DEFER_NEW_ENTRY`
- no first-entry dry-run for that pair
- basket management path logs instead

## What good logs look like

### Allowed dry-run case
You want to see a sequence like:
- policy state logged with fresh status
- `ALLOW_NEW_TRADE`
- `GRID_FIRST_ENTRY_SIGNAL`
- `GRID_DRY_RUN_ENTRY`

### Correctly blocked case
You want to see one of:
- `BLOCK_NEW_TRADE`
- `GRID_SKIP_NEW_ENTRY`
- `GRID_DEFER_NEW_ENTRY`

with a reason that makes sense.

## What bad signs look like

Investigate immediately if you see:
- dry-run entry when policy should block
- dry-run entry with expired intent
- missing reason strings
- repeated malformed-file errors without fail-closed behavior
- real orders while `InpEnableLiveTrading = false`

## Recommended test order

1. happy-path dry-run
2. policy block
3. missing policy file
4. expired intent
5. direction none
6. spread block
7. exposure block
8. existing basket case

This order moves from simplest to more stateful cases.

## Exit criteria before live enable

Do not enable live trading until:
- all core cases behave as expected
- reasons are clear in logs
- no real trade can occur in dry-run mode
- stale/missing/invalid file behavior is fail-closed
- published file paths are stable and repeatable

## Recommendation after checklist passes

Only then consider a limited live pilot with:
- one pair
- tiny lot size
- strong logging
- tight supervision
