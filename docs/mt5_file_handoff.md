# MT5 File Handoff Convention

## Purpose

This document defines the v1 shared-file convention between the Python master and the MQL5 slave.

Current handoff files:
- `pair_risk_policy.json`
- `entry_intent.json`
- `grid_policy.json`

## v1 approach

The Python master publishes policy JSON files into a handoff directory that mirrors the structure of MetaTrader common files.

### Source artifacts
- `data/live/policy/pair_risk_policy.json`
- `data/live/policy/entry_intent.json`
- `data/live/policy/grid_policy.json`

### Published handoff artifacts
- `runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json`

## Why this path

MQL5 commonly reads shared files through the terminal common-files area.
For development inside this workspace, we mirror that layout so:
- the Python side has a stable publish target
- the MQL5 side has one explicit expected relative path
- deployment can later swap the mirrored directory for the real MT5 common-files location

## Python publish step

Publisher scripts:
- `src/massive_pipeline/publish_pair_risk_policy.py`
- `src/massive_pipeline/publish_entry_intent.py`
- `src/massive_pipeline/publish_grid_policy.py`

These scripts copy the live policy artifacts into:
- `runtime_handoff/mt5_common/Files/ForexSlave/`

## Master wrapper behavior

The event-risk master wrapper now runs:
1. live inference
2. pair policy aggregation
3. pair policy publish step
4. entry intent build + publish
5. grid policy build + publish

Wrapper entrypoint:
- `src/massive_pipeline/run_event_risk_master.py`

## MQL5 expectation

For v1 development, the slave should be configured to look for:
- `pair_risk_policy.json`
- `entry_intent.json`
- `grid_policy.json`

inside its expected common-files-facing handoff directory.

In production, this should resolve to the real MetaTrader common-files path used by the terminal.

## Deployment note

When you move from workspace testing to live MT5 deployment, replace or sync:
- `runtime_handoff/mt5_common/Files/ForexSlave/`

with the actual MT5 common-files directory visible to the terminal.

## Recommended next step

Update the MQL5 config/deployment notes so `InpPolicyFilePath` matches the live common-files location convention you choose for the terminal environment.
