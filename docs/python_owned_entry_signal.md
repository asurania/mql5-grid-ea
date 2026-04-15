# Python-Owned Entry Signal Contract

## Decision

First-entry direction and intent should be owned by the Python master, not the MQL5 slave.

That means:
- Python decides whether a new basket should be started
- Python decides the intended direction
- Python can optionally suggest lot size or entry mode
- MQL5 still retains the right to block execution when policy or local safety rules fail

## Why this is the right split

This keeps the architecture coherent:

### Python master owns
- event intelligence
- ML risk models
- regime logic
- future directional models
- higher-level strategy coordination

### MQL5 slave owns
- broker interaction
- order execution
- exposure tracking
- basket state
- local hard safety rules
- enforcement of execution permissions

This avoids letting directional strategy logic leak back into the slave.

## Recommended v1 handoff artifact

Add a second Python-produced file for entry intent, for example:
- `entry_intent.json`

Published to the same MT5-style handoff area as policy files.

### Suggested development mirror path
- `runtime_handoff/mt5_common/Files/ForexSlave/entry_intent.json`

### Suggested MT5 common-files relative path
- `ForexSlave\\entry_intent.json`

## Suggested schema

### v2 (current)

Added alignment scoring, volatility regime filtering, and short-term counter-move detection.

```json
{
  "generated_at_utc": "2026-04-15T14:00:00Z",
  "version": "entry_intent_v2",
  "pairs": [
    {
      "pair": "GBPJPY",
      "should_enter": true,
      "direction": "buy",
      "entry_mode": "initial",
      "suggested_lots": 0.01,
      "reason": "v2_aligned_buy_str0.0034_score0.82",
      "expires_at_utc": "2026-04-15T14:05:00Z",
      "debug": {
        "atr_frac_60": 0.001234,
        "vol_regime": "normal",
        "alignment_score": 0.82,
        "trend_strength": 0.0034
      }
    }
  ]
}
```

### v1 (deprecated)

Simple trend alignment: all of 15m/60m/240m same sign.

```json
{
  "generated_at_utc": "2026-04-15T14:00:00Z",
  "version": "entry_intent_v1",
  "pairs": [
    {
      "pair": "GBPJPY",
      "should_enter": true,
      "direction": "buy",
      "entry_mode": "initial",
      "suggested_lots": 0.01,
      "reason": "v1_trend_alignment_long",
      "expires_at_utc": "2026-04-15T14:05:00Z"
    }
  ]
}
```

## Field meanings

### Top-level
- `generated_at_utc`: when the Python master generated the file
- `version`: schema version for compatibility
- `pairs`: list of pair-specific entry intents

### Per-pair fields
- `pair`: symbol identifier
- `should_enter`: whether Python currently authorizes starting a new basket
- `direction`: `buy`, `sell`, or `none`
- `entry_mode`: for example `initial`, later maybe `scale_in`
- `suggested_lots`: optional lot hint
- `reason`: human/debug string from Python side
- `expires_at_utc`: stale protection for entry intent
- `debug`: (v2 only) alignment score, volatility regime, trend strength for diagnostics

## V2 entry intent logic

The v2 signal replaces the simple "all timeframes same sign" rule with:

1. **Volatility regime filter**
   - Compute ATR fraction (60-bar average range / price)
   - Reject entries in `dead_chop` (ATR frac < 0.0003) or `extreme_vol` (ATR frac > 0.008)

2. **Weighted alignment score**
   - Score each timeframe (5m weight=1, 15m weight=2, 60m weight=3, 240m weight=4)
   - Direction = weighted majority
   - Alignment score = total weight in majority direction / total weight
   - Require alignment score >= 0.5 (at least 2 of 3 major TFs agree)

3. **Trend strength filter**
   - Trend strength = 0.4 * |ret_60m| + 0.6 * |ret_240m|
   - Must be between 0.0002 and 0.015 (too weak = noise, too strong = chasing)

4. **Short-term counter-move filter**
   - If 5m return strongly opposes the direction and is >50% of 15m magnitude, skip
   - Prevents entering against an active reversal

## Slave behavior

The MQL5 slave should treat entry intent as:
- necessary for starting a new basket
- not sufficient on its own for execution

Execution still requires:
1. fresh policy state
2. policy gate allows new entries
3. risk overlay passes
4. no local execution blockers
5. fresh, unexpired entry intent authorizes entry

Note:
- when `grid_policy.json` uses `grid_mode=both_sides` and `seed_mode=both_sides`, MQL5 may open both a buy and sell starter from an empty basket even if entry intent is directional
- entry intent still acts as a gate for whether basket start is allowed at all

## Recommended enforcement order

For first basket entry:
1. read pair risk policy
2. validate policy freshness
3. pass execution gate
4. pass risk overlay
5. read entry intent for the pair
6. validate `should_enter == true`
7. validate `direction != none`
8. validate `expires_at_utc` still valid
9. only then call `TradeExecutor`

## Important boundary rule

If Python does not explicitly authorize a first entry, the MQL5 slave should not invent one.

This is the core rule that keeps the master/slave split clean.

## Suggested next implementation steps

### Python side
1. define an `entry_intent.json` generator
2. publish it into the MT5 handoff area
3. version the schema

### MQL5 side
1. add an `EntryIntentReader`
2. update `EntrySignal` to consume entry intent instead of local direction logic
3. allow `GridManager` to route first-entry requests through that reader

## Recommended v1 simplification

For v1, restrict Python-owned entry intent to:
- first entry only
- one action per pair
- short expiration window
- no scale-in instructions yet

That keeps the handoff simple and safe while the slave remains responsible for basket management and policy enforcement.
