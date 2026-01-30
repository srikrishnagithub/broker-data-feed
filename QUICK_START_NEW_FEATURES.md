# Quick Start Guide - New Features

## 🚀 Feature 1: Startup Gap-Fill

### What it does
Automatically fetches historical data when you start the program late during market hours.

### Requirements
- No configuration needed! Works automatically.
- Requires `../Trading-V2/nse_cli.py` to be accessible

### How to use
Just start the program normally during market hours:

```bash
python main.py --symbols-from-db --broker kite
```

If you start after 9:15 AM, you'll see:
```
[INFO] Started during market hours: Started 120.5 minutes after market open
[INFO] Performing gap-fill to fetch historical data from market open...
[INFO] Fetching data from 2026-01-28 09:10:00 to 2026-01-28 11:10:00
[SUCCESS] Successfully fetched 5min data for all symbols
[SUCCESS] Total: 1350 candles migrated
```

---

## 🔄 Feature 2: Dynamic Symbol Management

### What it does
Add new symbols to your data feed without restarting the service!

### Setup (One-time)

1. **Create config file**
   ```bash
   cp symbols_config.json.example symbols_config.json
   ```

2. **Edit `.env` file**
   ```bash
   # Add these lines to your .env
   DYNAMIC_SYMBOLS_ENABLED=true
   SYMBOLS_CONFIG_FILE=symbols_config.json
   SYMBOL_MONITOR_INTERVAL=30
   ```

3. **Start the service**
   ```bash
   python main.py --symbols-from-db --broker kite
   ```

### Adding a New Symbol

1. **Edit symbols_config.json**
   ```json
   {
     "symbols": [
       "RELIANCE",
       "INFY",
       "TCS",
       "WIPRO"  ← Add this line
     ],
     "enabled": true
   }
   ```

2. **Save the file**

3. **Wait ~30 seconds**
   The service will automatically:
   - ✅ Detect the new symbol
   - ✅ Verify it exists in database
   - ✅ Check historical data (from 2024)
   - ✅ Fetch missing historical data if needed
   - ✅ Fill today's gap
   - ✅ Start live tracking

4. **Check logs**
   ```
   [INFO] Detected 1 new symbols: {'WIPRO'}
   [INFO] Adding new symbol: WIPRO
   [SUCCESS] Instrument token verified: WIPRO = 969473
   [SUCCESS] Successfully added WIPRO to data feed
   ```

---

## 📊 Verify It's Working

### Check Live Data
```sql
-- See today's candles for a symbol
SELECT COUNT(*), MIN(datetime), MAX(datetime)
FROM live_candles_5min
WHERE tradingsymbol = 'WIPRO'
AND DATE(datetime) = CURRENT_DATE;
```

### Check Historical Data
```sql
-- Verify historical data exists
SELECT MIN(datetime), MAX(datetime), COUNT(*)
FROM historical_5min
WHERE tradingsymbol = 'WIPRO';
```

---

## ⚠️ Troubleshooting

### Problem: Gap-fill not working

**Solution:**
```bash
# Check nse_cli.py is accessible
ls ../Trading-V2/nse_cli.py

# Test it manually
cd ../Trading-V2
python nse_cli.py --mode data --interval 5 --symbol RELIANCE --start_date 2026-01-28
```

### Problem: New symbols not detected

**Solution:**
```bash
# Check environment variable
echo $DYNAMIC_SYMBOLS_ENABLED

# Verify config file
cat symbols_config.json

# Check the service logs
tail -f logs/broker_data_feed_*.log | grep "new symbols"
```

### Problem: Historical data missing

**Solution:**
```bash
# Fetch historical data manually
cd ../Trading-V2
python nse_cli.py --mode data --interval both --symbol WIPRO --start_date 2024-01-01 --end_date 2026-01-28
```

---

## 📁 Files Overview

### New Files
- `core/startup_gap_fill.py` - Gap-fill logic
- `core/dynamic_symbol_manager.py` - Symbol management
- `symbols_config.json` - Your symbols list (create from .example)
- `NEW_FEATURES.md` - Detailed documentation
- `QUICK_START_NEW_FEATURES.md` - This file

### Modified Files
- `main.py` - Integrated new features
- `config/config.py` - Added config methods
- `core/data_feed_service.py` - Added dynamic subscription support

---

## 💡 Tips

1. **Start Early**: If you start before 9:15 AM, no gap-fill happens (faster startup)

2. **Add Multiple Symbols**: You can add multiple symbols at once to symbols_config.json

3. **Monitor Logs**: Keep an eye on logs to see when symbols are added:
   ```bash
   tail -f logs/broker_data_feed_*.log
   ```

4. **Historical Data**: Ensure you have historical data from 2024 for best results

5. **Backup Config**: Keep a backup of symbols_config.json before editing

---

## 🎯 Common Use Cases

### Use Case 1: Started at Lunch Time
```
Start Time: 1:30 PM
Market Hours: 9:10 AM - 3:45 PM
Action: Gap-fill runs automatically, fetches 9:10 AM - 1:30 PM data
Result: Full day's data available
```

### Use Case 2: Add New Trading Symbol
```
Current Symbols: 50
Action: Add "TATAMOTORS" to symbols_config.json
Wait: ~30-60 seconds
Result: TATAMOTORS now being tracked with full historical + today's data
```

### Use Case 3: Weekend Restart
```
Start Time: Saturday 10:00 AM
Market Hours: Closed
Action: No gap-fill (not market hours)
Dynamic Symbols: Still monitored
Result: Service ready for Monday
```

---

## 📞 Need Help?

1. Read [NEW_FEATURES.md](NEW_FEATURES.md) for detailed documentation
2. Check logs: `logs/broker_data_feed_YYYY-MM-DD.log`
3. Verify database tables and data
4. Test each component individually

---

## ✅ Checklist

Before using new features:

- [ ] Trading-V2 folder is in parent directory
- [ ] nse_cli.py exists at `../Trading-V2/nse_cli.py`
- [ ] Database has historical_5min, historical_15min, historical_60min tables
- [ ] Database has instruments or kotak_instruments table
- [ ] .env has DYNAMIC_SYMBOLS_ENABLED=true (for Feature 2)
- [ ] symbols_config.json created (for Feature 2)
- [ ] Service has internet access (for fetching historical data)

---

**Enjoy seamless data feed management! 🎉**
