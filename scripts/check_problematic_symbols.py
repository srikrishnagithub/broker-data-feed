"""
Check problematic symbols in database
"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv('PG_CONN_STR'))

print("\n=== Checking problematic symbols ===\n")

with engine.connect() as conn:
    # Check if symbols exist in fundamental table
    result = conn.execute(text("""
        SELECT "SYMBOL" 
        FROM fundamental 
        WHERE "SYMBOL" IN ('BAJAJ', 'IIFLHF29', 'M&MFIN', 'BAJAJFINSV', 'BAJAJ-AUTO', 'M&M')
        ORDER BY "SYMBOL"
    """))
    
    print("Symbols in fundamental table:")
    for row in result:
        print(f"  - {row[0]}")
    
    # Check if they exist in instruments table
    print("\nSymbols in instruments table:")
    result = conn.execute(text("""
        SELECT tradingsymbol, instrument_token
        FROM instruments 
        WHERE tradingsymbol LIKE '%BAJAJ%' 
           OR tradingsymbol LIKE '%IIFL%'
           OR tradingsymbol LIKE '%M&M%'
        ORDER BY tradingsymbol
        LIMIT 20
    """))
    
    for row in result:
        print(f"  - {row[0]} (token: {row[1]})")

print("\nDone!")
