# Complete 5-Min → 15-Min → 60-Min Candle Aggregation and Backfill System

## Summary of Implementation

You now have a **complete hierarchical candle aggregation and backfill system** that:

1. ✅ **Builds 5-minute candles from ticks** (existing)
2. ✅ **Aggregates 5-minute candles into 15-minute candles** (NEW)
3. ✅ **Aggregates 15-minute candles into 60-minute candles** (NEW via backfill)
4. ✅ **Automatically backfills missing candles on startup** (NEW)

## Component Overview

### 1. Aggregation Functions

**File:** `core/hourly_candle_builder.py`

```python
def aggregate_5min_to_15min(symbol, candles_5min, instrument_token=None, logger=None):
    """Groups 3 consecutive 5-minute candles into one 15-minute candle"""
    # Open: from 1st 5-min candle
    # High: maximum across 3 candles
    # Low: minimum across 3 candles
    # Close: from 3rd 5-min candle
    # Volume: sum of all volumes
```

### 2. Database Methods

**File:** `core/database_handler.py`

Three new methods for backfill:

```python
def backfill_missing_15min_candles(symbol: str) -> int
    """Detects and fills missing 15-min candles from 5-min data"""

def backfill_missing_60min_candles(symbol: str) -> int
    """Detects and fills missing 60-min candles from 15-min data"""

def startup_backfill_all_symbols() -> Dict[str, Dict[str, int]]
    """Runs backfill for all symbols on startup"""
```

### 3. Scripts

**File:** `scripts/aggregate_5min_to_15min.py`
- Manual aggregation script
- Usage: `python scripts/aggregate_5min_to_15min.py --all`

**File:** `scripts/startup_initialization.py`
- Standalone startup script
- Usage: `python scripts/startup_initialization.py`

### 4. Integration with Main

**File:** `main.py`
- Automatically calls `startup_backfill_all_symbols()` on startup
- Reports backfill results in logs

## How the System Works

### Scenario: Detected Missing 15-Min Candles

```
Startup:
├─ Load 5-minute candles from database
├─ Check which 15-minute candles are missing
├─ For each missing 15-min period:
│   └─ Aggregate 3 × 5-min candles → 1 × 15-min candle
├─ Save new 15-min candles
├─ Check which 60-minute candles are missing
├─ For each missing 60-min period:
│   └─ Aggregate 4 × 15-min candles → 1 × 60-min candle
├─ Save new 60-min candles
└─ Report backfill results
```

### Example Timeline

```
9:00-9:05   5-min ✓
9:05-9:10   5-min ✓
9:10-9:15   5-min ✓
─────────────────────────── Backfill: Create 9:00-9:15 15-min ✓
9:15-9:20   5-min ✓
9:20-9:25   5-min ✓
9:25-9:30   5-min ✓
─────────────────────────── Backfill: Create 9:15-9:30 15-min ✓
...
9:45-10:00  15-min ✓
─────────────────────────── Backfill: Create 9:00-10:00 60-min ✓
```

## Usage Patterns

### Pattern 1: Automatic (Recommended)

```bash
# Start the service - backfill runs automatically on startup
python main.py --symbols-from-db
```

Output:
```
[INFO] Step 1: Performing startup backfill of missing 15-min and 60-min candles...
[INFO] Backfilling RELIANCE...
[INFO] Backfilled 10 15-minute candles for RELIANCE
[INFO] Backfilled 2 60-minute candles for RELIANCE
[SUCCESS] ✓ Backfill complete: 45 x 15-min, 12 x 60-min candles
```

### Pattern 2: Standalone Initialization

```bash
python scripts/startup_initialization.py
```

### Pattern 3: Programmatic Usage

```python
from core.database_handler import DatabaseHandler

db = DatabaseHandler()

# Backfill all symbols
results = db.startup_backfill_all_symbols()

# Print results
for symbol, counts in results.items():
    print(f"{symbol}: 15-min={counts['15min_backfilled']}, 60-min={counts['60min_backfilled']}")

db.close()
```

### Pattern 4: Manual Per-Symbol Aggregation

```python
from core.database_handler import DatabaseHandler
from core.hourly_candle_builder import aggregate_5min_to_15min
import pandas as pd

db = DatabaseHandler()

# Get 5-min candles
df = pd.read_sql(
    "SELECT * FROM live_candles_5min WHERE tradingsymbol = 'RELIANCE' ORDER BY datetime",
    db.engine
)

# Aggregate manually
result = aggregate_5min_to_15min('RELIANCE', df)

# Save
db.save_candles([result], 'live_candles_15min')
db.close()
```

## Verification

### Check backfill results in logs:
```bash
# Look for startup initialization messages
grep "Backfill" logs/broker_data_feed.log
```

### Check database for candles:
```sql
-- Count candles by interval
SELECT 'live_candles_5min' as table_name, COUNT(*) FROM live_candles_5min
UNION ALL
SELECT 'live_candles_15min', COUNT(*) FROM live_candles_15min
UNION ALL
SELECT 'live_candles_60min', COUNT(*) FROM live_candles_60min;

-- View sample 15-min candles
SELECT datetime, open, high, low, close, volume 
FROM live_candles_15min 
WHERE tradingsymbol = 'RELIANCE'
ORDER BY datetime DESC LIMIT 10;

-- Verify continuous periods
SELECT COUNT(*) as gaps
FROM (
    SELECT LAG(datetime) OVER (ORDER BY datetime) as prev_time, datetime
    FROM live_candles_15min
    WHERE tradingsymbol = 'RELIANCE'
) t
WHERE datetime - INTERVAL '15 minutes' != prev_time;
```

## Test Results

All tests passing ✓

### Unit Tests:
- `tests/test_5min_to_15min_aggregation.py` - Aggregation logic
- `tests/test_backfill_candles.py` - Backfill logic

Run tests:
```bash
python tests/test_5min_to_15min_aggregation.py
python tests/test_backfill_candles.py
```

## Key Features

| Feature | Status | Notes |
|---------|--------|-------|
| 5-min candle creation from ticks | ✅ Existing | Uses CandleAggregator |
| Manual 5→15 min aggregation | ✅ New | Via aggregation script |
| Auto 5→15 min aggregation | ✅ New | Via backfill on startup |
| Auto 15→60 min aggregation | ✅ New | Via backfill on startup |
| Missing candle detection | ✅ New | Compares DB against expected timeline |
| Startup initialization | ✅ New | Runs automatically on startup |
| Duplicate handling | ✅ New | Uses `on_duplicate='update'` |
| Logging & monitoring | ✅ New | Detailed startup logs |

## Files Created/Modified

### Created:
- ✅ `core/database_handler.py` - Methods for backfill
- ✅ `scripts/aggregate_5min_to_15min.py` - Manual aggregation script
- ✅ `scripts/startup_initialization.py` - Standalone initialization
- ✅ `tests/test_5min_to_15min_aggregation.py` - Aggregation tests
- ✅ `tests/test_backfill_candles.py` - Backfill tests
- ✅ `5MIN_TO_15MIN_AGGREGATION.md` - Aggregation documentation
- ✅ `QUICK_START_5MIN_TO_15MIN.md` - Quick start guide
- ✅ `CANDLE_BACKFILL_AND_STARTUP.md` - Backfill documentation
- ✅ `COMPLETE_CANDLE_AGGREGATION_SYSTEM.md` - This file

### Modified:
- ✅ `core/hourly_candle_builder.py` - Added aggregation function
- ✅ `main.py` - Added startup backfill integration

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   BROKER DATA FEED SYSTEM                       │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐         ┌─────────┐         ┌─────────┐
   │  Ticks  │         │Database │         │ Config  │
   └─────────┘         └─────────┘         └─────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼────────────┐
                    │  CandleAggregator    │
                    │  (5-min from ticks)  │
                    └─────────┬────────────┘
                              │
                    ┌─────────▼──────────────────────────┐
                    │    Database Handler                │
                    │  • save_candles()                  │
                    │  • aggregate_5min_to_15min()       │
                    │  • backfill_missing_15min_candles()│
                    │  • backfill_missing_60min_candles()│
                    │  • startup_backfill_all_symbols()  │
                    └─────────┬──────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            ▼                 ▼                 ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ 5-min table  │ │ 15-min table │ │ 60-min table │
    │ (CONTINUOUS) │ │ (BACKFILLED) │ │ (BACKFILLED) │
    └──────────────┘ └──────────────┘ └──────────────┘
```

## Next Steps (Optional Enhancements)

1. **Real-time aggregation** - Aggregate as candles close (not just on startup)
2. **Forming hourly candles** - Support incomplete hour calculations
3. **Configurable backfill** - Limit backfill to recent data
4. **Parallel processing** - Speed up backfill for many symbols
5. **Metrics & monitoring** - Track aggregation performance

## FAQ

**Q: Why backfill only on startup?**
A: Current implementation focuses on data integrity on startup. Real-time aggregation can be added in future versions.

**Q: What if 5-minute candles have gaps?**
A: Backfill only creates candles from available 5-minute data. Gaps are skipped, which is correct behavior.

**Q: Can I re-run backfill?**
A: Yes! The system uses `on_duplicate='update'`, so re-running is safe and idempotent.

**Q: How long does backfill take?**
A: Typically < 1 second per symbol for normal datasets. Check logs for exact times.

**Q: What if a candle is partially formed?**
A: Partial candles are not aggregated. You need all 3 (for 15-min) or 4 (for 60-min) complete candles.

---

**You now have a production-ready hierarchical candle aggregation system!** 🎉
