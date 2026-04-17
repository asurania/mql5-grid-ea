# Forex Event Risk Master Runtime

## Entry point

Run the full event-risk control loop with:

```bash
/home/asurani/.openclaw/workspace/.venv-forex/bin/python src/massive_pipeline/run_event_risk_master.py
```

Or pass grid-optimizer sizing inputs explicitly:

```bash
/home/asurani/.openclaw/workspace/.venv-forex/bin/python src/massive_pipeline/run_event_risk_master.py \
  --account-equity 10000 \
  --risk-mode medium
```

Optional current demo flag:

```bash
/home/asurani/.openclaw/workspace/.venv-forex/bin/python src/massive_pipeline/run_event_risk_master.py \
  --account-equity 10000 \
  --risk-mode medium \
  --allow-gbpjpy-demo-override
```

## What it does

This wrapper runs, in order:

1. `src/massive_pipeline/run_live_event_risk_inference.py`
2. `src/massive_pipeline/build_pair_risk_policy.py`
3. `src/massive_pipeline/publish_pair_risk_policy.py`
4. `src/massive_pipeline/build_entry_intent_v2.py`
5. `src/massive_pipeline/publish_entry_intent.py`
6. `src/massive_pipeline/build_live_session_range_features.py`
7. `src/massive_pipeline/run_live_session_range_inference.py`
8. `src/massive_pipeline/build_grid_policy.py --account-equity ... --risk-mode ... [--allow-gbpjpy-demo-override]`
9. `src/massive_pipeline/publish_grid_policy.py`

## Outputs

### Event-level model output
- `data/live/event_risk/event_risk_actions.json`

### Pair-level execution policy
- `data/live/policy/pair_risk_policy.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json`

### Entry intent
- `data/live/policy/entry_intent.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json`

### Session range model output
- `data/live/policy/session_range_features.json`
- `data/live/policy/session_range_predictions.json`

### Grid policy
- `data/live/policy/grid_policy.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json`

The grid policy payload now also includes optimizer-level metadata such as:
- `risk_mode`
- `account_equity`
- `risk_budget_currency`
- `target_profit_currency`
- `allow_gbpjpy_demo_override`

### Wrapper run log
- `data/live/policy/event_risk_master_run.json`

## Recommended invocation pattern

Run this on a schedule from the Python master service, for example:
- every 5 minutes during trading hours
- or immediately after refreshing economic calendar data

## Expected behavior

- If no upcoming events are inside the scoring horizon, the wrapper still succeeds.
- In that case, pair policies should default to `allow_trading`.
- Any step failure is recorded in `event_risk_master_run.json` with stdout/stderr.
- The wrapper summary now records the grid optimizer settings used for that run.

## Next integration point

The master runtime now produces the three Python-owned handoff files the MQL5 slave consumes:
- pair risk policy
- entry intent
- grid policy

Next operational step is dry-run testing against a real MT5 terminal common-files path.
