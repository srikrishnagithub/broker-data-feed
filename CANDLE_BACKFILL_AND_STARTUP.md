# Candle Backfill and Startup Initialization

## Overview

The broker data feed now includes **automatic backfill functionality** that detects and regenerates missing 15-minute and 60-minute candles from available lower-timeframe data on startup.

This ensures data integrity even if the system was shut down or missed data during a period.

## How It Works

### The Problem It Solves

If the system was down or there was an issue, you might have:
```
✓ 5-minute candles:   9:00-9:05, 9:05-9:10, 9:10-9:15, ... (continuous)
✗ 15-minute candles:  GAP (missing some)
✗ 60-minute candles:  GAP (missing some)
```

### The Solution

On startup, the system:
1. **Checks for missing 15-minute candles** using available 5-minute data
2. **Checks for missing 60-minute candles** using available 15-minute data (including newly backfilled ones)
3. **Aggregates and stores** any missing candles in the database

### Example

**Available 5-minute candles:**
```
9:00, 9:05, 9:10, 9:15, 9:20, 9:25, 9:30, 9:35, 9:40, 9:45, 9:50, 9:55
```

**Step 1: Check 15-minute candles**
- Expected: 9:00, 9:15, 9:30, 9:45
- Check if they exist in database
- If missing, create them from 5-minute data:
  - 9:00 ← aggregate 9:00, 9:05, 9:10
  - 9:15 ← aggregate 9:15, 9:20, 9:25
  - 9:30 ← aggregate 9:30, 9:35, 9:40
  - 9:45 ← aggregate 9:45, 9:50, 9:55

**Step 2: Check 60-minute candles**
- Expected: 9:00
- Check if it exists in database
- If missing, create from 15-minute data:
  - 9:00 ← aggregate 9:00, 9:15, 9:30, 9:45 (four 15-min candles)

## Implementation

### Key Functions in DatabaseHandler

#### `backfill_missing_15min_candles(symbol: str) -> int`
```python
# Detects missing 15-minute candles and creates them from 5-minute data
backfilled_count = db.backfill_missing_15min_candles('RELIANCE')
# Returns: number of 15-min candles created
```

**Algorithm:**
1. Fetch all 5-minute candles for the symbol
2. Get all existing 15-minute candles
3. Group 5-minute candles into sets of 3
4. For each group, calculate the expected 15-minute timestamp
5. If that timestamp is missing from the database, create it
6. Save to `live_candles_15min`

#### `backfill_missing_60min_candles(symbol: str) -> int`
```python
# Detects missing 60-minute candles and creates them from 15-minute data
backfilled_count = db.backfill_missing_60min_candles('RELIANCE')
# Returns: number of 60-min candles created
```

**Algorithm:**
1. Fetch all 15-minute candles for the symbol
2. Get all existing 60-minute candles
3. Group 15-minute candles into sets of 4 (4 × 15-min = 60-min)
4. For each group, calculate the expected 60-minute timestamp
5. If that timestamp is missing from the database, create it
6. Save to `live_candles_60min`

#### `startup_backfill_all_symbols() -> Dict[str, Dict[str, int]]`
```python
# Runs backfill for all symbols in the system
results = db.startup_backfill_all_symbols()

# Returns:
# {
#     'RELIANCE': {'15min_backfilled': 10, '60min_backfilled': 2},
#     'INFY': {'15min_backfilled': 5, '60min_backfilled': 1},
#     ...
# }
```

## Usage

### Automatic on Startup

The backfill is **automatically called** when `main.py` starts:

```bash
python main.py --symbols-from-db
```

You'll see in the logs:
```
[2026-01-02 10:30:45] [INFO] Step 1: Performing startup backfill of missing 15-min and 60-min candles...
[2026-01-02 10:30:46] [INFO] Backfilling RELIANCE...
[2026-01-02 10:30:47] [INFO] Backfilled 10 15-minute candles for RELIANCE
[2026-01-02 10:30:47] [INFO] Backfilled 2 60-minute candles for RELIANCE
...
[2026-01-02 10:30:48] [SUCCESS] ✓ Backfill complete: 45 x 15-min, 12 x 60-min candles
```

### Manual Backfill (Standalone)

Run the standalone script:

```bash
# Run backfill for all symbols
python scripts/startup_initialization.py
```

Or use Python directly:

```python
from core.database_handler import DatabaseHandler

db = DatabaseHandler()

# Backfill all symbols
results = db.startup_backfill_all_symbols()

# Or backfill specific symbol
db.backfill_missing_15min_candles('RELIANCE')
db.backfill_missing_60min_candles('RELIANCE')

db.close()
```

## Files Added/Modified

✅ **Added:**
- `core/database_handler.py` - Three new methods:
  - `backfill_missing_15min_candles()`
  - `backfill_missing_60min_candles()`
  - `startup_backfill_all_symbols()`
- `scripts/startup_initialization.py` - Standalone startup script
- `tests/test_backfill_candles.py` - Test suite for backfill logic

✅ **Modified:**
- `main.py` - Added call to `startup_backfill_all_symbols()` during startup

## Test Results

All backfill tests passing ✓

```
✓ Test: Backfill Missing 15-Minute Candles
  - Creates 4 x 15-min candles from 12 x 5-min candles
  
✓ Test: Backfill Missing 60-Minute Candles
  - Creates 2 x 60-min candles from 8 x 15-min candles
  
✓ Test: Missing Candle Detection
  - Correctly identifies and fills gaps in candle series
```

## Candle Timing Reference

### 15-Minute Candle Formation
```
5-Min Candles   →  15-Min Candle
9:00            ┐
9:05            ├→  9:00 (closes at 9:15)
9:10            ┘

9:15            ┐
9:20            ├→  9:15 (closes at 9:30)
9:25            ┘
```

### 60-Minute Candle Formation
```
15-Min Candles  →  60-Min Candle
9:00            ┐
9:15            ├→  9:00 (closes at 10:00)
9:30            ├→
9:45            ┘

10:00           ┐
10:15           ├→  10:00 (closes at 11:00)
10:30           ├→
10:45           ┘
```

## Important Notes

1. **Backfill only creates missing candles** - It doesn't modify existing ones
2. **Source must be complete** - Need at least 3 x 5-min or 4 x 15-min candles consecutively
3. **Gaps are skipped** - If there's a gap in lower-timeframe candles, those higher-timeframe periods are skipped
4. **Automatic deduplication** - Uses `on_duplicate='update'` to safely handle re-runs

## Troubleshooting

### No candles backfilled
```
→ Check if 5-minute candles exist in live_candles_5min
→ Verify the table is populated: SELECT COUNT(*) FROM live_candles_5min;
```

### Unexpected gaps in 15-minute data after backfill
```
→ This is normal if there are gaps in the 5-minute data
→ Example: If 9:00-9:10 is missing, no 9:00 15-min candle will be created
→ Backfill only works with available data
```

### Performance with large datasets
```
→ Backfill processes one symbol at a time
→ For 1000s of candles, may take a few seconds per symbol
→ Logs show progress for each symbol
```

## Future Enhancements

Possible improvements for future versions:

1. **Real-time aggregation** - Aggregate 5-min → 15-min immediately when 3rd candle closes
2. **Partial hour handling** - Support "forming" hourly candles before the hour ends
3. **Configurable retention** - Backfill only recent data (e.g., last 7 days)
4. **Multi-symbol batch processing** - Parallel backfill for faster startup

## See Also

- [5MIN_TO_15MIN_AGGREGATION.md](5MIN_TO_15MIN_AGGREGATION.md) - Aggregation mechanism details
- [QUICK_START_5MIN_TO_15MIN.md](QUICK_START_5MIN_TO_15MIN.md) - Quick start guide
- [main.py](main.py) - Main entry point with startup integration
