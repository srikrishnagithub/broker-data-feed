#!/usr/bin/env python3
"""
Import KOTAK NEO instrument master from CSV file.

This script imports a manually downloaded instrument CSV file into the database.

How to get the CSV:
1. Login to KOTAK NEO web portal
2. Go to Trade API section
3. Download "Scrip Master" or "Instrument Master" CSV
4. Save it and run this script

Usage:
    python scripts/import_kotak_instruments_csv.py <path_to_csv>
    
Example:
    python scripts/import_kotak_instruments_csv.py instruments.csv
"""

import sys
import csv
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database_handler import DatabaseHandler
from config.config import Config
from sqlalchemy import text


def create_kotak_instruments_table(db_handler: DatabaseHandler):
    """Create kotak_instruments table if it doesn't exist."""
    print("Creating kotak_instruments table...")
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS kotak_instruments (
        id SERIAL PRIMARY KEY,
        exchange VARCHAR(20),
        exchange_segment VARCHAR(20),
        token VARCHAR(50),
        trading_symbol VARCHAR(100),
        name VARCHAR(200),
        instrument_type VARCHAR(50),
        psymbol VARCHAR(100),
        expiry DATE,
        strike DECIMAL(18, 4),
        lot_size INTEGER,
        tick_size DECIMAL(18, 4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Create indexes for fast lookup
    CREATE INDEX IF NOT EXISTS idx_kotak_trading_symbol ON kotak_instruments(trading_symbol);
    CREATE INDEX IF NOT EXISTS idx_kotak_psymbol ON kotak_instruments(psymbol);
    CREATE INDEX IF NOT EXISTS idx_kotak_exchange_segment ON kotak_instruments(exchange_segment);
    CREATE INDEX IF NOT EXISTS idx_kotak_token ON kotak_instruments(token);
    """
    
    try:
        with db_handler.engine.connect() as conn:
            for statement in create_table_sql.split(';'):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()
        
        print("✅ Table created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False


def import_csv(csv_path: str):
    """Import instrument CSV into database."""
    print("=" * 70)
    print("KOTAK NEO Instrument Master CSV Importer")
    print("=" * 70)
    print()
    
    # Check if file exists
    if not Path(csv_path).exists():
        print(f"❌ File not found: {csv_path}")
        return False
    
    try:
        # Initialize database
        print("1. Initializing database...")
        config = Config()
        db_handler = DatabaseHandler(logger=lambda msg, level: print(f"[{level}] {msg}"))
        print("✅ Database connected")
        
        # Create table
        print("\n2. Setting up database table...")
        if not create_kotak_instruments_table(db_handler):
            return False
        
        # Read CSV
        print(f"\n3. Reading CSV file: {csv_path}")
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            instruments = list(reader)
        
        print(f"✅ Read {len(instruments)} instruments from CSV")
        
        # Show sample
        if instruments:
            print("\nSample row (first instrument):")
            print(f"  Columns: {list(instruments[0].keys())}")
            print(f"  Sample: {instruments[0]}")
        
        # Clear existing data
        print("\n4. Clearing old data...")
        try:
            with db_handler.engine.connect() as conn:
                conn.execute(text("DELETE FROM kotak_instruments"))
                conn.commit()
            print("✅ Old data cleared")
        except Exception as e:
            print(f"⚠️  Warning: {e}")
        
        # Detect column names (different CSV formats)
        sample = instruments[0]
        columns = list(sample.keys())
        
        # Common column name variations
        col_mapping = {
            'exchange': ['exchange', 'exch', 'Exchange', 'pExchange'],
            'exchange_segment': ['exchange_segment', 'exch_seg', 'segment', 'ExchangeSegment', 'pExchSeg'],
            'token': ['token', 'instrument_token', 'Token', 'InstrumentToken', 'pSymbol'],
            'trading_symbol': ['tradingsymbol', 'trading_symbol', 'symbol', 'TradingSymbol', 'Symbol', 'pTrdSymbol', 'pSymbolName'],
            'name': ['name', 'company_name', 'Name', 'CompanyName', 'pDesc'],
            'instrument_type': ['instrument_type', 'inst_type', 'InstrumentType', 'pInstType'],
            'psymbol': ['pSymbol', 'psymbol', 'PSymbol', 'pTrdSymbol'],
            'expiry': ['expiry', 'Expiry', 'expiry_date', 'pExpiryDate', 'lExpiryDate '],
            'strike': ['strike', 'Strike', 'strike_price', 'dStrikePrice;'],
            'lot_size': ['lot_size', 'lotsize', 'LotSize', 'lLotSize', 'iLotSize'],
            'tick_size': ['tick_size', 'ticksize', 'TickSize', 'dTickSize ']
        }
        
        def get_column(row, field):
            """Get value from row using column mapping."""
            for col_name in col_mapping.get(field, []):
                if col_name in row:
                    return row[col_name]
            return ''
        
        # Insert instruments
        print("\n5. Inserting instruments into database...")
        
        inserted = 0
        failed = 0
        batch_size = 1000
        
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            
            try:
                with db_handler.engine.connect() as conn:
                    for inst in batch:
                        # Extract fields
                        exchange = get_column(inst, 'exchange')
                        exchange_segment = get_column(inst, 'exchange_segment')
                        token = get_column(inst, 'token')
                        trading_symbol = get_column(inst, 'trading_symbol')
                        name = get_column(inst, 'name')
                        instrument_type = get_column(inst, 'instrument_type')
                        psymbol = get_column(inst, 'psymbol') or trading_symbol
                        expiry = get_column(inst, 'expiry') or None
                        strike = get_column(inst, 'strike') or 0
                        lot_size = get_column(inst, 'lot_size') or 1
                        tick_size = get_column(inst, 'tick_size') or 0.05
                        
                        # Skip empty rows
                        if not trading_symbol:
                            continue
                        
                        insert_sql = """
                        INSERT INTO kotak_instruments 
                            (exchange, exchange_segment, token, trading_symbol, name, 
                             instrument_type, psymbol, expiry, strike, lot_size, tick_size)
                        VALUES 
                            (:exchange, :exchange_segment, :token, :trading_symbol, :name,
                             :instrument_type, :psymbol, :expiry, :strike, :lot_size, :tick_size)
                        """
                        
                        conn.execute(text(insert_sql), {
                            'exchange': exchange[:20] if exchange else '',
                            'exchange_segment': exchange_segment[:20] if exchange_segment else '',
                            'token': str(token)[:50],
                            'trading_symbol': trading_symbol[:100],
                            'name': name[:200] if name else '',
                            'instrument_type': instrument_type[:50] if instrument_type else '',
                            'psymbol': psymbol[:100],
                            'expiry': expiry if expiry and expiry != '' else None,
                            'strike': float(strike) if strike and strike != '' else 0,
                            'lot_size': int(lot_size) if lot_size and lot_size != '' else 1,
                            'tick_size': float(tick_size) if tick_size and tick_size != '' else 0.05
                        })
                        
                        inserted += 1
                    
                    conn.commit()
                    
                print(f"   Batch {i // batch_size + 1}: Inserted {len(batch)} instruments")
                
            except Exception as e:
                print(f"   ❌ Error in batch {i // batch_size + 1}: {e}")
                failed += len(batch)
        
        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"✅ Total instruments in CSV: {len(instruments)}")
        print(f"✅ Successfully inserted: {inserted}")
        if failed > 0:
            print(f"❌ Failed: {failed}")
        print()
        print("Verify with:")
        print("  SELECT COUNT(*) FROM kotak_instruments;")
        print("  SELECT * FROM kotak_instruments WHERE trading_symbol LIKE 'RELIANCE%';")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_kotak_instruments_csv.py <csv_file>")
        print()
        print("Example:")
        print("  python scripts/import_kotak_instruments_csv.py instruments.csv")
        print()
        print("How to get the CSV:")
        print("1. Login to KOTAK NEO web portal")
        print("2. Go to Trade API section")
        print("3. Download 'Scrip Master' or 'Instrument Master' CSV")
        print("4. Run this script with the downloaded file")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    success = import_csv(csv_path)
    sys.exit(0 if success else 1)
