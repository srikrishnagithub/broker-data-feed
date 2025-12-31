import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('PG_CONN_STR'))

with engine.connect() as conn:
    # Check what's in fundamental table
    result = conn.execute(text(
        'SELECT "SYMBOL" FROM fundamental WHERE "SYMBOL" ILIKE :pattern LIMIT 10'
    ), {'pattern': '%TATA%'})
    
    print('TATA symbols in fundamental table:')
    for row in result:
        print(f'  {row[0]}')
    
    print('\nChecking kotak_instruments for similar:')
    result = conn.execute(text(
        'SELECT trading_symbol, name FROM kotak_instruments WHERE (trading_symbol ILIKE :pattern OR name ILIKE :pattern) AND exchange_segment = :seg LIMIT 15'
    ), {'pattern': '%TATA%', 'seg': 'nse_cm'})
    
    for row in result:
        print(f'  {row[0]:30} | {row[1]}')
