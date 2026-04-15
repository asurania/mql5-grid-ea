# Forex Event Risk Inference Spec

## Purpose

This document defines the production inference contract for the first live economic-event risk model used by the Python master in the Forex trading system.

Current live candidate model:
- Model family: XGBoost + LightGBM ensemble (probability average)
- Target: `y_avoid_session`
- XGBoost artifact: `data/models/avoid_session/xgb_y_avoid_session.json`
- LightGBM artifact: `data/models/avoid_session_lgbm/lgbm_y_avoid_session.joblib`
- Calibration: `data/models/avoid_session/calibration/recommended_thresholds.json`
- Ensemble metrics: `data/models/avoid_session_ensemble/metrics.json`

The ensemble averages XGBoost and LightGBM probabilities for better calibration.
Test ROC AUC: 0.715, Test PR AUC: 0.426, strong-avoid precision at 0.75: 93.3%.

The model predicts whether an upcoming economic event should cause the strategy to avoid the surrounding session for a given pair.

## Architecture role

- **Python master**
  - owns economic-calendar ingestion
  - computes pre-event features
  - loads the trained model
  - scores each relevant pair-event combination
  - converts score to risk action
  - publishes execution policy to the MQL5 slave

- **MQL5 slave**
  - does not run ML
  - receives a pair/session risk policy from Python
  - applies execution restrictions, for example:
    - allow trading
    - halt new entries
    - flatten or suspend according to policy rules configured outside the model

## Model input contract

One inference row represents:
- one economic event
- one target pair
- scored before event time using only data available before the event

### Required feature columns

#### Event identity and metadata
- `pair`
- `event_timestamp_utc`
- `event_name`
- `event_category`
- `currency_norm`
- `importance_score_filled`
- `risk_prior`
- `avoid_session`

#### Time features
- `event_year`
- `event_month`
- `event_weekday`
- `event_hour`

#### Encoded risk/session flags
- `risk_prior_halt`
- `risk_prior_reduce`
- `avoid_asia`
- `avoid_london`
- `avoid_both`

#### Currency and pair structural flags
- `is_jpy_event`
- `is_gbp_event`
- `is_usd_event`
- `is_eur_event`
- `is_nzd_event`
- `pair_is_jpy_cross`
- `pair_has_gbp_base`
- `pair_has_usd_quote`

#### Event category one-hot features
- `cat_central_bank`
- `cat_inflation`
- `cat_employment`
- `cat_gdp`
- `cat_pmi`
- `cat_retail_sales`
- `cat_trade`
- `cat_housing`
- `cat_sentiment`
- `cat_speech`
- `cat_auction`
- `cat_agriculture`
- `cat_other`

#### Pair one-hot features
- `pair_eurjpy`
- `pair_gbpjpy`
- `pair_gbpusd`
- `pair_nzdusd`

#### Pre-event price regime features
- `ret_prev_5m`
- `ret_prev_15m`
- `ret_prev_60m`
- `ret_prev_240m`
- `rolling_std_5m_30`
- `rolling_std_15m_30`
- `avg_range_frac_60`
- `range_width_60`
- `dist_from_mean_60`

## Feature generation rules

### Calendar-derived features
These are computed from the normalized event record.

Requirements:
- timestamps normalized to UTC
- event category mapping stable between training and live
- missing importance values filled consistently with training logic
- risk-prior and avoid-session heuristic flags generated with the same pipeline as training

### Price-derived features
These must be computed from minute bars strictly before scoring time.

Definitions:
- `ret_prev_5m` = close(t) / close(t-5m) - 1
- `ret_prev_15m` = close(t) / close(t-15m) - 1
- `ret_prev_60m` = close(t) / close(t-60m) - 1
- `ret_prev_240m` = close(t) / close(t-240m) - 1
- `bar_range_frac` = (high - low) / close
- `rolling_std_5m_30` = rolling std of `ret_prev_5m` over last 30 bars
- `rolling_std_15m_30` = rolling std of `ret_prev_15m` over last 30 bars
- `avg_range_frac_60` = rolling mean of `bar_range_frac` over last 60 bars
- `range_width_60` = (rolling_high_60 - rolling_low_60) / close
- `dist_from_mean_60` = (close - rolling_mean_close_60) / close

Important:
- use the latest completed minute bar before inference time
- do not use any bar that includes post-event information
- if event time lands exactly on a minute boundary, score using the most recent completed pre-event bar

## Model output contract

For each pair-event inference row, Python master should emit:

```json
{
  "pair": "GBPJPY",
  "event_timestamp_utc": "2026-04-15T12:30:00Z",
  "event_name": "UK CPI y/y",
  "model": "ensemble_xgb_lgbm",
  "score_xgb": 0.64,
  "score_lgbm": 0.70,
  "score_avoid_session": 0.67,
  "risk_action": "avoid_session",
  "risk_band": "standard_avoid",
  "threshold_version": "avoid_session_ensemble_v1",
  "generated_at_utc": "2026-04-15T12:25:00Z"
}
```

## Decision policy

Current recommended thresholds:
- `score >= 0.75` → `avoid_session_strong`
- `0.60 <= score < 0.75` → `avoid_session`
- `0.45 <= score < 0.60` → `review_or_halt_new_entries`
- `score < 0.45` → `do_not_trigger_avoid_session`

### Recommended live default
Use `0.60` as the default cutoff for session avoidance.

### Recommended live interpretation
- `avoid_session_strong`
  - disable new entries for the pair
  - optionally flatten according to outer strategy policy
  - keep restriction active for configured session block

- `avoid_session`
  - disable new entries for the pair for the relevant session window
  - leave position reduction or flattening to higher-level risk policy

- `review_or_halt_new_entries`
  - optional soft band
  - best used only when another regime or exposure rule is also negative

- `do_not_trigger_avoid_session`
  - no session block from this model alone

## Integration flow

### Python master workflow
1. ingest upcoming economic calendar events
2. expand each event to relevant pairs
3. compute heuristic priors
4. pull latest completed minute bars for each pair
5. compute pre-event regime features
6. assemble inference feature row in training-compatible schema
7. load XGBoost and LightGBM model artifacts
8. compute `score_avoid_session` as the average of both model probabilities
9. map score to decision thresholds
10. publish pair risk policy to execution layer

### MQL5 slave workflow
1. receive pair-level policy from Python master
2. check current pair against active policy
3. if action is `avoid_session` or stronger:
   - reject new grid/martingale entries
   - optionally allow only management of existing positions
4. if action is `review_or_halt_new_entries`:
   - follow configurable soft-halt rule
5. log received policy and execution response

## Operational guidance

### When to score
Recommended scoring times:
- initial score when event enters the actionable horizon, for example 60 minutes before event
- rescore closer to event, for example 15 minutes before event
- optional final rescore 1 minute before event if data latency is controlled

### Pair routing
Score only pairs relevant to the event currency mix and trading universe:
- EURJPY
- GBPJPY
- GBPUSD
- NZDUSD

### Safety guidance
- do not let MQL5 infer risk from raw calendar labels alone
- keep model scoring centralized in Python
- version both model artifact and threshold policy
- log every scored event, score, threshold, and resulting action for audit and retraining

## Files to use

### Model artifacts
- `data/models/avoid_session/xgb_y_avoid_session.json`
- `data/models/avoid_session_lgbm/lgbm_y_avoid_session.joblib`
- `data/models/avoid_session_ensemble/metrics.json`
- `data/models/avoid_session/metrics.json`
- `data/models/avoid_session_lgbm/metrics.json`
- `data/models/avoid_session/feature_importance.csv`
- `data/models/avoid_session_lgbm/feature_importance.csv`

### Calibration artifacts
- `data/models/avoid_session/calibration/recommended_thresholds.json`
- `data/models/avoid_session/calibration/threshold_grid_test.csv`
- `data/models/avoid_session/calibration/operating_points.csv`

### Training reference datasets
- `data/processed/modeling/avoid_session_training_dataset.parquet`
- `data/processed/modeling/event_risk_training_dataset_with_price_context.parquet`

## Recommended next implementation task

Build a production inference script in Python that:
- loads upcoming events
- computes the required pre-event feature row
- scores the ensemble (XGBoost + LightGBM averaged probabilities)
- emits a compact pair risk action payload for the MQL5 slave

(This script now exists as `src/massive_pipeline/run_live_event_risk_inference.py`.)
