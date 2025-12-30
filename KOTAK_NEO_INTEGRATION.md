# KOTAK NEO Broker Integration Guide

## Overview

This guide provides detailed information about integrating the KOTAK NEO broker with the broker data feed service.

## Features

The KOTAK NEO broker implementation includes:

- **Automatic Authentication**: Handles login and MPIN verification
- **Re-authentication on Expiry**: Automatically detects token expiry and re-authenticates
- **Symbol Count Validation**: Enforces KOTAK NEO's limit of 100 symbols per connection
- **WebSocket Connection**: Real-time tick data via WebSocket
- **Error Recovery**: Automatic reconnection with re-authentication
- **Standardized Interface**: Implements the BaseBroker interface for consistency

## Configuration

### Required Environment Variables

Add these to your `.env` file:

```bash
# KOTAK NEO Credentials
KOTAK_CONSUMER_KEY=your_consumer_key
KOTAK_CONSUMER_SECRET=your_consumer_secret
KOTAK_MOBILE_NUMBER=your_mobile_number
KOTAK_PASSWORD=your_password
KOTAK_MPIN=your_mpin
```

### Symbol Limit

KOTAK NEO enforces a maximum of **100 symbols per WebSocket connection**. The implementation will:
- Check symbol count before subscribing
- Reject subscriptions that exceed the limit
- Log an error if limit is exceeded

## Usage

### Start with KOTAK NEO Broker

Use the `--broker kotak` or `--broker kotak_neo` flag:

```bash
# Start with specific symbols
python main.py --broker kotak --symbols RELIANCE INFY TCS

# Start with symbols from file
python main.py --broker kotak --symbols-file instruments.txt

# Start with database symbols
python main.py --broker kotak --symbols-from-db

# Test broker connection
python main.py --broker kotak --test-broker
```

### Symbol File Format

Create a file with one symbol per line:

```
RELIANCE
INFY
TCS
HDFCBANK
WIPRO
```

**Important**: Ensure the file contains no more than 100 symbols.

## Authentication Flow

The KOTAK NEO broker uses a two-step authentication process:

1. **Login**: Authenticate with mobile number and password
2. **MPIN Verification**: Verify with MPIN to obtain access token

### Authentication Token Management

- Tokens are cached for 24 hours (configurable)
- Automatic re-authentication occurs at 90% of token TTL
- Re-authentication is triggered on connection errors
- Failed authentication requires manual intervention (restart with new credentials)

## WebSocket Connection

### Connection URL

```
wss://mlhsi.kotaksecurities.com?sId={sid}&serverId={server_id}
```

Parameters:
- `sid`: Session ID from authentication
- `serverId`: Server ID from authentication (default: "1")

### Message Format

**Subscribe:**
```json
{
  "a": "subscribe",
  "v": [{"k": "instrument_token"}],
  "m": "mf"
}
```

**Unsubscribe:**
```json
{
  "a": "unsubscribe",
  "v": [{"k": "instrument_token"}]
}
```

**Tick Data:**
```json
{
  "t": "tk",
  "d": [
    {
      "tk": "instrument_token",
      "lp": "last_price",
      "v": "volume",
      "oi": "open_interest"
    }
  ]
}
```

## Error Handling

### Authentication Errors

If authentication fails:
1. Check credentials in `.env` file
2. Verify mobile number format
3. Ensure MPIN is correct
4. Check if account has API access enabled

### Symbol Count Exceeded

If you see: "Symbol count exceeds maximum (100)":
1. Reduce the number of symbols in your input
2. Split symbols across multiple instances (not recommended)
3. Prioritize most important symbols

### Connection Errors

The broker automatically handles:
- Network disconnections
- Token expiry
- WebSocket errors

Manual restart required for:
- Invalid credentials
- Account access issues
- Persistent authentication failures

## API Endpoints

### Authentication
```
POST https://gw-napi.kotaksecurities.com/login/1.0/login/v2/validate
```

### Instrument List
```
GET https://gw-napi.kotaksecurities.com/login/scripmaster/v1/instrumentDump
```

## Comparison with Kite

| Feature | Kite | KOTAK NEO |
|---------|------|-----------|
| Max Symbols | 3000 | 100 |
| Authentication | API Key + Token | Multi-step (Login + MPIN) |
| Token Type | Access Token | JWT |
| Token Expiry | Daily | 24 hours |
| Re-auth | Manual | Automatic |
| WebSocket URL | Fixed | Dynamic (with sid) |

## Troubleshooting

### Issue: "Authentication failed"

**Cause**: Invalid credentials or network issue

**Solution**:
1. Verify all credentials in `.env`
2. Check network connectivity
3. Ensure account has API access
4. Try logging in via browser first

### Issue: "Symbol count exceeds maximum"

**Cause**: More than 100 symbols requested

**Solution**:
1. Reduce symbol count to ≤100
2. Use `--symbols-from-db` with filtered query
3. Create multiple service instances (advanced)

### Issue: "WebSocket connection closed"

**Cause**: Token expiry or network issue

**Solution**:
- Service will automatically attempt reconnection
- Check logs for re-authentication status
- If persistent, restart service

### Issue: "Instrument not found"

**Cause**: Symbol not available in KOTAK NEO

**Solution**:
1. Verify symbol name is correct
2. Check if instrument is supported by KOTAK NEO
3. Use correct exchange (NSE/BSE)

## Best Practices

1. **Symbol Management**
   - Keep symbol count well below 100
   - Use database filtering for optimal symbol selection
   - Monitor subscription status regularly

2. **Credential Security**
   - Never commit `.env` file to version control
   - Use strong passwords and MPIN
   - Rotate credentials periodically

3. **Monitoring**
   - Enable MQTT heartbeats
   - Monitor logs for authentication warnings
   - Set up alerts for connection failures

4. **Database Integration**
   - Use existing `instruments` table for token mapping
   - Store KOTAK-specific instrument data separately if needed
   - Keep symbol-to-token mapping updated

## Migration from Kite

If migrating from Kite to KOTAK NEO:

1. **Update Configuration**
   ```bash
   # Add KOTAK credentials to .env
   KOTAK_CONSUMER_KEY=...
   KOTAK_CONSUMER_SECRET=...
   KOTAK_MOBILE_NUMBER=...
   KOTAK_PASSWORD=...
   KOTAK_MPIN=...
   ```

2. **Reduce Symbol Count**
   ```bash
   # If using >100 symbols with Kite, reduce for KOTAK
   # Use database filtering or prioritization
   ```

3. **Update Launch Command**
   ```bash
   # Change from:
   python main.py --symbols-from-db
   
   # To:
   python main.py --broker kotak --symbols-from-db
   ```

4. **Verify Connection**
   ```bash
   python main.py --broker kotak --test-broker
   ```

## Support

For KOTAK NEO API documentation:
- [KOTAK NEO API Docs](https://github.com/Kotak-Neo/kotak-neo-api)
- [WebSocket Documentation](https://github.com/Kotak-Neo/kotak-neo-api/tree/main/websocket)

For service issues:
- Check logs in `logs/` directory
- Use `--test-broker` for diagnostics
- Review error messages in console output
