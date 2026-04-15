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
      "reason": "python_signal_long_regime_alignment",
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
