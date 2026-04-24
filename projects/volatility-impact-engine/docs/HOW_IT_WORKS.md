# How the News Impact Filter Works

## Overview

The news filter reads a CSV file of upcoming economic events with ML-generated risk scores. It blocks the EA from entering new trades during high-risk periods around these events.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EA Logic Flow                            │
└─────────────────────────────────────────────────────────────┘

OnInit():
    │
    ├─► LoadNewsImpactFile("event_scores.csv")
    │       │
    │       └─► Read CSV into memory
    │
    └─► EA starts running

OnTick():
    │
    ├─► calc()
    │     │
    │     ├─► check_time()              (existing time filters)
    │     │
    │     ├─► NEWS FILTER CHECK (NEW)
    │     │     │
    │     │     ├─► LoadNewsImpactFile()   (reloads every hour)
    │     │     │
    │     │     ├─► IsNewsBlockingTrade()
    │     │     │     │
    │     │     │     ├─► Check if symbol matches
    │     │     │     ├─► Check if score >= threshold
    │     │     │     └─► Check if current time in [event-pre, event+post]
    │     │     │
    │     │     ├─► If BLOCKED:
    │     │     │     └─► action_stop = true
    │     │     │     └─► return (no new trades)
    │     │     │
    │     │     └─► If NOT blocked:
    │     │           └─► action_stop = false
    │     │           └─► Continue normal trading
    │     │
    │     ├─► check_orders()            (existing order management)
    │     │
    │     └─► trade(buy/sell)           (only if not blocked)
    │
    └─► OnDeinit():
          └─► CleanupNewsFilter()       (free memory)
```

## Step-by-Step Logic

### Step 1: Load Events (OnInit + Hourly Refresh)

```mql5
// At startup and every hour
LoadNewsImpactFile("event_scores.csv")

// Reads CSV:
// Date,Forex Symbol,Calendar Event,Score,Bucket Class
// 2026-04-29 18:00:00,EURUSD,Fed Funds,78.3,extreme

// Stores in memory as array of structs:
news_events[0] = {date: Apr 29 18:00, symbol: "EURUSD", score: 78.3}
```

### Step 2: Check Each Tick (OnTick → calc())

```mql5
// Current time: Apr 29 17:45
// Current symbol: EURUSD

IsNewsBlockingTrade(
    "EURUSD",        // symbol
    50.0,            // threshold (blocks medium/high/extreme)
    15,              // pre_minutes (block 15 min before)
    60               // post_minutes (block 60 min after)
)

// Checks:
// 1. Symbol match: "EURUSD" == "EURUSD" ✓
// 2. Score >= 50: 78.3 >= 50.0 ✓
// 3. Time in window: 
//    block_start = 18:00 - 15 min = 17:45
//    block_end   = 18:00 + 60 min = 19:00
//    Current time: 17:45 ✓ (YES, blocked)

// Returns: TRUE → action_stop = true
```

### Step 3: Trading Decision

```mql5
if(action_stop) {
    // BLOCKED - No new trades
    // Existing positions continue to run
    // Grid can still close/manage positions
    return;
}

// NOT BLOCKED - Normal trading
if(s==0 && bid>ma) { trade(sell); }
if(b==0 && bid<ma) { trade(buy); }
```

## Time Window Example

```
Event: Fed Funds Rate at 18:00 UTC
Score: 78.3 (extreme)
Settings: pre=15min, post=60min

Time:    17:30    17:45    18:00    18:30    19:00    19:15
         │        │        │        │        │        │
Block:   │████████│████████│████████│████████│        │
                  │←─pre───│──event─│──post──│→
         
         Trading  NO TRADE  NO TRADE  NO TRADE  Trading
         Allowed  (blocked) (blocked) (blocked) Allowed
```

## Decision Flowchart

```
EA wants to enter trade
        │
        ▼
┌─────────────────┐
│ use_news_filter │
│    enabled?     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
   YES       NO
    │         │
    ▼         ▼
┌──────────┐ ┌──────────┐
│ CSV file │ │ Continue │
│ loaded?  │ │ trading  │
└────┬─────┘ └──────────┘
     │
┌────┴────┐
│         │
YES       NO
 │        │
 │        ▼
 │   ┌──────────┐
 │   │ Log      │
 │   │ warning  │
 │   │ (no file)│
 │   └────┬─────┘
 │        │
 │        ▼
 │   ┌──────────┐
 │   │ Continue │
 │   │ trading  │
 │   └──────────┘
 │
 ▼
┌─────────────────────┐
│ Symbol in CSV?      │
│ And score >= thresh?│
│ And time in window? │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    │           │
   YES          NO
    │           │
    ▼           ▼
┌──────────┐ ┌──────────┐
│ BLOCKED  │ │ Continue │
│ action_  │ │ trading  │
│ stop=true│ │ normally │
└──────────┘ └──────────┘
```

## Key Points

### What Gets Blocked
- ✅ New trade entries (buy/sell grid positions)
- ✅ Grid additions (stepping into more positions)

### What Still Works
- ✅ Existing positions continue to run
- ✅ Take profit adjustments
- ✅ Stop loss / equity protection
- ✅ Manual closes (via buttons)
- ✅ Time-based filters (separate system)

### Multiple Events
If multiple events overlap, the EA blocks until the **last event window ends**:
```
Event A: 12:00 (score 78) → Block 11:45-13:00
Event B: 12:30 (score 51) → Block 12:15-13:30

Combined: Block from 11:45 to 13:30 (last event ends)
```

### Symbol Matching
The filter checks if the event's symbol matches the chart symbol:
```
Chart: EURUSD
Event symbol: EURUSD → MATCH → Block
Event symbol: GBPUSD → NO MATCH → Allow
```

## Input Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| use_news_filter | true | Enable/disable filter |
| news_csv_file | "event_scores.csv" | CSV filename |
| news_score_threshold | 50.0 | Min score to block (0-100) |
| news_pre_minutes | 15 | Minutes before event |
| news_post_minutes | 60 | Minutes after event |

## Score Threshold Guide

| Threshold | Blocks | Risk Level |
|-----------|--------|------------|
| 25 | Low+ events | Very conservative |
| 50 | Medium+ events | Conservative |
| 75 | High+ events | Moderate |
| 90 | Only extreme | Aggressive |

## Visual Feedback

The EA comment shows:
```
--- News Impact Filter ---
ACTIVE EVENTS:
18:00 Fed Funds Tgt Rate (78.3)

Or when no active events:
Next Event: 2026-04-29 12:30 Building Permits (Score: 51.3, Class: high)
```

## Files Required

1. **MQL5/Include/NewsImpactFilter.mqh** - Filter library
2. **MQL5/Files/event_scores.csv** - Event data (generated weekly)
3. **MQL5/Experts/ConvertedGridEA.mq5** - Modified EA

## Weekly Workflow

```
Sunday:
    │
    ├─► Run Python script
    │   python score_future_events_all_pairs.py
    │       │
    │       └─► Generates CSV for next 7 days
    │
    ├─► Copy CSV to MT5 Files folder
    │
    └─► Restart EA (or wait for auto-reload in 1 hour)
```
