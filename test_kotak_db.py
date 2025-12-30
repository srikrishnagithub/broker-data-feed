from sqlalchemy import create_engine, text
import os

os.environ['PG_CONN_STR'] = 'postgresql://postgres:root@localhost:5432/broker_data_feed'
engine = create_engine(os.environ['PG_CONN_STR'])

with engine.connect() as conn:
    result = conn.execute(text("SELECT exchange_token, trading_symbol, psymbol FROM kotak_instruments WHERE trading_symbol LIKE 'RELIANCE%' LIMIT 3"))
    for row in result:
        print(f"exchange_token={row[0]}, trading_symbol={row[1]}, psymbol={row[2]}")
