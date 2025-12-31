# KOTAK NEO - Getting Instrument Master

Since the instrument master API endpoint is not available, here are **3 alternatives**:

---

## Option 1: Manual CSV Download (Recommended) ✅

### Steps:

1. **Login to KOTAK NEO**
   - Web: https://neo.kotaksecurities.com/
   - Or mobile app

2. **Find Instrument Master**
   - Go to **"Trade API"** section
   - Look for **"Scrip Master"** or **"Instrument Master"** download
   - Download CSV file

3. **Import into Database**
   ```bash
   python scripts/import_kotak_instruments_csv.py /path/to/downloaded/instruments.csv
   ```

4. **Done!** The service will now use database lookups.

---

## Option 2: Use Zerodha Kite Instruments (Alternative)

If KOTAK doesn't provide instrument master, you can use Kite's (they're similar for NSE):

```bash
# Download Kite instruments
curl -o instruments.csv https://api.kite.trade/instruments

# Import with minor modifications
python scripts/import_kotak_instruments_csv.py instruments.csv
```

**Note**: Symbol formats might differ slightly. Test with a few symbols first.

---

## Option 3: Hardcoded Common Symbols (Quick Fix)

For immediate testing, I can add a hardcoded mapping for common symbols:

```python
# In kotak_neo_broker.py
COMMON_SYMBOLS = {
    'RELIANCE': 'RELIANCE-EQ',
    'INFY': 'INFY-EQ',
    'TCS': 'TCS-EQ',
    'HDFCBANK': 'HDFCBANK-EQ',
    'WIPRO': 'WIPRO-EQ',
    'SBIN': 'SBIN-EQ',
    'ITC': 'ITC-EQ',
    # ... add more as needed
}
```

---

## Option 4: Contact KOTAK Support

Ask KOTAK support:
- **Question**: "What is the API endpoint for downloading instrument/scrip master?"
- **Or**: "How can I get the complete list of trading symbols with pSymbol format?"

They might provide:
- API endpoint we haven't tried
- Direct download link
- FTP access
- Or tell you to use the web dashboard

---

## Which Option Should You Choose?

| Option | Best For | Setup Time |
|--------|----------|------------|
| **Option 1** (CSV Download) | Production use | 5 minutes |
| **Option 2** (Kite data) | Testing/backup | 2 minutes |
| **Option 3** (Hardcoded) | Quick testing | 1 minute |
| **Option 4** (Support) | Long-term solution | 1-2 days |

---

## Immediate Next Steps

**For testing right now**, let me create Option 3 (hardcoded symbols) so you can continue testing while we figure out the proper instrument master.

Would you like me to:
1. Add hardcoded mapping for your symbols (RELIANCE, INFY, TCS)?
2. Or wait for you to download the CSV from KOTAK dashboard?
3. Or try using Kite's instrument data as a starting point?

Let me know and I'll implement it! 🚀

---

## Current Status

✅ Authentication working  
✅ REST API polling working  
✅ Database table created  
⏳ Need instrument master data (one of 4 options above)  
❌ Symbol format causing "Invalid neosymbol" error

**Blocker**: Need correct pSymbol format for each symbol.
