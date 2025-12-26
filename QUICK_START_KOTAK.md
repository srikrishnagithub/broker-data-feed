# KOTAK NEO Quick Start Guide

## 1-Minute Setup

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Credentials
Create/edit `.env` file:
```bash
# KOTAK NEO Credentials (REQUIRED)
KOTAK_CONSUMER_KEY=your_consumer_key
KOTAK_CONSUMER_SECRET=your_consumer_secret
KOTAK_MOBILE_NUMBER=your_mobile_number
KOTAK_PASSWORD=your_password
KOTAK_MPIN=your_mpin

# Database (REQUIRED)
PG_CONN_STR=postgresql://user:pass@host:port/database
```

### Step 3: Test Connection
```bash
python main.py --broker kotak --test-broker
```

### Step 4: Start Service
```bash
# With specific symbols (max 100)
python main.py --broker kotak --symbols RELIANCE INFY TCS

# With symbols from file
python main.py --broker kotak --symbols-file instruments.txt

# With database symbols
python main.py --broker kotak --symbols-from-db
```

---

## Common Commands

| Task | Command |
|------|---------|
| Test KOTAK connection | `python main.py --broker kotak --test-broker` |
| Test Kite connection | `python main.py --broker kite --test-broker` |
| Test database | `python main.py --test-database` |
| Start with KOTAK | `python main.py --broker kotak --symbols-from-db` |
| Start with Kite | `python main.py --broker kite --symbols-from-db` |
| Syntax validation | `python test_syntax.py` |

---

## Key Differences from Kite

| Feature | Kite | KOTAK NEO |
|---------|------|-----------|
| **Max Symbols** | 3,000 | **100** ⚠️ |
| **Authentication** | Simple | Multi-step (Login + MPIN) |
| **Token Expiry** | Manual refresh | **Auto re-auth** ✅ |
| **Broker Flag** | `--broker kite` | `--broker kotak` |

---

## ⚠️ Important Limits

- **Maximum 100 symbols** per connection
- Tokens expire after 24 hours (auto re-auth enabled)
- MPIN must be 6 digits
- Mobile number format: no spaces or dashes

---

## Troubleshooting

### Authentication Failed
```bash
# Check credentials
cat .env | grep KOTAK

# Verify mobile number (no spaces)
# Verify MPIN (6 digits)
# Ensure API access enabled
```

### Symbol Limit Exceeded
```bash
# Count symbols in file
wc -l instruments.txt

# Must be ≤100
# Reduce or filter symbols
```

### Connection Issues
```bash
# Check logs
tail -f logs/broker_data_feed.log

# Service auto-reconnects
# Check for re-authentication messages
```

---

## File Structure

```
.
├── brokers/
│   ├── kite_broker.py         # Kite implementation
│   └── kotak_neo_broker.py    # KOTAK NEO implementation ✨
├── config/
│   └── config.py              # Config (updated for KOTAK)
├── main.py                     # Entry point (updated)
├── .env                        # Your credentials (create this)
├── .env.example               # Template ✨
└── KOTAK_NEO_INTEGRATION.md   # Full guide ✨
```

---

## Example Workflows

### Migrate from Kite to KOTAK

```bash
# 1. Add KOTAK credentials to .env
echo "KOTAK_CONSUMER_KEY=..." >> .env
echo "KOTAK_CONSUMER_SECRET=..." >> .env
# ... (add other credentials)

# 2. Test connection
python main.py --broker kotak --test-broker

# 3. Filter database symbols to ≤100
# (update your database query)

# 4. Start service
python main.py --broker kotak --symbols-from-db
```

### Run Both Brokers (Separate Instances)

```bash
# Terminal 1: Kite with 200 symbols
python main.py --broker kite --symbols-from-db

# Terminal 2: KOTAK with top 100 symbols
python main.py --broker kotak --symbols-file top100.txt
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| `KOTAK_NEO_INTEGRATION.md` | Complete integration guide |
| `KOTAK_IMPLEMENTATION_SUMMARY.md` | Implementation details |
| `IMPLEMENTATION_COMPLETE.md` | Final summary |
| `README.md` | Main documentation |
| `.env.example` | Config template |

---

## Support

**Issues?** Check:
1. `.env` credentials are correct
2. Symbol count ≤100
3. Database connection working
4. Logs: `logs/broker_data_feed.log`

**Documentation**:
- Full guide: `KOTAK_NEO_INTEGRATION.md`
- KOTAK API: https://github.com/Kotak-Neo/kotak-neo-api

---

## Status

✅ Implementation COMPLETE  
✅ Syntax validated  
✅ Documentation ready  
⏳ Pending: Real credential testing  

**Next**: Configure `.env` and run `python main.py --broker kotak --test-broker`
