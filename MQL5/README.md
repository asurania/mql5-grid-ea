# MQL5 Slave Skeleton

This folder contains the initial MQL5 slave scaffold for the Python-master / MQL5-slave architecture.

## Current contents

### Expert
- `Experts/ForexSlaveEA.mq5`

### Includes
- `Include/ForexSlave/Types.mqh`
- `Include/ForexSlave/Config.mqh`
- `Include/ForexSlave/TelemetryLogger.mqh`
- `Include/ForexSlave/PolicyReader.mqh`
- `Include/ForexSlave/ExecutionGate.mqh`
- `Include/ForexSlave/TradeExecutor.mqh`
- `Include/ForexSlave/PositionRegistry.mqh`

## Current state

This is a skeleton only.

Implemented:
- EA shell
- timer refresh loop
- basic file-backed policy reader
- fail-safe execution gate with explicit block reasons
- logging
- basic real trade executor wrapper around `CTrade`
- position registry for per-pair open position, lot, and floating PnL tracking

Not implemented yet:
- robust JSON parsing of `pair_risk_policy.json` (current reader is schema-specific string extraction)
- basket/grid logic
- exposure tracking

## Current handoff path expectation

The MQL5 skeleton is now configured to read:
- `ForexSlave\\pair_risk_policy.json`

relative to the MT5 common-files root.

In workspace development, this corresponds to the mirrored handoff artifact:
- `runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json`

## Recommended next coding step

Implement the real `PolicyReader` file-loading and JSON parsing path first.
That unlocks meaningful end-to-end testing before any strategy port work.
