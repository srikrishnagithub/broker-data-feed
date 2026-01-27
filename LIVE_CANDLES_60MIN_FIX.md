# Fix: live_candles_60min Not Getting Filled in Real Time

## Problem Identified

The `live_candles_60min` table is not being filled in real time because the `CANDLE_INTERVALS` configuration is missing required intervals.

### Root Cause

In `config/config.py`, the default `CANDLE_INTERVALS` is:
```python
'candle_intervals': [
    int(x.strip()) 
    for x in os.getenv('CANDLE_INTERVALS', '5').split(',')
]
```

This defaults to **only `[5]`** (5-minute candles).

The real-time aggregation flow is:
```
Ticks → 5-min candles → 15-min candles → 60-min candles
```

**Without 15-minute candles in the `candle_intervals` configuration, 60-minute candles cannot be created.**

### Why It Fails

1. `DataFeedService._aggregate_candles_realtime()` is called when 5-min candles complete
2. It checks for 5-min candles and tries to create 15-min candles
3. **BUT** the `CandleAggregator` only tracks intervals in its `self.active_candles` dictionary
4. If 15 is not in `CANDLE_INTERVALS`, the aggregator never creates 15-min candles in `active_candles`
5. Without 15-min candles being tracked, `_try_create_60min_candles()` never gets called with completed 15-min candles
6. Therefore, no 60-min candles are created

## Solution

### Set Environment Variable

You **must** set `CANDLE_INTERVALS` to include all required intervals:

```bash
# In your .env file or environment:
CANDLE_INTERVALS=5,15,60
```

### How It Works

When `CANDLE_INTERVALS=5,15,60`:

1. **From Ticks**: 5-min, 15-min, and 60-min candles are all created from incoming ticks
2. **Real-Time Aggregation**: 
   - When 5-min candles complete → attempt to form 15-min candles from database
   - When 15-min candles complete → attempt to form 60-min candles from database
3. **Result**: All three tables (`live_candles_5min`, `live_candles_15min`, `live_candles_60min`) get filled in real time

### Configuration Options

#### Minimal (5-minute only)
```bash
CANDLE_INTERVALS=5
```
Result: Only `live_candles_5min` is filled

#### With Hourly (Real-time 60-min)
```bash
CANDLE_INTERVALS=5,15,60
```
Result: `live_candles_5min`, `live_candles_15min`, and `live_candles_60min` all filled

#### With Extra Intervals
```bash
CANDLE_INTERVALS=5,15,30,60
```
Result: 5-min, 15-min, 30-min, and 60-min candles all filled

#### Full Example .env
```bash
# Database
PG_CONN_STR=postgresql://postgres:password@localhost:5432/trading_v2

# Kite Broker
KITE_API_KEY=your_api_key
KITE_ACCESS_TOKEN=your_access_token

# Service Configuration - THIS IS CRITICAL FOR 60-MIN CANDLES
CANDLE_INTERVALS=5,15,60
HEARTBEAT_INTERVAL=30
LOG_LEVEL=INFO

# Optional: MQTT
MQTT_BROKER=broker.hivemq.cloud
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
```

## Verification

After setting the environment variable:

1. **Start the service**:
   ```bash
   python main.py --symbols-from-db
   ```

2. **Watch the logs** for confirmation:
   ```
   [2025-01-02 10:45:30] [INFO] Candle intervals: [5, 15, 60] minutes
   [2025-01-02 10:45:35] [INFO] [REAL-TIME] Created 15-min candle for RELIANCE at 2025-01-02 10:00:00
   [2025-01-02 10:46:00] [INFO] [REAL-TIME] Created 60-min candle for RELIANCE at 2025-01-02 10:00:00
   ```

3. **Check database**:
   ```sql
   -- Check if 60-min candles are being filled
   SELECT COUNT(*), MAX(datetime) FROM live_candles_60min;
   SELECT COUNT(*), MAX(datetime) FROM live_candles_15min;
   SELECT COUNT(*), MAX(datetime) FROM live_candles_5min;
   ```

## Code Flow Explained

### With CANDLE_INTERVALS=5,15,60

**From `core/data_feed_service.py`:**

```python
# 1. Ticks come in and create all three interval candles
service = DataFeedService(
    broker=broker,
    database=db_handler,
    candle_intervals=[5, 15, 60],  # All three are tracked
)

# 2. When 5-min candles complete -> save to live_candles_5min
# 3. When 15-min candles complete -> save to live_candles_15min
# 4. When 60-min candles complete -> save to live_candles_60min

# 5. Real-time aggregation runs AFTER saving
# 6. _try_create_15min_candles() queries live_candles_5min
# 7. _try_create_60min_candles() queries live_candles_15min
# 8. Results are saved back to the databases
```

## Troubleshooting

### 60-min candles still not appearing?

1. **Verify configuration is loaded**:
   ```bash
   python -c "from config.config import Config; print(Config.get_service_config())"
   ```
   Output should show: `'candle_intervals': [5, 15, 60]`

2. **Check if 15-min candles are being created**:
   ```sql
   SELECT COUNT(*) FROM live_candles_15min WHERE datetime > NOW() - INTERVAL '1 hour';
   ```

3. **Check if 60-min candles have the right timestamps**:
   ```sql
   SELECT COUNT(*), MIN(datetime), MAX(datetime) FROM live_candles_60min;
   ```

4. **Monitor logs during market hours** (9:10 AM - 3:45 PM IST) - candles only save during market hours

5. **Ensure data is flowing**:
   ```sql
   SELECT COUNT(*) FROM live_candles_5min WHERE datetime > NOW() - INTERVAL '1 hour';
   ```

## Additional Notes

- **Off-market hours**: Candles are NOT saved outside market hours (by design). See `_is_market_hours()` in `data_feed_service.py`
- **Startup backfill**: On service startup, the system runs `startup_backfill_all_symbols()` to catch any missing candles from past sessions
- **Real-time aggregation**: The system continuously checks for new 5-min and 15-min candles and creates higher timeframes in real time
