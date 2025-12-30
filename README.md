# Broker Data Feed Service

Independent live OHLC data feeding service for Trading-V2 with multi-broker support.

## Features

- **Multi-broker Support**: Extensible architecture to support multiple brokers
  - **Kite (Zerodha)**: Full support with automatic token refresh
  - **KOTAK NEO**: Full support with auto re-authentication and symbol limits
- **Real-time Tick Processing**: Converts live tick data to OHLC candles
- **Multiple Timeframes**: Supports multiple candle intervals simultaneously (1min, 5min, 15min, etc.)
- **Database Integration**: Automatic storage to existing Trading-V2 database tables
- **MQTT Heartbeats**: Optional MQTT integration for monitoring and alerting
- **Error Recovery**: Automatic reconnection on broker connection failures
- **Logging**: Comprehensive logging with configurable levels

## Architecture

```
broker_data_feed/
├── core/
│   ├── base_broker.py         # Abstract broker interface
│   ├── candle_aggregator.py   # Tick-to-OHLC aggregation
│   ├── database_handler.py    # Database operations
│   └── data_feed_service.py   # Main service coordinator
├── brokers/
│   ├── kite_broker.py         # Kite/Zerodha implementation
│   ├── kotak_neo_broker.py    # KOTAK NEO implementation
│   └── mqtt_publisher.py      # MQTT integration
├── config/
│   └── config.py              # Configuration management
├── tests/
│   └── test_broker.py         # Testing utilities
└── main.py                    # Entry point
```

## Installation

1. Ensure dependencies are installed:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`:
```bash
# Required
PG_CONN_STR=postgresql://user:pass@host:port/trading_v2
KITE_API_KEY=your_api_key
KITE_ACCESS_TOKEN=your_access_token

# Optional
CANDLE_INTERVALS=5,15  # Comma-separated intervals in minutes
HEARTBEAT_INTERVAL=30  # Heartbeat interval in seconds
MQTT_BROKER=broker.hivemq.com
MQTT_USERNAME=your_username
MQTT_PASSWORD=your_password
```

## Usage

### Start with Kite Broker (Default)

```bash
# Start with specific symbols
python broker_data_feed/main.py --symbols RELIANCE INFY TCS HDFCBANK

# Start with symbols from file
python broker_data_feed/main.py --symbols-file instruments.txt

# Start with symbols from database
python broker_data_feed/main.py --symbols-from-db

# Test broker connection
python broker_data_feed/main.py --test-broker
```

### Start with KOTAK NEO Broker

```bash
# Start with specific symbols
python broker_data_feed/main.py --broker kotak --symbols RELIANCE INFY TCS

# Start with symbols from file (max 100 symbols)
python broker_data_feed/main.py --broker kotak --symbols-file instruments.txt

# Start with symbols from database
python broker_data_feed/main.py --broker kotak --symbols-from-db

# Test broker connection
python broker_data_feed/main.py --broker kotak --test-broker
```

**Note**: KOTAK NEO has a limit of 100 symbols per connection. See [KOTAK_NEO_INTEGRATION.md](KOTAK_NEO_INTEGRATION.md) for details.

### Test Database Connection

```bash
python broker_data_feed/main.py --test-database
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PG_CONN_STR` | PostgreSQL connection string | Required |
| `KITE_API_KEY` | Kite API key | Required for Kite |
| `KITE_ACCESS_TOKEN` | Kite access token | Required for Kite |
| `KOTAK_CONSUMER_KEY` | KOTAK consumer key | Required for KOTAK NEO |
| `KOTAK_CONSUMER_SECRET` | KOTAK consumer secret | Required for KOTAK NEO |
| `KOTAK_MOBILE_NUMBER` | KOTAK mobile number | Required for KOTAK NEO |
| `KOTAK_PASSWORD` | KOTAK password | Required for KOTAK NEO |
| `KOTAK_MPIN` | KOTAK MPIN | Required for KOTAK NEO |
| `CANDLE_INTERVALS` | Candle intervals (minutes) | `5` |
| `HEARTBEAT_INTERVAL` | Heartbeat interval (seconds) | `30` |
| `CANDLE_TABLE_NAME` | Target database table | `merged_candles_5min` |
| `MQTT_BROKER` | MQTT broker hostname | Optional |
| `MQTT_PORT` | MQTT broker port | `8883` |
| `MQTT_USERNAME` | MQTT username | Optional |
| `MQTT_PASSWORD` | MQTT password | Optional |
| `MQTT_USE_TLS` | Use TLS for MQTT | `true` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Adding New Brokers

To add support for a new broker:

1. Create a new broker class inheriting from `BaseBroker`:
```python
from broker_data_feed.core.base_broker import BaseBroker, TickData

class NewBroker(BaseBroker):
    def connect(self) -> bool:
        # Implementation
        pass
    
    def disconnect(self):
        # Implementation
        pass
    
    # Implement other abstract methods...
```

2. Add broker configuration to `config/config.py`
3. Update `main.py` to support the new broker
4. Create integration documentation (see `KOTAK_NEO_INTEGRATION.md` as example)

## Broker-Specific Documentation

- [KOTAK NEO Integration Guide](KOTAK_NEO_INTEGRATION.md) - Detailed KOTAK NEO setup and usage

## Database Schema

The service saves candles to the following table structure:

```sql
CREATE TABLE merged_candles_5min (
    datetime TIMESTAMP,
    tradingsymbol VARCHAR,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume INTEGER
);
```

## Monitoring

### Heartbeat
The service publishes heartbeats every 30 seconds (configurable) containing:
- Tick count
- Candle count
- Last tick time
- Active candle statistics

### MQTT Topics
- `heartbeat/data_feed` - Service heartbeat messages

## Logging

Logs include:
- Tick processing statistics
- Candle completion notifications
- Connection status updates
- Error messages with details

Format: `[YYYY-MM-DD HH:MM:SS] [LEVEL] message`

## Error Handling

- **Connection Failures**: Automatic reconnection attempts
- **Database Errors**: Logged with retry on next candle
- **Tick Processing Errors**: Logged but service continues
- **Shutdown Handling**: Graceful cleanup with candle finalization

## Testing

Run broker connection test:
```bash
python broker_data_feed/tests/test_broker.py
```

## Troubleshooting

### No ticks received
- Check KITE_ACCESS_TOKEN is valid
- Verify market hours (9:15 AM - 3:30 PM IST)
- Ensure instruments are actively trading

### Database connection failed
- Verify PG_CONN_STR is correct
- Check database server is accessible
- Ensure table `merged_candles_5min` exists

### MQTT connection timeout
- Check MQTT broker credentials
- Verify network connectivity
- Service continues without MQTT if connection fails

## License

Part of Trading-V2 project.
