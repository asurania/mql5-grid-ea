# ML Grid Policy Design

## Goal

Design a Python-owned ML policy layer that selects safe and effective grid settings for a **two-sided grid** (buy ladder + sell ladder) before a new basket starts.

The model should eventually control:
- step size
- initial lot size
- multiplier
- max trades allowed
- whether both sides are allowed or one side should be disabled

This is a higher-level policy problem than the current event-risk and entry-intent models.

---

## Core principle

The model should **not** directly learn from whatever grid settings happened historically.

Instead:
1. define candidate grid policies
2. simulate them on historical market states
3. rank them by risk-adjusted outcome
4. train the model to predict the best policy from pre-basket features

This avoids learning bad human choices or overfitting to arbitrary parameter history.

---

## Recommended v1 approach

### Use policy buckets, not raw regression

Instead of predicting raw values like:
- `step_pips = 11.37`
- `multiplier = 1.218`

start with a discrete policy classifier.

Example policy buckets:
- `no_trade`
- `both_sides_conservative`
- `both_sides_normal`
- `both_sides_wide_light`
- `buy_only_conservative`
- `sell_only_conservative`

Each bucket maps to a fixed parameter template.

This is safer, easier to label, easier to backtest, and easier to audit.

---

## Architecture split

### Python master owns
- market-state feature computation
- grid-policy model inference
- policy selection
- publishing chosen grid configuration

### MQL5 slave owns
- actual order execution
- basket state tracking
- applying the received policy
- refusing actions that violate local hard safety constraints

Python decides *what policy is allowed*.
MQL5 decides *whether execution is still safe right now*.

---

# 1. Historical simulation requirement

We need a **two-sided grid simulator**.

For each candidate basket start time and parameter set, it should simulate:
- buy-side ladder behavior
- sell-side ladder behavior
- simultaneous exposure on both sides
- basket closure / recovery logic
- floating drawdown and margin usage over time

## Simulator inputs

### Market data
- minute bars for target pairs
- optional spread assumptions or spread model
- session boundaries
- event timeline / event-risk state

### Basket start state
- timestamp
- pair
- initial direction permissions (`buy_only`, `sell_only`, `both_sides`)
- account equity
- available margin
- open exposure elsewhere

### Candidate policy parameters
- `grid_mode` (`both_sides`, `buy_only`, `sell_only`)
- `step_pips`
- `initial_lot`
- `multiplier`
- `max_trades_per_side`
- optional future fields:
  - `take_profit_mode`
  - `basket_tp_currency`
  - `max_gross_lots`
  - `time_stop_minutes`

## Simulator outputs per run
- `net_pnl`
- `max_drawdown_abs`
- `max_drawdown_pct`
- `max_margin_used`
- `max_gross_lots`
- `time_to_exit_minutes`
- `closed_normally`
- `hit_stop_condition`
- `blowup_flag`
- `buy_trades_opened`
- `sell_trades_opened`
- `buy_pnl`
- `sell_pnl`
- `worst_floating_buy`
- `worst_floating_sell`
- `worst_total_floating`

---

# 2. Candidate policy templates

Recommended v1 template library:

## No-trade
```json
{
  "policy_id": "no_trade",
  "allow_new_basket": false
}
```

## Both sides conservative
```json
{
  "policy_id": "both_sides_conservative",
  "allow_new_basket": true,
  "grid_mode": "both_sides",
  "step_pips": 18,
  "initial_lot": 0.01,
  "multiplier": 1.10,
  "max_trades_per_side": 3
}
```

## Both sides normal
```json
{
  "policy_id": "both_sides_normal",
  "allow_new_basket": true,
  "grid_mode": "both_sides",
  "step_pips": 12,
  "initial_lot": 0.01,
  "multiplier": 1.20,
  "max_trades_per_side": 5
}
```

## Both sides wide light
```json
{
  "policy_id": "both_sides_wide_light",
  "allow_new_basket": true,
  "grid_mode": "both_sides",
  "step_pips": 22,
  "initial_lot": 0.01,
  "multiplier": 1.05,
  "max_trades_per_side": 4
}
```

## Buy-only conservative
```json
{
  "policy_id": "buy_only_conservative",
  "allow_new_basket": true,
  "grid_mode": "buy_only",
  "step_pips": 15,
  "initial_lot": 0.01,
  "multiplier": 1.15,
  "max_trades_per_side": 4
}
```

## Sell-only conservative
```json
{
  "policy_id": "sell_only_conservative",
  "allow_new_basket": true,
  "grid_mode": "sell_only",
  "step_pips": 15,
  "initial_lot": 0.01,
  "multiplier": 1.15,
  "max_trades_per_side": 4
}
```

These are placeholders. Real values should come from backtest search.

---

# 3. Feature dataset schema

One row = one potential basket start time for one pair.

## Identity columns
- `pair`
- `basket_start_ts_utc`
- `session_label`
- `event_proximity_minutes`

## Event-risk context
- `score_avoid_session`
- `risk_action_band`
- `event_in_next_15m`
- `event_in_next_60m`
- `event_importance_score`
- `event_category`
- `risk_prior_halt`
- `risk_prior_reduce`

## Price regime features
- `ret_prev_5m`
- `ret_prev_15m`
- `ret_prev_60m`
- `ret_prev_240m`
- `rolling_std_5m_30`
- `rolling_std_15m_30`
- `avg_range_frac_60`
- `range_width_60`
- `dist_from_mean_60`
- `atr_frac_14`
- `atr_frac_60`
- `atr_ratio_14_60`
- `mom_30m`
- `mom_2h`
- `abs_mom_30m`
- `abs_mom_2h`
- `dir_consistency_60`
- `momentum_aligned`

## Structural pair features
- `pair_is_jpy_cross`
- `pair_has_gbp_base`
- `pair_has_usd_quote`
- `pair_eurjpy`
- `pair_gbpjpy`
- `pair_gbpusd`
- `pair_nzdusd`

## Cross-side / two-sided context
These matter specifically because both buy and sell ladders may exist.
- `distance_to_recent_high_60`
- `distance_to_recent_low_60`
- `position_in_60m_range`
- `position_in_240m_range`
- `signed_range_skew`
- `whipsaw_score_recent`
- `mean_reversion_score`
- `trend_continuation_score`

## Account/risk context
- `equity_bucket`
- `free_margin_ratio`
- `gross_exposure_ratio`
- `open_baskets_count`
- `open_pair_exposure`
- `daily_drawdown_pct`

### Note
For offline dataset generation, account state can initially be simulated as standardized templates.
For live inference, use real account state from the Python master or MQL5 telemetry.

---

# 4. Label generation

For each historical basket-start row:
1. run all candidate policy templates in simulator
2. compute utility score for each
3. assign best template as target label

## Utility function example

```text
utility =
    net_pnl
    - 3.0 * max_drawdown_pct
    - 2.0 * margin_usage_pct
    - 5.0 * blowup_flag
    - 0.5 * time_to_exit_days
```

Alternative utility for safer live deployment:

```text
utility =
    0.5 * normalized_pnl
    - 2.0 * normalized_drawdown
    - 2.0 * normalized_margin
    - 10.0 * blowup_flag
```

The exact weighting should reflect your real risk tolerance.

---

# 5. Recommended training targets

## V1 target
- `y_best_grid_policy_id`

This is a multi-class classification target.

## Optional secondary targets
- `y_allow_new_basket`
- `y_preferred_side_mode` (`both_sides`, `buy_only`, `sell_only`)
- `y_safe_max_trades_bucket`
- `y_safe_step_bucket`

A staged approach may outperform one giant multi-class policy model.

---

# 6. JSON handoff contract

Python should publish a new file for grid policy, for example:
- `grid_policy.json`

## Suggested path
- development mirror: `runtime_handoff/mt5_common/Files/ForexSlave/grid_policy.json`
- MT5 common-files relative path: `ForexSlave\\grid_policy.json`

## Suggested schema

```json
{
  "generated_at_utc": "2026-04-15T21:00:00Z",
  "version": "grid_policy_v1",
  "model": "grid_policy_classifier_v1",
  "pairs": [
    {
      "pair": "GBPJPY",
      "allow_new_basket": true,
      "policy_id": "both_sides_conservative",
      "grid_mode": "both_sides",
      "step_pips": 18,
      "initial_lot": 0.01,
      "multiplier": 1.10,
      "max_trades_per_side": 3,
      "confidence": 0.72,
      "reason": "ml_grid_policy_both_sides_conservative",
      "expires_at_utc": "2026-04-15T21:05:00Z"
    }
  ]
}
```

## Field meanings
- `allow_new_basket`: whether Python authorizes starting a new basket at all
- `policy_id`: selected template id
- `grid_mode`: `both_sides`, `buy_only`, `sell_only`
- `step_pips`: spacing between ladder entries
- `initial_lot`: starting lot size
- `multiplier`: lot growth multiplier per additional trade
- `max_trades_per_side`: cap per direction
- `confidence`: optional model confidence
- `reason`: human/debug explanation
- `expires_at_utc`: stale protection

---

# 7. MQL5 enforcement contract

The slave should treat grid policy as:
- necessary for opening a new basket
- not sufficient by itself

Execution still requires:
1. pair risk policy allows trading
2. entry intent allows basket start
3. grid policy exists and is fresh
4. local risk overlay passes
5. local exposure and broker checks pass

## Important
MQL5 should **not invent** step size, multiplier, or max trades if Python owns the policy.
It may still enforce hard upper bounds locally.

---

# 8. Recommended build order

## Phase 1
- Define fixed policy template library
- Build two-sided grid simulator
- Generate simulation outcome table

## Phase 2
- Build labeled training dataset (`best_policy_id`)
- Train classifier
- Evaluate with walk-forward tests

## Phase 3
- Publish `grid_policy.json`
- Add MQL5 `GridPolicyReader`
- Make `GridManager` consume Python-provided settings

## Phase 4
- Add live telemetry feedback loop
- Re-estimate policy ranking from live outcomes

---

# 9. Practical recommendation

For v1, do **not** jump directly to continuous regression of raw parameters.

Start with:
- 5-10 policy buckets
- walk-forward simulation labels
- classifier that chooses the safest useful policy

That gets you most of the value with much lower blow-up risk.

Later, if the simulator and live telemetry look stable, move toward:
- raw constrained parameter optimization
- separate buy-side and sell-side parameterization
- reinforcement-learning-like policy improvement

---

# 10. Immediate next coding task

Build a `docs/grid_policy_contract.md` file and a Python prototype that emits a static `grid_policy.json` using hand-authored templates, before ML selection is wired in.
