# MT5 Core Portfolio Policy Consumer Plan

## Goal

Define the first MT5-side implementation plan for consuming:
- `ForexSlave\\core_portfolio_policy.json`

This consumer should let the MQL5 slave enforce the Python-published `core_v1.1_guarded` execution baseline without re-deriving strategy logic locally.

## Scope

This plan is for the MT5 slave execution layer only.
It is not a full EA implementation.

The immediate target is a clean, testable consumer that can:
- load policy
- validate freshness
- expose pair/session configuration
- enforce new-basket permission and slot caps
- expose managed-close timing and guardrail state to execution modules

## Inputs

### Required Python-owned files
1. `pair_risk_policy.json`
2. `entry_intent.json`
3. `core_portfolio_policy.json`

This document focuses on `core_portfolio_policy.json`.

## Recommended MT5 module additions

Under the existing slave architecture, add:

### `CorePortfolioPolicyReader`
Responsibility:
- load `core_portfolio_policy.json`
- parse top-level guardrails
- parse per-pair policy rows
- validate freshness
- expose row lookup by pair

Suggested methods:
- `bool Refresh()`
- `bool HasFreshRow(string pair)`
- `bool IsPairEnabled(string pair)`
- `bool AllowNewBasket(string pair)`
- `int GetMaxTradesPerSide(string pair)`
- `double GetStepPips(string pair)`
- `double GetInitialLot(string pair)`
- `double GetMultiplier(string pair)`
- `double GetBasketTpPips(string pair)`
- `double GetBasketSlPips(string pair)`
- `double GetMaxBasketDrawdownCurrency(string pair)`
- `double GetMaxSlotDrawdownCurrency(string pair)`
- `int GetManagedCloseMinutes(string pair)`
- `bool FlattenOnAccountBreach(string pair)`
- `string GetReason(string pair)`

### `PortfolioGuardrailState`
Responsibility:
- store top-level account/portfolio guardrails from the file
- expose them to execution gate and risk overlay

Suggested methods:
- `int GetMaxActiveSlots()`
- `double GetMaxTotalInitialLots()`
- `double GetMaxTotalDrawdownCurrency()`
- `double GetDailyLossCapCurrency()`
- `double GetSessionLossCapCurrency()`
- `bool BlockNewEntriesAfterDailyCap()`
- `bool FlattenOnAccountBreach()`

## Suggested MQL5 shared types

### `struct CorePortfolioPairPolicy`
Fields:
- `string pair`
- `string sessionName`
- `bool enabled`
- `bool allowNewBasket`
- `string gridMode`
- `string seedMode`
- `double stepPips`
- `double initialLot`
- `string initialLotMode`
- `double baseEquity`
- `double multiplier`
- `int maxTradesPerSide`
- `double basketTpPips`
- `double basketSlPips`
- `double maxBasketDrawdownCurrency`
- `double maxSlotDrawdownCurrency`
- `int managedCloseMinutes`
- `string sessionCloseBehavior`
- `bool flattenOnAccountBreach`
- `double tailLossGuardCurrency`
- `double forcedCloseRateWarn`
- `datetime expiresAt`
- `string reason`
- `bool valid`

### `struct CorePortfolioGuardrails`
Fields:
- `int maxActiveSlots`
- `double maxTotalInitialLots`
- `double maxTotalDrawdownCurrency`
- `double dailyLossCapCurrency`
- `double sessionLossCapCurrency`
- `bool flattenOnAccountBreach`
- `bool blockNewEntriesAfterDailyCap`
- `bool valid`

## Validation rules

Reject the entire policy file or pair row if:
- JSON parse fails
- `generated_at_utc` missing or invalid
- row `pair` missing
- row `enabled == false` for requested pair
- `allow_new_basket` missing
- `step_pips <= 0`
- `initial_lot <= 0`
- `multiplier < 1.0`
- `max_trades_per_side < 1`
- `basket_tp_pips < 0`
- `basket_sl_pips <= 0`
- `max_basket_drawdown_currency <= 0`
- `max_slot_drawdown_currency <= 0`
- `managed_close_minutes < 0`
- `expires_at_utc` expired

If invalid or stale:
- deny new basket creation
- continue only safe management behavior for existing baskets
- log the exact reason

## ExecutionGate integration

`ExecutionGate` should incorporate the new reader like this:

### For new baskets
Require all of:
1. fresh pair risk policy
2. fresh entry intent
3. fresh core portfolio row
4. pair row enabled
5. `allow_new_basket == true`
6. local broker/risk checks pass
7. active slot count below `maxActiveSlots`
8. total planned initial lots below `maxTotalInitialLots`
9. daily/session loss cap not breached

### For basket expansion
Require all of:
1. fresh core portfolio row
2. current basket side depth < `maxTradesPerSide`
3. current basket DD < `maxBasketDrawdownCurrency`
4. current slot DD < `maxSlotDrawdownCurrency`
5. local spread/margin checks pass

### For managed close
When session remaining time <= `managedCloseMinutes`:
- block new basket creation
- optionally block new grid legs if desired by future rule
- allow only management/exit logic

## Required PositionRegistry additions

To enforce portfolio-level guardrails, MT5 needs:
- active slot count across all managed pairs
- sum of initial lots for open baskets or projected first-entry lots
- total floating drawdown across all managed pairs
- daily realized PnL or a session-local realized loss tracker

Suggested methods:
- `int CountActiveSlots()`
- `double GetTotalManagedFloatingPnL()`
- `double GetTotalManagedDrawdownCurrency()`
- `double GetManagedRealizedPnLToday()`
- `bool PairHasActiveBasket(string pair)`

## RiskOverlay integration

RiskOverlay should consume top-level guardrails for:
- account drawdown breach
- daily/session loss cap
- slot-level DD cap

If breached:
- block new entries
- optionally flatten depending on `flattenOnAccountBreach`
- log exact breach source

## Logging requirements

For every block, MT5 should log one clear reason string, for example:
- `core_policy_missing`
- `core_policy_stale`
- `pair_disabled_by_core_policy`
- `new_basket_blocked_daily_loss_cap`
- `new_basket_blocked_max_active_slots`
- `grid_expansion_blocked_max_trades_per_side`
- `grid_expansion_blocked_slot_dd`
- `managed_close_mode_no_new_entries`

## Recommended implementation order

### Phase 1
Build `CorePortfolioPolicyReader` only.
- parse file
- validate rows
- expose accessors

### Phase 2
Integrate into `ExecutionGate`.
- block/allow new baskets
- expose managed-close timing
- expose slot depth cap

### Phase 3
Integrate top-level portfolio guardrails with `PositionRegistry` and `RiskOverlay`.
- max active slots
- total drawdown cap
- daily/session loss caps

### Phase 4
Implement account-breach flatten behavior.

## Immediate next coding step

Build a minimal MQL5 include skeleton for:
- `CorePortfolioPolicyReader.mqh`
- `CorePortfolioTypes.mqh`

That is the cleanest next code artifact before wiring it into the EA loop.
