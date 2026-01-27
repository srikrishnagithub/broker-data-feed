# 5-Minute to 15-Minute Candle Aggregation Solution

## Problem Analysis

You were experiencing an issue where **15-minute candles were not being generated** even though you had 5-minute candle data (from 9:05 to 9:30 and beyond).

### Root Cause

The original `CandleAggregator` was designed to build candles directly from **tick data** using the `_get_candle_timestamp()` method. This method calculates candle timestamps incorrectly for aggregated timeframes.

**Example of the problem:**
- A tick at 9:30 would be mapped to a candle starting at 9:30 (incorrect)
- A tick at 9:10 would be mapped to a candle starting at 9:00 (incorrect for 15-min)

### Solution

Implemented a **hierarchical candle aggregation approach**:
```
Ticks → 5-min candles → 15-min candles → 60-min candles
```

This requires a new aggregation mechanism that builds candles from **existing lower-timeframe candles** rather than from raw ticks.

## Implementation

### 1. Added `aggregate_5min_to_15min()` function

**Location:** [core/hourly_candle_builder.py](core/hourly_candle_builder.py)

Groups 3 consecutive 5-minute candles into one 15-minute candle:

```python
def aggregate_5min_to_15min(
    symbol: str,
    candles_5min: pd.DataFrame,
    instrument_token: Optional[int] = None,
    logger=None
) -> Optional[Dict[str, Any]]:
    """
    Aggregate 5-minute candles into a single 15-minute candle.
    
    Returns:
        - open: From first 5-min candle
        - high: Maximum across all 3 candles
        - low: Minimum across all 3 candles
        - close: From last 5-min candle
        - volume: Sum of all volumes
        - datetime: Start of 15-minute period
    """
```

**Key Logic:**
```
9:05 5-min candle  ┐
9:10 5-min candle  ├─→ 9:00-9:15 15-min candle (closes at 9:15)
9:15 5-min candle  ┘

9:20 5-min candle  ┐
9:25 5-min candle  ├─→ 9:15-9:30 15-min candle (closes at 9:30)
9:30 5-min candle  ┘
```

### 2. Added `aggregate_5min_to_15min()` method to DatabaseHandler

**Location:** [core/database_handler.py](core/database_handler.py)

Queries the `live_candles_5min` table and aggregates latest 3 candles:

```python
def aggregate_5min_to_15min(self, symbol: str, limit: int = 100) -> Optional[Dict[str, Any]]:
    """
    Aggregate latest 5-minute candles into a 15-minute candle from database.
    """
```

### 3. Created aggregation script

**Location:** [scripts/aggregate_5min_to_15min.py](scripts/aggregate_5min_to_15min.py)

Automatically aggregates 5-minute candles and saves to `live_candles_15min`:

```bash
# Aggregate for a specific symbol
python scripts/aggregate_5min_to_15min.py RELIANCE

# Aggregate for all symbols
python scripts/aggregate_5min_to_15min.py --all
```

### 4. Created test suite

**Location:** [tests/test_5min_to_15min_aggregation.py](tests/test_5min_to_15min_aggregation.py)

Tests the aggregation logic with sample data (all tests passing ✓)

## How It Works

### Example with Your Data

Given 5-minute candles:
| Time | Open | High | Low | Close | Volume |
|------|------|------|-----|-------|--------|
| 9:05 | 100  | 101  | 99  | 100.5 | 1000   |
| 9:10 | 100.5| 102  | 100 | 101.5 | 1200   |
| 9:15 | 101.5| 103  | 101 | 102.5 | 1100   |

**First 15-minute candle** (9:00-9:15):
- Open: 100.00 (from 9:05)
- High: 103.00 (max of 101, 102, 103)
- Low: 99.00 (min of 99, 100, 101)
- Close: 102.50 (from 9:15)
- Volume: 3300 (sum of 1000 + 1200 + 1100)
- **Timestamp: 2026-01-02 09:00:00** (start of 15-min period)

### Using the Aggregation

**Option 1: Manual aggregation**
```python
from core.database_handler import DatabaseHandler
from core.hourly_candle_builder import aggregate_5min_to_15min
import pandas as pd

db = DatabaseHandler()

# Get 5-min candles for a symbol
df_5min = db.get_candles('RELIANCE', 'live_candles_5min', limit=100)

# Aggregate to 15-min
result_15min = aggregate_5min_to_15min('RELIANCE', df_5min)

# Save to database
db.save_candles([result_15min], 'live_candles_15min', on_duplicate='update')
```

**Option 2: Use the script**
```bash
python scripts/aggregate_5min_to_15min.py RELIANCE
```

**Option 3: Database method**
```python
result = db.aggregate_5min_to_15min('RELIANCE')
db.save_candles([result], 'live_candles_15min')
```

## Next Steps

To fully integrate this with your real-time data feed:

1. **Add aggregation callback** to `DataFeedService` that aggregates 5-min candles into 15-min candles when 5-min candles close
2. **Add another aggregation layer** for 60-min candles from 15-min candles (similar pattern)
3. **Store aggregated candles** to respective tables (`live_candles_15min`, `live_candles_60min`)

### Suggested Enhancement

Modify [core/data_feed_service.py](core/data_feed_service.py) to add automatic aggregation:

```python
def _on_candle_complete(self, candles: List[Candle]):
    # Save 5-min candles
    candles_by_interval = {}
    # ... existing code ...
    
    # NEW: Aggregate 5-min to 15-min
    for symbol in completed_symbols:
        result_15min = self.database.aggregate_5min_to_15min(symbol)
        if result_15min:
            self.database.save_candles([result_15min], 'live_candles_15min')
    
    # NEW: Aggregate 15-min to 60-min
    # ... similar pattern ...
```

## Verification

The aggregation has been tested with sample data:

```
✓ First 15-minute candle: Timestamp 9:00, OHLC correct, Volume correct
✓ Second 15-minute candle: Timestamp 9:15, OHLC correct, Volume correct  
✓ Edge case: Returns None for insufficient candles (< 3)
```

All tests passing! ✓
