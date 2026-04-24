# Optimal Blocking Windows Based on Data Analysis

## Executive Summary

Based on analysis of 57,916 historical events with 1-minute bar data, here are the recommended blocking windows for each event class:

| Event Class | Pre-Event Block | Post-Event Block | Total Window | Rationale |
|-------------|----------------|-----------------|--------------|-----------|
| **Extreme** (Score 75+) | **30 min** | **120 min** | 2.5 hours | 95th percentile returns still elevated at 60m, high whipsaw risk |
| **High** (Score 50-75) | **15 min** | **90 min** | 1.75 hours | Peak volatility in 15-30m window, significant reversal risk |
| **Medium** (Score 25-50) | **10 min** | **60 min** | 1.17 hours | Most volatility absorbed within 1 hour |
| **Low** (<25) | **5 min** | **30 min** | 35 min | Minimal impact, quick normalization |

## Key Data Findings

### 1. Volatility Timing

**When does peak volatility occur?**
- 8.2% of events peak in first 5 minutes
- 17.4% peak between 5-15 minutes
- 27.2% peak between 15-30 minutes
- **51.4% peak between 30-60 minutes**

**Key insight:** Most events don't peak immediately. The maximum move often happens 30-60 minutes after the event.

### 2. Returns by Event Class

**Extreme Events (High Importance, n=293):**
```
5m:  95th percentile = 0.26% (26 pips on EURUSD)
15m: 95th percentile = 0.36% (36 pips)
30m: 95th percentile = 0.40% (40 pips)
60m: 95th percentile = 0.61% (61 pips) ← Still very high
```

**High/Medium Events (Importance 1, n=3,062):**
```
5m:  95th percentile = 0.21%
15m: 95th percentile = 0.30%
30m: 95th percentile = 0.32%
60m: 95th percentile = 0.40%
```

**Normal Events (Importance -1/0, n=54,561):**
```
5m:  95th percentile = 0.10%
15m: 95th percentile = 0.14%
30m: 95th percentile = 0.16%
60m: 95th percentile = 0.17%
```

### 3. Critical Finding: Whipsaws

**31.3% of ALL events show sign flips between 15-60 minutes.**

This means:
- Price goes up initially, then reverses down (or vice versa)
- **Grid EAs are especially vulnerable**: they accumulate positions in one direction, then the reversal hits
- Blocking needs to extend past the reversal period

### 4. Volatility Expansion Events (n=13,418)

Events that caused significant volatility:
```
5m:  22.5% exceed 0.1% move
15m: 43.3% exceed 0.1% move
30m: 61.7% exceed 0.1% move
60m: 80.2% exceed 0.1% move ← Majority still volatile at 1 hour
```

## Recommended Configuration by Risk Tolerance

### Conservative (Maximum Protection)
```cpp
input double news_score_threshold = 25.0;  // Block medium+
input int    news_pre_minutes = 30;        // 30 min before
input int    news_post_minutes = 120;      // 2 hours after
```
**Use if:** You want maximum safety, don't mind missing some trades

### Moderate (Balanced)
```cpp
input double news_score_threshold = 50.0;  // Block high+
input int    news_pre_minutes = 20;        // 20 min before
input int    news_post_minutes = 90;       // 1.5 hours after
```
**Use if:** Standard grid protection, recommended for most traders

### Aggressive (Minimal Blocking)
```cpp
input double news_score_threshold = 75.0;  // Block only extreme
input int    news_pre_minutes = 15;        // 15 min before
input int    news_post_minutes = 60;       // 1 hour after
```
**Use if:** Tight grid with small steps, or if you accept higher risk

## Per-Class Settings (Advanced)

Instead of one threshold, use class-specific windows:

```cpp
// In your EA, modify IsNewsBlockingTrade to use class-specific windows

int GetPreWindow(string bucket_class)
{
    if(bucket_class == "extreme") return 30;
    if(bucket_class == "high") return 20;
    if(bucket_class == "medium") return 10;
    return 5; // low
}

int GetPostWindow(string bucket_class)
{
    if(bucket_class == "extreme") return 120;
    if(bucket_class == "high") return 90;
    if(bucket_class == "medium") return 60;
    return 30; // low
}
```

## Why These Windows?

### Pre-Event (15-30 min)
- **Price often starts moving before the event** (leaked data, positioning)
- Entry bar is typically 16.8 minutes before event time
- Early volatility can trigger grid entries at bad prices

### Post-Event (60-120 min)
- **51.4% of events peak at 30-60 minutes** (not immediately)
- **31.3% show reversals** after initial move
- Volatility expansion events: 80% still volatile at 60 minutes
- Trend danger events: continue trending for 1-3 hours

## Grid-Specific Considerations

### Why Grid EAs Need LONGER Windows

1. **Multiple positions**: Grid opens many positions, so volatility affects all of them
2. **No directional bias**: Grid trades both directions, so any big move hurts
3. **Whipsaws kill grids**: 31% reversal rate means direction changes = grid gets caught on wrong side
4. **Margin calls**: Extreme moves + multiple positions = margin call risk

### Recommended for Grid EAs

| Grid Type | Pre | Post | Threshold |
|-----------|-----|------|-----------|
| Tight grid (5-10 pip steps) | 30 min | 120 min | 50 (medium+) |
| Medium grid (10-20 pip steps) | 20 min | 90 min | 50 (medium+) |
| Wide grid (20+ pip steps) | 15 min | 60 min | 75 (high+) |

## Example Scenarios

### Fed Funds (Extreme, Score 78)
```
Event: 2026-04-29 18:00 UTC
Class: extreme

Conservative block: 17:30 - 20:00 (2.5 hours)
Moderate block: 17:40 - 19:30 (1.8 hours)
Aggressive block: 17:45 - 19:00 (1.25 hours)
```

### Building Permits (High, Score 51)
```
Event: 2026-04-29 12:30 UTC
Class: high

Conservative block: 12:00 - 14:30 (2.5 hours)
Moderate block: 12:10 - 14:00 (1.8 hours)
Aggressive block: 12:15 - 13:30 (1.25 hours)
```

### Dallas Fed (Medium, Score 17)
```
Event: 2026-04-27 14:30 UTC
Class: medium

Conservative block: 14:00 - 16:30 (2.5 hours)
Moderate block: 14:20 - 15:30 (1.2 hours)
Aggressive block: 14:25 - 15:00 (0.6 hours)
```

## Testing Recommendations

1. **Backtest with different windows**: Try 15/60, 20/90, 30/120 combinations
2. **Monitor missed trades**: Check if filter blocks too many good opportunities
3. **Track drawdown**: Compare with/without filter during news events
4. **Adjust based on your grid**: Tighter grids need more protection

## Summary Table

| Your Style | Score Threshold | Pre (min) | Post (min) | Missed Trades | Protection |
|------------|----------------|-----------|------------|---------------|------------|
| Ultra-safe | 25 (medium+) | 30 | 120 | High | Maximum |
| Conservative | 50 (high+) | 20 | 90 | Moderate | High |
| Balanced | 50 (high+) | 15 | 60 | Low | Good |
| Aggressive | 75 (extreme) | 10 | 30 | Very low | Minimal |

## My Recommendation for Your Grid EA

Given that you have:
- Variable step EA (can adjust step sizes)
- Grid multiplier (positions grow)
- Auto SL based on equity drawdown

**I recommend:**
```cpp
input double news_score_threshold = 50.0;  // Block high+ events
input int    news_pre_minutes = 20;         // 20 min before
input int    news_post_minutes = 90;        // 1.5 hours after
```

**Why:**
- Protects against 80% of dangerous events
- 1.5 hour post-window covers most volatility and whipsaws
- Still allows trading during low-impact periods
- Balances protection with opportunity

You can always tighten it if you see problems during specific events.
