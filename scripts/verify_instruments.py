import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database_handler import DatabaseHandler
from sqlalchemy import text

db = DatabaseHandler()
conn = db.engine.connect()

# Count total
result = conn.execute(text("SELECT COUNT(*) FROM kotak_instruments"))
print(f"Total instruments: {result.scalar()}")

# Find our test symbols
result = conn.execute(text("""
    SELECT psymbol, trading_symbol, exchange_segment, token
    FROM kotak_instruments 
    WHERE trading_symbol LIKE '%RELIANCE%'
    OR trading_symbol LIKE '%INFY%'
    OR trading_symbol LIKE '%TCS%'
    OR psymbol LIKE '%RELIANCE%'
    OR psymbol LIKE '%INFY%'
    OR psymbol LIKE '%TCS%'
    LIMIT 20
"""))

print("\nTest symbols found:")
for row in result:
    print(f"  psymbol: {row[0]}, trading_symbol: {row[1]}, exchange: {row[2]}, token: {row[3]}")

conn.close()
