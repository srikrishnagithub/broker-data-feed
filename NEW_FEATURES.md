# NEW FEATURES - Broker Data Feed

## Overview

Two major features have been added to the broker data feed service:

1. **Startup Gap-Fill**: Automatically fetch historical data when starting late during market hours
2. **Dynamic Symbol Management**: Add new symbols to the data feed without restarting the service

---

## Feature 1: Startup Gap-Fill

### Purpose

When the program is started during or after market hours, it automatically fetches historical data from market open (9:10 AM IST) until the current time to ensure no data gaps.

### How It Works

1. **Detection**: On startup, the system checks if it's currently within market hours (Mon-Fri, 9:10 AM - 3:45 PM IST)
2. **Gap Check**: If started more than 5 minutes after market open, gap-fill is triggered
3. **Historical Fetch**: Uses `nse_cli.py` from Trading-V2 to fetch historical data for all configured intervals (5min, 15min, 60min)
4. **Migration**: Automatically migrates fetched data to live tables using existing migration logic
5. **Iteration**: Repeats the process if still significantly behind (> 10 minutes)

### Example Scenarios

#### Scenario 1: Started at 11:52 AM
```
Market Open: 9:10 AM
Current Time: 11:52 AM
Gap: 2 hours 42 minutes

Actions:
1. Fetch historical data from 9:10 AM to 11:50 AM (rounded to 5-min boundary)
2. Migrate to live_candles_5min, live_candles_15min, live_candles_60min
3. Check if still behind (yes, ~2 minutes)
4. At 11:55 AM, fetch data from 11:50 AM to 11:55 AM
5. Migrate again
6. Now caught up, start live tracking
```

#### Scenario 2: Started at 9:12 AM
```
Market Open: 9:10 AM
Current Time: 9:12 AM
Gap: 2 minutes

Actions:
- Gap < 5 minutes, no gap-fill needed
- Start live tracking immediately
```

### Usage

Gap-fill is **automatic** and requires no configuration. It's triggered automatically when:
- Program starts during market hours (Mon-Fri, 9:10 AM - 3:45 PM IST)
- Current time is > 5 minutes after market open

### Logs

Look for these log entries:
```
[INFO] STARTUP INITIALIZATION
[INFO] Started during market hours: Started X minutes after market open
[INFO] Performing gap-fill to fetch historical data from market open...
[INFO] Fetching data from 2026-01-28 09:10:00 to 2026-01-28 11:50:00
[SUCCESS] Successfully fetched 5min data for all symbols
[INFO] Migrating 5min candles to live tables...
[SUCCESS] Migrated 450 records for 5min
[SUCCESS] Total: 1350 candles migrated
```

### Files Added/Modified

- **NEW**: `core/startup_gap_fill.py` - Core gap-fill logic
- **MODIFIED**: `main.py` - Integrated gap-fill into startup sequence

---

## Feature 2: Dynamic Symbol Management

### Purpose

Add new symbols to the live data feed without restarting the service. Includes automatic historical data verification and backfill.

### How It Works

1. **Config File Monitoring**: Monitors `symbols_config.json` (or custom path) every 30 seconds
2. **Symbol Detection**: Detects when new symbols are added to the config file
3. **Verification**: 
   - Checks if instrument token exists in database
   - Verifies historical data availability (from 2024 onwards)
4. **Historical Fetch**: If historical data missing, fetches it using `nse_cli.py`
5. **Gap-Fill**: Performs today's gap-fill (if market is open)
6. **Live Subscription**: Subscribes to the symbol and starts tracking ticks

### Configuration File Format

Create `config/symbols.yaml`:

```yaml
symbols:
  - RELIANCE
  - INFY
  - TCS
  - HDFCBANK

enabled: true
last_updated: "2026-01-28T14:30:00"
description: "Symbol configuration for broker data feed"
```

Alternatively, use JSON format (`symbols.json`):
```json
{
  "symbols": [
    "RELIANCE",
    "INFY",
    "TCS",
    "HDFCBANK"
  ],
  "enabled": true,
  "last_updated": "2026-01-28T14:30:00"
}
```

Or simple text format (one symbol per line):
```
RELIANCE
INFY
TCS
HDFCBANK
```

### Environment Variables

Add to your `.env` file:

```bash
# Enable dynamic symbol management
DYNAMIC_SYMBOLS_ENABLED=true

# Path to symbols config file (optional, defaults to config/symbols.yaml)
SYMBOLS_CONFIG_FILE=config/symbols.yaml

# How often to check for new symbols in seconds (optional, default: 30)
SYMBOL_MONITOR_INTERVAL=30
```

### Adding a New Symbol

1. Edit `config/symbols.yaml` and add the new symbol:
```yaml
symbols:
  - RELIANCE
  - INFY
  - TCS
  - HDFCBANK
  - WIPRO  # ← NEW

enabled: true
```

2. Save the file

3. Within 30 seconds, the service will:
   - Detect the new symbol
   - Verify instrument token in database
   - Check historical data availability
   - Fetch historical data if missing (from 2024)
   - Perform gap-fill for today's data
   - Start live tracking

### Logs

Look for these log entries:
```
[INFO] Enabling dynamic symbol management...
[INFO]   Config file: config/symbols.yaml
[INFO]   Monitor interval: 30 seconds
[SUCCESS] Dynamic symbol management enabled
...
[INFO] Detected 1 new symbols: {'WIPRO'}
[INFO] Adding new symbol: WIPRO
[SUCCESS] Instrument token verified: WIPRO = 969473
[INFO] Historical data exists for WIPRO:
[INFO]   Earliest: 2024-01-01 09:15:00
[INFO]   Latest: 2026-01-27 15:29:00
[INFO]   Records: 45678
[INFO] Performing gap-fill for WIPRO (today's data)
[INFO] Notifying data feed to start tracking WIPRO
[SUCCESS] Successfully added WIPRO to data feed
[INFO] Subscribing to 1 new instruments...
[SUCCESS] Successfully added 1 new symbols
```

### Files Added/Modified

- **NEW**: `core/dynamic_symbol_manager.py` - Core dynamic symbol management
- **MODIFIED**: `config/config.py` - Added config methods for symbols file
- **MODIFIED**: `core/data_feed_service.py` - Added methods for dynamic subscription
- **MODIFIED**: `main.py` - Integrated dynamic symbol manager

---

## Historical Data Requirements

Both features rely on historical data from **2024 onwards**. The system will:

1. Check if historical data exists in tables: `historical_5min`, `historical_15min`, `historical_60min`
2. If data is missing or incomplete, fetch it using `nse_cli.py` from Trading-V2
3. Migrate to live tables as needed

### Manual Historical Data Fetch

If you need to fetch historical data manually:

```bash
# From Trading-V2 directory
python nse_cli.py --mode data --interval both --symbol WIPRO --start_date 2024-01-01 --end_date 2026-01-28
```

---

## Dependencies

### External Dependencies

- **nse_cli.py** from Trading-V2 must be accessible at `../Trading-V2/nse_cli.py` (relative to broker_data_feed)
- All required Python packages from Trading-V2's requirements.txt

### Database Requirements

- Tables: `historical_5min`, `historical_15min`, `historical_60min`
- Tables: `live_candles_5min`, `live_candles_15min`, `live_candles_60min`
- Tables: `instruments` (for Kite) or `kotak_instruments` (for Kotak)
- Migration script: `scripts/migrate_historical_to_live.py`

---

## Testing

### Test Gap-Fill

1. Start the service during market hours but after 9:15 AM:
```bash
python main.py --symbols-from-db --broker kite
```

2. Check logs for gap-fill activity
3. Verify data in live tables:
```sql
SELECT COUNT(*), MIN(datetime), MAX(datetime) 
FROM live_candles_5min 
WHERE DATE(datetime) = CURRENT_DATE;
```

### Test Dynamic Symbol Addition

1. Start the service normally:
```bash
python main.py --symbols-from-db --broker kite
```

2. In another terminal, edit `symbols_config.json` and add a new symbol

3. Watch the logs for detection and addition

4. Verify subscription:
```sql
SELECT * FROM live_candles_5min 
WHERE tradingsymbol = 'WIPRO' 
AND DATE(datetime) = CURRENT_DATE
ORDER BY datetime DESC;
```

---

## Troubleshooting

### Gap-Fill Not Working

**Problem**: Gap-fill not triggered on startup

**Checks**:
1. Verify it's market hours: Mon-Fri, 9:10 AM - 3:45 PM IST
2. Check if started > 5 minutes after market open
3. Look for error logs about nse_cli.py

**Solution**:
```bash
# Verify nse_cli.py path
ls ../Trading-V2/nse_cli.py

# Test nse_cli.py manually
cd ../Trading-V2
python nse_cli.py --mode data --interval 5 --symbol RELIANCE --start_date 2026-01-28
```

### Dynamic Symbols Not Detected

**Problem**: New symbols not being added

**Checks**:
1. Verify `DYNAMIC_SYMBOLS_ENABLED=true` in .env
2. Check config/symbols.yaml path and format
3. Look for file modification detection logs

**Solution**:
```bash
# Check config
echo $DYNAMIC_SYMBOLS_ENABLED

# Test file path
cat config/symbols.yaml

# Check logs for monitor activity
grep "Detected.*new symbols" logs/broker_data_feed_*.log
```

### Historical Data Not Found

**Problem**: Symbol added but historical data missing

**Checks**:
1. Verify symbol exists in instruments table
2. Check historical_* tables for data
3. Look for nse_cli.py errors in logs

**Solution**:
```bash
# Fetch historical data manually
cd ../Trading-V2
python nse_cli.py --mode data --interval both --symbol WIPRO --start_date 2024-01-01
```

---

## Performance Considerations

### Gap-Fill

- **Network**: Gap-fill fetches data from NSE, can take 1-5 minutes depending on data volume
- **Database**: Migration uses bulk insert, minimal impact
- **Startup Time**: Adds 2-10 minutes to startup time if gap-fill is needed

### Dynamic Symbol Management

- **Monitoring**: Very lightweight, checks file every 30 seconds
- **Addition**: Adding 1 symbol takes 30-60 seconds (historical verification + gap-fill)
- **Limit**: No hard limit, but recommend adding < 10 symbols at once

---

## Future Enhancements

Possible improvements:

1. **Web UI**: Add symbols via web interface instead of config file
2. **REST API**: HTTP endpoint to add symbols programmatically
3. **Symbol Removal**: Support removing symbols dynamically
4. **Batch Gap-Fill**: Optimize for multiple symbols added together
5. **Historical Cache**: Cache frequently requested historical data

---

## Support

For issues or questions:

1. Check logs: `logs/broker_data_feed_YYYY-MM-DD.log`
2. Review this documentation
3. Test components individually (gap-fill, nse_cli.py, migration script)
4. Verify database tables and data availability

---

## Summary

Both features work seamlessly to ensure:
- ✅ No data gaps when starting late
- ✅ Easy symbol addition without restarts
- ✅ Automatic historical data management
- ✅ Minimal configuration required
- ✅ Comprehensive logging for troubleshooting
