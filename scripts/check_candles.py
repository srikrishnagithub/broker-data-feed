import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database_handler import DatabaseHandler
from sqlalchemy import text

db = DatabaseHandler()
conn = db.engine.connect()

result = conn.execute(text("""
    SELECT tradingsymbol, datetime, open, high, low, close, volume 
    FROM live_candles_5min 
    WHERE datetime >= CURRENT_DATE 
    ORDER BY datetime DESC, tradingsymbol 
    LIMIT 10
"""))

print("\n📊 Recent 5-Minute Candles (Today):\n")
print(f"{'Symbol':<10} {'DateTime':<25} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>10}")
print("=" * 95)

for row in result:
    symbol = row[0]
    dt = row[1]
    o, h, l, c = row[2], row[3], row[4], row[5]
    vol = row[6]
    print(f"{symbol:<10} {str(dt):<25} {o:8.2f} {h:8.2f} {l:8.2f} {c:8.2f} {vol:10,}")

conn.close()
