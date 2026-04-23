# Legacy Grid Parity Simulator

## Purpose

This module is the first pass of Phase C, a parity-oriented simulator for the legacy Prop-Buster MQL4 grid logic, rewritten around a normalized Python risk model.

It is intentionally separated from:
- MT5 execution bridge logic
- live policy publishing
- ML policy selection

The goal is to create a deterministic harness for:
- validating translated entry and expansion behavior
- comparing normalized risk overlays against legacy behavior
- serving as the reference engine for future backtests and optimizer labeling

---

## Files

- `src/massive_pipeline/legacy_grid_parity.py`
- `src/massive_pipeline/backtest_legacy_grid_parity.py`

---

## Current scope

### Included
- buy seed entry when bid < MA and bid < Gann
- sell seed entry when bid > MA and bid > Gann
- fixed and variable step support
- variable step arrays preserve decimals, for example `8.5` stays `8.5`
- progressive lot sizing by multiplier
- max levels per side
- historical MA reconstruction from minute closes
- historical Gann HiLo approximation from minute highs, lows, and closes
- basket TP/SL handling from weighted average entry
- managed-close mode that stops new entries and expansions near session end
- Calgary-time session segmentation for the target operating window
- variable EA step/TP windows with managed and immediate modes
- weekday filters and month-day exemptions
- 7-pair preset coverage for the target starting universe
- normalized currency drawdown cap

### Not yet included
- spread/slippage model
- exact MT4 order modification parity
- MT5 bridge handoff

---

## Design choice

We are not preserving every legacy quirk.

Notably, the MQL4 code truncates variable-step array values to integers during parsing. This simulator does not. Decimal steps are preserved because the requested direction is to improve behavior rather than reproduce bugs.

---

## Normalized risk model

The simulator uses explicit currency limits:
- `max_account_drawdown_currency`
- `max_basket_drawdown_currency`
- `target_basket_profit_currency`

This is the bridge between:
- the legacy EA risk controls (`ddeq_max`, `ddov_max`, etc.)
- the uploaded spreadsheet's theoretical DD and margin framing
- the newer Python-owned config and policy system

---

## Next build steps

1. add historical MA and Gann feature reconstruction from minute bars
2. implement weighted basket TP/SL logic to match intended basket management
3. add session windows and managed closing behavior
4. add policy export compatibility with existing `grid_policy.json`
5. integrate this simulator into policy-label generation for ML
