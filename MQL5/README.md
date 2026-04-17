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
- `Include/ForexSlave/GridManager.mqh`
- `Include/ForexSlave/RiskOverlay.mqh`
- `Include/ForexSlave/EntrySignal.mqh`
- `Include/ForexSlave/EntryIntentReader.mqh`
- `Include/ForexSlave/GridPolicyReader.mqh`

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
- GridManager flow for Python-authorized first-entry execution and basket-management hooks
- RiskOverlay for hard spread and exposure safety checks before future entries
- EntrySignal wired to Python-published entry intent through `EntryIntentReader`
- GridPolicyReader wired to Python-published `grid_policy.json` for step size, lot, multiplier, and max trades
- basket expansion logic wired to Python grid policy (step distance, multiplier, max trades)
- basket exit hooks: pair flatten on strong avoid, close-all on basket profit target
- hard grid-policy safety caps: max gross lots, max basket drawdown, min step vs spread, min free margin percent
- explicit dry-run safety switch with live trading disabled by default

Not implemented yet:
- robust JSON parsing of `pair_risk_policy.json` (current reader is schema-specific string extraction)
- basket/grid logic
- exposure tracking

## Safety default

The EA now defaults to:
- `InpEnableLiveTrading = false`

That means first-entry execution paths will log dry-run decisions unless you explicitly enable live trading.

## Current handoff path expectation

The MQL5 skeleton is now configured to read:
- `ForexSlave\\pair_risk_policy.json`
- `ForexSlave\\entry_intent.json`
- `ForexSlave\\grid_policy.json`

relative to the MT5 common-files root.

In workspace development, this corresponds to the mirrored handoff artifacts:
- `runtime_handoff/mt5_common/Files/ForexSlave/pair_risk_policy.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json`
- `runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json`

## Recommended next coding step

Refine basket exit logic to support configurable basket TP, side-aware profit harvesting, and recovery rules beyond the current simple close-all-on-profit implementation.
