# MQL5 Pair Risk Policy Contract

## Purpose

This document defines how the MQL5 slave should consume and apply the pair-level policy emitted by the Python master event-risk pipeline.

Primary upstream artifact:
- `data/live/policy/pair_risk_policy.json`

## Design goal

The MQL5 slave should remain execution-focused.
It should not compute ML, reinterpret economic-calendar logic, or infer risk from raw events.
It should only:
- read policy
- validate freshness
- map policy action to execution permissions
- enforce those permissions consistently

## Source artifact schema

Expected file:
- `pair_risk_policy.json`

Top-level example:

```json
{
  "generated_at_utc": "2026-04-15T13:40:36.817753+00:00",
  "source_model": "xgb_y_avoid_session",
  "threshold_version": "avoid_session_v1",
  "pair_policies": [
    {
      "pair": "GBPJPY",
      "policy_action": "block_new_entries",
      "policy_band": "standard_avoid",
      "max_score_avoid_session": 0.67,
      "trigger_event_id": "abc123",
      "trigger_event_name": "UK CPI y/y",
      "trigger_event_timestamp_utc": "2026-04-15T12:30:00+00:00",
      "generated_at_utc": "2026-04-15T13:40:36.817753+00:00"
    }
  ]
}
```

## Required top-level fields

- `generated_at_utc`
- `source_model`
- `threshold_version`
- `pair_policies`

## Required per-pair fields

- `pair`
- `policy_action`
- `policy_band`
- `max_score_avoid_session`
- `trigger_event_id`
- `trigger_event_name`
- `trigger_event_timestamp_utc`
- `generated_at_utc`

## Supported pairs

Initial v1 universe:
- `EURJPY`
- `GBPJPY`
- `GBPUSD`
- `NZDUSD`

If a pair is not present, the slave should treat it as unsupported by this policy file, not silently infer a value.

## Supported policy actions

### 1. `allow_trading`
Meaning:
- no event-risk block from the model pipeline

Recommended MQL5 behavior:
- allow normal new entries
- allow normal position management

### 2. `soft_halt_new_entries`
Meaning:
- moderate caution band
- model is not strong enough for full avoid-session, but risk is elevated

Recommended MQL5 behavior:
- reject new entries for the pair
- continue managing existing positions
- do not force-close solely because of this action

### 3. `block_new_entries`
Meaning:
- standard avoid-session action

Recommended MQL5 behavior:
- reject all new entries for the pair
- continue managing existing positions
- optional: tighten grid expansion rules if higher-level strategy wants that, but keep this outside the contract

### 4. `block_new_entries_and_flag_strong_avoid`
Meaning:
- strongest avoid-session action

Recommended MQL5 behavior:
- reject all new entries for the pair
- continue managing existing positions unless outer risk logic chooses to flatten
- expose a `strong_avoid` flag internally so higher-level strategy logic can decide whether to:
  - reduce exposure
  - flatten
  - suspend recovery logic

## Freshness and stale-data rules

This matters a lot.
The slave should never trust policy indefinitely.

### Recommended freshness budget
Use these default checks:
- policy file age <= **10 minutes** → fresh
- policy file age > **10 minutes** and <= **30 minutes** → stale warning
- policy file age > **30 minutes** → stale fail-safe

### MQL5 stale handling

#### Fresh
- use policy normally

#### Stale warning
- continue using current policy
- raise an internal warning / log message
- optionally restrict new entries if your operational posture is conservative

#### Stale fail-safe
Recommended default:
- **fail closed for new entries** on covered pairs
- continue managing existing positions
- log explicit stale-policy error

Reason:
A dead Python master during live event risk is more dangerous than being temporarily conservative.

If you prefer a less conservative posture, make it a config option, but the default should be explicit and intentional.

## Missing-file behavior

If `pair_risk_policy.json` is missing:
- treat as policy unavailable
- default recommendation: **fail closed for new entries** on covered pairs
- continue existing position management
- emit clear log / telemetry event

## Parse-error behavior

If the JSON cannot be parsed or required fields are missing:
- treat as invalid policy
- do not attempt partial inference from malformed content
- default recommendation: **fail closed for new entries** on covered pairs
- emit clear log / telemetry event

## Pair lookup behavior

For each EA-managed pair:
1. load the latest valid policy file
2. locate exact `pair` entry
3. if found, apply `policy_action`
4. if not found:
   - treat as no valid policy for that pair
   - recommended default: fail closed for new entries on configured covered pairs

This is stricter than allow-by-default, on purpose.

## Suggested MQL5 internal state

For each managed pair, the slave should maintain at least:
- `policy_action`
- `policy_band`
- `max_score_avoid_session`
- `trigger_event_name`
- `trigger_event_timestamp_utc`
- `policy_generated_at_utc`
- `policy_age_seconds`
- `policy_status` (`fresh`, `stale_warning`, `stale_fail_safe`, `missing`, `invalid`)

## Execution decision matrix

### New entries
| Policy action | New entries |
|---|---|
| `allow_trading` | allow |
| `soft_halt_new_entries` | deny |
| `block_new_entries` | deny |
| `block_new_entries_and_flag_strong_avoid` | deny |

### Existing positions
| Policy action | Existing position management |
|---|---|
| `allow_trading` | normal |
| `soft_halt_new_entries` | normal management only |
| `block_new_entries` | normal management only |
| `block_new_entries_and_flag_strong_avoid` | normal management, optional higher-level exposure reduction |

## Logging requirements

The MQL5 slave should log at minimum:
- policy file load success/failure
- policy freshness state
- pair-level action applied
- any denied new entry due to policy
- any stale or invalid policy fail-safe activation

## Recommended polling cadence

Suggested v1 polling behavior:
- poll policy file every **30 to 60 seconds**
- reload immediately before placing a new trade if practical

The polling interval should be shorter than the freshness warning threshold.

## Contract boundaries

### Python master owns
- event ingestion
- feature generation
- model scoring
- threshold calibration
- pair policy generation

### MQL5 slave owns
- reading policy artifact
- validating freshness and integrity
- applying execution restrictions
- logging and operational safety behavior

## Recommended next implementation task

Implement an MQL5-side adapter that:
- reads `pair_risk_policy.json`
- parses UTC timestamps safely
- computes policy age
- exposes helper functions like:
  - `CanOpenNewTrade(pair)`
  - `IsStrongAvoid(pair)`
  - `GetPolicyStatus(pair)`
  - `GetTriggerEventName(pair)`
