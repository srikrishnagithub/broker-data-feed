# Broker Data Feed Service - Quick Start Guide

## Prerequisites

1. **Database**: PostgreSQL with Trading-V2 schema
2. **Kite Account**: Valid API key and access token
3. **Python**: Python 3.8+ with required packages

## Step-by-Step Setup

### 1. Configure Environment

Edit `.env` file with your credentials:

```bash
# Required settings
PG_CONN_STR=postgresql://postgres:your_password@localhost:5432/trading_v2
KITE_API_KEY=your_api_key_here
KITE_ACCESS_TOKEN=your_access_token_here

# Optional settings
CANDLE_INTERVALS=5,15  # Support both 5min and 15min candles
HEARTBEAT_INTERVAL=30  # Heartbeat every 30 seconds
```

### 2. Verify Setup

Run the test script to verify everything is configured correctly:

```bash
python broker_data_feed\tests\test_broker.py
```

Expected output:
```
✅ Configuration: PASS
✅ Database: PASS
✅ Broker: PASS
✅ Instruments: PASS
```

### 3. Start the Service

#### Option A: Using specific symbols
```bash
python broker_data_feed\main.py --symbols RELIANCE INFY TCS
```

#### Option B: Using symbols file
```bash
python broker_data_feed\main.py --symbols-file broker_data_feed\instruments_sample.txt
```

#### Option C: Using database symbols (last 30 days)
```bash
python broker_data_feed\main.py --symbols-from-db
```

#### Option D: Using batch file (Windows)
```bash
launch_data_feed.bat --symbols RELIANCE INFY TCS
```

### 4. Monitor the Service

Watch the console output for:
- **Connection status**: "Kite WebSocket connected successfully"
- **Tick processing**: "Processed 100 ticks"
- **Candle completion**: "Candle 5min RELIANCE: O=2450.00 H=2455.00 L=2448.00 C=2453.00"
- **Heartbeats**: "[HEARTBEAT] Ticks: 1234, Candles: 56"

### 5. Verify Data in Database

Check that candles are being saved:

```sql
SELECT datetime, tradingsymbol, open, high, low, close, volume
FROM merged_candles_5min
WHERE tradingsymbol = 'RELIANCE'
ORDER BY datetime DESC
LIMIT 10;
```

## Common Operations

### Check Service Status
The service logs heartbeats every 30 seconds showing:
- Total ticks processed
- Total candles saved
- Time since last tick

### Stop the Service
Press `Ctrl+C` once for graceful shutdown. The service will:
1. Close any incomplete candles
2. Save remaining candles to database
3. Disconnect from broker
4. Display final statistics

### Run During Market Hours
The service should be started during market hours (9:15 AM - 3:30 PM IST) for live data.

Outside market hours, it will still connect but receive no ticks (this is normal).

## Troubleshooting

### No ticks received
**Cause**: Market is closed or connection issue
**Solution**: 
- Verify market is open (9:15 AM - 3:30 PM IST)
- Check KITE_ACCESS_TOKEN is valid
- Run: `python broker_data_feed\main.py --test-broker`

### Database connection failed
**Cause**: Invalid PG_CONN_STR or database not accessible
**Solution**:
- Verify PostgreSQL is running
- Check connection string in `.env`
- Run: `python broker_data_feed\main.py --test-database`

### Import errors
**Cause**: Missing dependencies
**Solution**: Install required packages
```bash
pip install kiteconnect sqlalchemy pandas python-dotenv paho-mqtt
```

### Symbol not found
**Cause**: Invalid symbol name
**Solution**: Use correct NSE symbol names (e.g., `RELIANCE` not `RELIANCE.NS`)

## Advanced Configuration

### Multiple Candle Intervals
To generate multiple timeframes simultaneously:
```bash
# In .env file
CANDLE_INTERVALS=1,5,15,30  # 1min, 5min, 15min, 30min
```

Note: Only 5min candles are saved to database. Other intervals are aggregated in memory.

### MQTT Integration
To enable MQTT heartbeats:
```bash
# In .env file
MQTT_BROKER=your_broker.hivemq.cloud
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
MQTT_PORT=8883
```

### Custom Table Name
To save candles to a different table:
```bash
# In .env file
CANDLE_TABLE_NAME=my_custom_candles_table
```

## Production Deployment

### As Windows Service
Use NSSM (Non-Sucking Service Manager) to run as service:
```bash
nssm install BrokerDataFeed "C:\Python39\python.exe" "C:\path\to\broker_data_feed\main.py --symbols-from-db"
nssm start BrokerDataFeed
```

### Using Task Scheduler
Create a scheduled task to start at 9:10 AM daily:
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 9:10 AM
4. Action: Start program `launch_data_feed.bat`
5. Set working directory to project root

### Logging
All logs are printed to console. To save logs:
```bash
python broker_data_feed\main.py --symbols-from-db > logs\data_feed.log 2>&1
```

## Next Steps

1. **Monitor Performance**: Watch tick rate and candle generation
2. **Verify Data Quality**: Check candle data in database
3. **Setup Alerts**: Configure MQTT for monitoring
4. **Automate Startup**: Use Task Scheduler or service manager

## Support

For issues or questions:
1. Check the main README: `broker_data_feed/README.md`
2. Run diagnostic tests: `test_data_feed.bat`
3. Review error messages in console output
