# MQL5 Slave Architecture for Python-Master Control

## Goal

Design a clean MQL5 slave EA that:
- executes trades and manages positions
- consumes pair-level policy from Python master
- does not run ML
- does not own event interpretation
- remains small, deterministic, and testable

This is a fresh-design target, not a mechanical MT4-to-MT5 conversion.

## Design principles

### 1. Python owns intelligence
Python master is the control plane.
It owns:
- market/event intelligence
- ML scoring
- session-risk decisions
- higher-level policy generation

### 2. MQL5 owns execution
MQL5 slave is the execution plane.
It owns:
- order placement
- order modification
- position tracking
- basket state
- broker/platform interaction
- enforcement of received policy

### 3. Keep boundaries hard
The slave should not:
- replicate ML logic
- infer event danger from calendar labels
- quietly override Python risk actions

If the policy says no new entries, the slave should obey it.

## High-level module layout

Recommended MQL5 EA structure:

### 1. `PolicyReader`
Responsibility:
- load `pair_risk_policy.json`
- validate parse success
- validate freshness
- expose per-pair policy state

Suggested methods:
- `bool Refresh()`
- `bool HasFreshPolicy(string pair)`
- `string GetPolicyAction(string pair)`
- `string GetPolicyBand(string pair)`
- `double GetAvoidScore(string pair)`
- `string GetTriggerEventName(string pair)`
- `datetime GetTriggerEventTime(string pair)`
- `string GetPolicyStatus(string pair)`

### 2. `ExecutionGate`
Responsibility:
- decide whether a new trade action is allowed
- convert policy + local safety rules into execution permission

Suggested methods:
- `bool CanOpenNewTrade(string pair)`
- `bool CanAddGridLeg(string pair)`
- `bool IsSoftHalt(string pair)`
- `bool IsStrongAvoid(string pair)`
- `string ExplainBlockReason(string pair)`

### 3. `PositionRegistry`
Responsibility:
- track current open positions and pending orders for the EA
- compute basket state per pair

Suggested methods:
- `int CountOpenPositions(string pair)`
- `double GetNetLots(string pair)`
- `double GetFloatingPnL(string pair)`
- `bool HasOpenExposure(string pair)`
- `bool HasPendingOrders(string pair)`

### 4. `GridManager`
Responsibility:
- implement local execution strategy mechanics
- spacing, lot progression, basket logic, take-profit logic
- only act when gate permits

Suggested methods:
- `void EvaluateNewEntries(string pair)`
- `void EvaluateBasketManagement(string pair)`
- `void EvaluateRecoveryLogic(string pair)`

### 5. `TradeExecutor`
Responsibility:
- wrap raw MQL5 trade API
- normalize order placement/modification/close behavior
- centralize error handling and retries

Suggested methods:
- `bool OpenBuy(string pair, double lots, double sl, double tp, string comment)`
- `bool OpenSell(string pair, double lots, double sl, double tp, string comment)`
- `bool ClosePosition(ulong ticket)`
- `bool ModifyPosition(ulong ticket, double sl, double tp)`
- `bool CancelOrder(ulong ticket)`

### 6. `RiskOverlay`
Responsibility:
- apply hard local safety rules independent of the ML model
- examples:
  - max spread
  - max slippage
  - max number of legs
  - max exposure per pair
  - trading session whitelist/blacklist

Suggested methods:
- `bool PassesBrokerSafety(string pair)`
- `bool PassesExposureLimits(string pair)`
- `bool PassesSpreadCheck(string pair)`
- `string ExplainRiskBlock(string pair)`

### 7. `TelemetryLogger`
Responsibility:
- emit clear diagnostics for every important execution decision
- support debugging and later replay

Suggested methods:
- `void LogPolicyState(string pair)`
- `void LogTradeDecision(string pair, string action, string reason)`
- `void LogExecutionResult(string pair, string op, bool success, string detail)`
- `void LogPolicyError(string detail)`

## Core runtime loop

Recommended event flow inside the EA:

### OnInit
- initialize modules
- load initial policy file
- validate symbol coverage
- warm local state caches

### OnTimer
Use timer-driven orchestration, for example every 5 to 30 seconds:
- refresh policy file
- refresh position registry
- refresh broker/risk state
- log stale or invalid policy state

### OnTick
For the current symbol or managed symbols:
1. update market snapshot
2. read current pair policy
3. if no new entries allowed, block entry logic
4. continue allowed management logic for existing positions
5. if new entries allowed and local safety passes, let GridManager evaluate entries

This is better than packing everything into raw tick handlers with implicit state.

## Suggested decision chain for new entries

When evaluating a possible new order:

1. `PolicyReader` says whether policy is fresh and valid
2. `ExecutionGate` checks whether policy allows new entries
3. `RiskOverlay` checks local hard constraints
4. `GridManager` decides whether strategy conditions justify the trade
5. `TradeExecutor` sends the order
6. `TelemetryLogger` records the outcome

That order is important.
Policy and safety should block before strategy logic spends effort.

## Policy semantics in the slave

Recommended mapping:

### `allow_trading`
- allow entry evaluation
- allow basket management

### `soft_halt_new_entries`
- deny all new entries
- allow basket management
- allow closing/reducing exposure

### `block_new_entries`
- deny all new entries
- allow basket management
- optionally suppress aggressive recovery expansion

### `block_new_entries_and_flag_strong_avoid`
- deny all new entries
- allow basket management
- set local `strong_avoid` flag
- optional higher-level rule may reduce exposure or flatten if implemented later

## Recommended first implementation scope

Keep v1 small.

### Phase 1, minimal viable slave
Implement:
- `PolicyReader`
- `ExecutionGate`
- `TradeExecutor`
- `TelemetryLogger`
- thin EA loop skeleton

Goal:
- prove that MQL5 can safely obey Python policy
- block or allow entries correctly
- manage existing positions safely

### Phase 2, strategy execution port
Add:
- `PositionRegistry`
- `GridManager`
- `RiskOverlay`

Goal:
- move actual grid or basket logic into the new slave cleanly

### Phase 3, advanced controls
Optional later:
- stronger exposure-reduction logic on `strong_avoid`
- heartbeat/status reporting back to Python
- richer policy fields beyond avoid-session

## Suggested file layout

If you build this as a clean MQL5 project, something like:

```text
MQL5/
  Experts/
    ForexSlaveEA.mq5
  Include/
    ForexSlave/
      PolicyReader.mqh
      ExecutionGate.mqh
      PositionRegistry.mqh
      GridManager.mqh
      TradeExecutor.mqh
      RiskOverlay.mqh
      TelemetryLogger.mqh
      Types.mqh
      Config.mqh
```

## Suggested shared types

Useful structs/enums to define early:

### `enum PolicyAction`
- `POLICY_ALLOW_TRADING`
- `POLICY_SOFT_HALT_NEW_ENTRIES`
- `POLICY_BLOCK_NEW_ENTRIES`
- `POLICY_BLOCK_NEW_ENTRIES_STRONG`
- `POLICY_INVALID`

### `enum PolicyStatus`
- `POLICY_STATUS_FRESH`
- `POLICY_STATUS_STALE_WARNING`
- `POLICY_STATUS_STALE_FAIL_SAFE`
- `POLICY_STATUS_MISSING`
- `POLICY_STATUS_INVALID`

### `struct PairPolicy`
Fields:
- `string pair`
- `PolicyAction action`
- `string policyBand`
- `double maxScoreAvoidSession`
- `string triggerEventId`
- `string triggerEventName`
- `datetime triggerEventTime`
- `datetime generatedAt`
- `PolicyStatus status`

## Important implementation rule

The slave should be able to say exactly why a trade was blocked.
Never just return false without a reason.
That will matter a lot during live debugging.

## Recommended next build step

Implement a minimal MQL5 skeleton with:
- shared types
- policy reader interface
- execution gate interface
- EA timer/tick skeleton
- stubbed trade decision flow

That gives you a clean foundation before porting any real basket logic.
