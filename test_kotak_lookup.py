from sqlalchemy import create_engine, text
from config.config import Config

config = Config()
engine = create_engine(config.get_database_config()['connection_string'])

with engine.connect() as conn:
    # Check specific stocks
    result = conn.execute(text("""
        SELECT trading_symbol, psymbol, exchange_segment
        FROM kotak_instruments 
        WHERE trading_symbol IN ('RELIANCE', 'INFY', 'TCS', 'AARTIIND', 'ABREL')
        LIMIT 10
    """))
    
    print("Query results for requested symbols:")
    for row in result:
        print(f"  trading_symbol: '{row[0]}', psymbol: '{row[1]}', exchange_segment: '{row[2]}'")
