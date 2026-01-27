# Quick Start: 5-Min → 15-Min Candle Aggregation

## The Issue (Fixed!)
You had 5-minute candles in `live_candles_5min` but no 15-minute candles being generated in `live_candles_15min`.

## Why It Was Happening
The original system only built candles directly from ticks. It needed a **separate aggregation mechanism** to build 15-minute candles from 5-minute candles.

## The Solution (3 Options)

### Option 1: Run the Aggregation Script (Easiest)
```bash
# For one symbol
python scripts/aggregate_5min_to_15min.py RELIANCE

# For all symbols with data
python scripts/aggregate_5min_to_15min.py --all
```

### Option 2: Use Python Directly
```python
from core.database_handler import DatabaseHandler
from core.hourly_candle_builder import aggregate_5min_to_15min

db = DatabaseHandler()

# Get last 15 5-minute candles
result = db.aggregate_5min_to_15min('RELIANCE')

# Save to 15-minute table
if result:
    db.save_candles([result], 'live_candles_15min')
```

### Option 3: Manual Aggregation with DataFrame
```python
import pandas as pd
from core.database_handler import DatabaseHandler
from core.hourly_candle_builder import aggregate_5min_to_15min

db = DatabaseHandler()

# Fetch 5-minute candles
query = """
    SELECT datetime, open, high, low, close, volume, instrument_token
    FROM live_candles_5min
    WHERE tradingsymbol = 'RELIANCE'
    ORDER BY datetime DESC
    LIMIT 100
"""
# Execute query and load into DataFrame
df = pd.read_sql(query, db.engine)

# Aggregate
result = aggregate_5min_to_15min('RELIANCE', df)

# Save
db.save_candles([result], 'live_candles_15min')
```

## Candle Timing Reference

| 5-Min Candle | → Grouped | → 15-Min Candle |
|---|---|---|
| 9:05 | ┐ | **9:00** (closes at 9:15) |
| 9:10 | ├→ |  |
| 9:15 | ┘ |  |
| 9:20 | ┐ | **9:15** (closes at 9:30) |
| 9:25 | ├→ |  |
| 9:30 | ┘ |  |

## Files Added/Modified

✅ **Added:**
- `core/hourly_candle_builder.py` - `aggregate_5min_to_15min()` function
- `core/database_handler.py` - `aggregate_5min_to_15min()` method
- `scripts/aggregate_5min_to_15min.py` - Aggregation script
- `tests/test_5min_to_15min_aggregation.py` - Test suite

✅ **Tests Passing:**
```
✓ First 15-min candle aggregation
✓ Second 15-min candle aggregation
✓ Edge case handling (< 3 candles)
```

## Real-Time Integration (Future)

To automate this in your live data feed, modify `DataFeedService._on_candle_complete()` to:

1. Save 5-minute candles
2. Every 3rd 5-minute candle close → Aggregate and save 15-minute candle
3. Every 4th 15-minute candle close → Aggregate and save 60-minute candle

See [5MIN_TO_15MIN_AGGREGATION.md](5MIN_TO_15MIN_AGGREGATION.md) for implementation details.

## Verify It Works

Check your database:
```sql
-- See the aggregated 15-minute candles
SELECT datetime, open, high, low, close, volume 
FROM live_candles_15min 
WHERE tradingsymbol = 'RELIANCE' 
ORDER BY datetime DESC 
LIMIT 10;
```

Done! 🎉
