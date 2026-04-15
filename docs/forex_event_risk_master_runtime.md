# Forex Event Risk Master Runtime

## Entry point

Run the full event-risk control loop with:

```bash
/home/asurani/.openclaw/workspace/.venv-forex/bin/python src/massive_pipeline/run_event_risk_master.py
```

## What it does

This wrapper runs, in order:

1. `src/massive_pipeline/run_live_event_risk_inference.py`
2. `src/massive_pipeline/build_pair_risk_policy.py`

## Outputs

### Event-level model output
- `data/live/event_risk/event_risk_actions.json`

### Pair-level execution policy
- `data/live/policy/pair_risk_policy.json`

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

## Next integration point

The Python master should consume:
- `data/live/policy/pair_risk_policy.json`

and translate each `policy_action` into execution permissions for the MQL5 slave.
