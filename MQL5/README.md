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

## Current state

This is a skeleton only.

Implemented:
- EA shell
- timer refresh loop
- stub policy reader
- execution gate
- logging
- trade executor stubs

Not implemented yet:
- JSON parsing of `pair_risk_policy.json`
- real trade placement wrapper
- basket/grid logic
- exposure tracking
- stale-file timestamp enforcement from real payload timestamps

## Recommended next coding step

Implement the real `PolicyReader` file-loading and JSON parsing path first.
That unlocks meaningful end-to-end testing before any strategy port work.
