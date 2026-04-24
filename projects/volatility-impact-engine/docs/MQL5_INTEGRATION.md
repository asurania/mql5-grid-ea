# ML-Driven Volatility Impact Engine - MQL5 Integration Guide

## Overview

This guide explains how to integrate the ML-driven news impact filter into your existing Grid EA.

## What Was Changed

### 1. New Include File: `MQL5/Include/NewsImpactFilter.mqh`
This library handles:
- Loading event scores from CSV
- Checking if current time/symbol is blocked
- Displaying active/next events in comments

### 2. Modified EA: `MQL5/Experts/ConvertedGridEA.mq5`
Added:
- `#include <NewsImpactFilter.mqh>` at top
- 5 new input parameters for news filter
- News check before every trade
- Active event display in chart comments

## New Input Parameters

```
s_news=""                           // Separator
use_news_filter=true                // Enable/disable filter
news_csv_file="event_scores.csv"    // CSV filename
news_score_threshold=50.0           // Score to block (0-100)
news_pre_minutes=15                 // Block before event (min)
news_post_minutes=60                // Block after event (min)
```

## How It Works

1. **On Init**: EA loads CSV file into memory
2. **On Every Tick**: 
   - Checks if current symbol has active high-score events
   - If blocked: sets `action_stop=true` (stops new entries)
   - If not blocked: allows normal trading
3. **Auto-refresh**: CSV reloads every hour (or on restart)

## CSV File Format

Place in `MQL5/Files/event_scores.csv`:

```csv
Date,Forex Symbol,Calendar Event,Score,Bucket Class
2026-04-29 18:00:00+00:00,EURUSD,Fed Funds Tgt Rate,78.33,extreme
2026-04-29 18:00:00+00:00,GBPUSD,Fed Funds Tgt Rate,78.33,extreme
2026-04-29 12:30:00+00:00,EURUSD,Building Permits: Number,51.09,high
```

## Integration Steps

### Step 1: Copy Files
```bash
# Copy include file
cp MQL5/Include/NewsImpactFilter.mqh "C:\Program Files\MetaTrader 5\MQL5\Include\"

# Copy modified EA
cp MQL5/Experts/ConvertedGridEA.mq5 "C:\Program Files\MetaTrader 5\MQL5\Experts\"
```

### Step 2: Generate Weekly CSV
Run Python script weekly (or set up cron):
```bash
cd /home/asurani/.openclaw/workspace/projects/volatility-impact-engine
source .venv/bin/activate
python src/score_future_events_all_pairs.py --start-date 2026-04-27 --end-date 2026-05-03 --currency ALL
```

### Step 3: Copy CSV to MT5
Copy generated file to MT5 Files folder:
```bash
# From Linux/WSL
cp data/future_event_scores_*.csv /mnt/c/Users/YourName/AppData/Roaming/MetaQuotes/Terminal/*/MQL5/Files/

# Or from Windows
copy data\future_event_scores_*.csv "C:\Program Files\MetaTrader 5\MQL5\Files\event_scores.csv"
```

### Step 4: Compile and Run
1. Open MetaEditor
2. Compile `ConvertedGridEA.mq5` (F7)
3. Attach to chart
4. Set input parameters as desired
5. Enable "Allow DLL imports" if prompted

## Configuration Examples

### Current requested setup
```
use_news_filter=true
news_score_threshold=50.0
news_pre_minutes=120
news_post_minutes=120
```

Behavior:
- score >= 50 blocks around the event
- news block uses the EA's existing `time_action` setting
- so during the block it will:
  - `close_all_trades`, or
  - `stop_entering_new_trades`, or
  - `managed_closing_of_trades`
  depending on your EA input

### If you want a lighter setup later
```
use_news_filter=true
news_score_threshold=75.0
news_pre_minutes=30
news_post_minutes=90
```

## Troubleshooting

### "News impact file not found"
- Ensure CSV is in `MQL5/Files/` directory
- Check filename matches `news_csv_file` input
- Use TerminalInfoString(TERMINAL_DATA_PATH) to find correct path

### "Filter not blocking trades"
- Check that event scores ≥ threshold
- Verify symbol matches exactly (EURUSD not EUR/USD)
- Check that pre/post minutes are appropriate

### "Too many trades blocked"
- Increase `news_score_threshold` (try 75)
- Reduce `news_pre_minutes` and `news_post_minutes`

## Weekly Automation

### Linux/Mac Cron Job
```bash
# Edit crontab
crontab -e

# Add weekly job (Sundays at 6 PM)
0 18 * * 0 cd /home/asurani/.openclaw/workspace/projects/volatility-impact-engine && source .venv/bin/activate && python src/score_future_events_all_pairs.py --start-date $(date +\%Y-\%m-\%d) --end-date $(date -d '+7 days' +\%Y-\%m-\%d) --currency ALL
```

### Windows Task Scheduler
1. Create new task, weekly trigger (Sundays)
2. Action: Start a program
3. Program: `pythonw.exe`
4. Arguments: `src/score_future_events_all_pairs.py --start-date ... --end-date ...`

## Files Summary

| File | Purpose |
|------|---------|
| `MQL5/Include/NewsImpactFilter.mqh` | News filter library |
| `MQL5/Experts/ConvertedGridEA.mq5` | Modified EA with integration |
| `src/score_future_events_all_pairs.py` | Python script to generate CSV |
| `data/future_event_scores_*.csv` | Generated forecast files |

## Next Steps

1. **Backtest**: Test with historical data to verify filter effectiveness
2. **Optimize**: Adjust threshold/pre/post minutes for your trading style
3. **Automate**: Set up weekly cron job for hands-free operation
4. **Monitor**: Check logs to ensure filter is working correctly

## Support

For issues or questions:
1. Check CSV file exists and is readable
2. Verify symbol naming matches exactly
3. Enable debug logging in NewsImpactFilter.mqh
4. Review MT5 Experts tab for error messages
