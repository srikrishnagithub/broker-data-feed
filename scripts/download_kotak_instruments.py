#!/usr/bin/env python3
"""
Download KOTAK NEO instrument master and store in database.

This script:
1. Authenticates with KOTAK NEO
2. Downloads instrument master file
3. Stores it in database table 'kotak_instruments'
4. Creates indexes for fast lookup

Usage:
    python scripts/download_kotak_instruments.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from brokers.kotak_neo_broker import KotakNeoBroker
from config.config import Config
from core.database_handler import DatabaseHandler
from sqlalchemy import Table, Column, Integer, String, MetaData, Index, create_engine, text
from datetime import datetime


def create_kotak_instruments_table(db_handler: DatabaseHandler):
    """
    Create kotak_instruments table if it doesn't exist.
    
    Table structure based on typical instrument master fields.
    """
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
            # Execute each statement separately
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


def download_and_store_instruments():
    """
    Main function to download and store KOTAK instruments.
    """
    print("=" * 70)
    print("KOTAK NEO Instrument Master Downloader")
    print("=" * 70)
    print()
    
    try:
        # Initialize config and database
        print("1. Initializing configuration...")
        config = Config()
        broker_config = config.get_broker_config('kotak')
        db_handler = DatabaseHandler(logger=lambda msg, level: print(f"[{level}] {msg}"))
        
        print("✅ Configuration loaded")
        
        # Create table
        print("\n2. Setting up database table...")
        if not create_kotak_instruments_table(db_handler):
            return False
        
        # Initialize broker
        print("\n3. Initializing KOTAK NEO broker...")
        broker = KotakNeoBroker(broker_config, logger=lambda msg, level: print(f"[{level}] {msg}"))
        
        # Authenticate
        print("\n4. Authenticating with KOTAK NEO...")
        if not broker.connect():
            print("❌ Authentication failed")
            return False
        
        print("✅ Authentication successful")
        
        # Fetch instrument master
        print("\n5. Downloading instrument master...")
        if not broker.fetch_instrument_master():
            print("❌ Failed to download instrument master")
            return False
        
        if not hasattr(broker, '_instrument_master') or not broker._instrument_master:
            print("❌ No instrument data received")
            return False
        
        instruments = broker._instrument_master
        print(f"✅ Downloaded {len(instruments)} instruments")
        
        # Clear existing data
        print("\n6. Clearing old data...")
        try:
            with db_handler.engine.connect() as conn:
                conn.execute(text("DELETE FROM kotak_instruments"))
                conn.commit()
            print("✅ Old data cleared")
        except Exception as e:
            print(f"❌ Error clearing old data: {e}")
            return False
        
        # Insert instruments into database
        print("\n7. Inserting instruments into database...")
        
        inserted = 0
        failed = 0
        batch_size = 1000
        
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            
            try:
                with db_handler.engine.connect() as conn:
                    for inst in batch:
                        # Extract fields (field names may vary)
                        exchange = inst.get('exchange') or inst.get('exch') or ''
                        exchange_segment = inst.get('exchange_segment') or inst.get('exch_seg') or ''
                        token = inst.get('token') or inst.get('instrument_token') or ''
                        trading_symbol = inst.get('tradingsymbol') or inst.get('symbol') or ''
                        name = inst.get('name') or inst.get('company_name') or ''
                        instrument_type = inst.get('instrument_type') or inst.get('inst_type') or ''
                        psymbol = inst.get('pSymbol') or inst.get('psymbol') or trading_symbol
                        expiry = inst.get('expiry') or None
                        strike = inst.get('strike') or 0
                        lot_size = inst.get('lot_size') or inst.get('lotsize') or 1
                        tick_size = inst.get('tick_size') or inst.get('ticksize') or 0.05
                        
                        insert_sql = """
                        INSERT INTO kotak_instruments 
                            (exchange, exchange_segment, token, trading_symbol, name, 
                             instrument_type, psymbol, expiry, strike, lot_size, tick_size)
                        VALUES 
                            (:exchange, :exchange_segment, :token, :trading_symbol, :name,
                             :instrument_type, :psymbol, :expiry, :strike, :lot_size, :tick_size)
                        """
                        
                        conn.execute(text(insert_sql), {
                            'exchange': exchange,
                            'exchange_segment': exchange_segment,
                            'token': str(token),
                            'trading_symbol': trading_symbol,
                            'name': name,
                            'instrument_type': instrument_type,
                            'psymbol': psymbol,
                            'expiry': expiry,
                            'strike': float(strike) if strike else 0,
                            'lot_size': int(lot_size) if lot_size else 1,
                            'tick_size': float(tick_size) if tick_size else 0.05
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
        print(f"✅ Total instruments downloaded: {len(instruments)}")
        print(f"✅ Successfully inserted: {inserted}")
        if failed > 0:
            print(f"❌ Failed: {failed}")
        print()
        print("You can now query instruments with:")
        print("  SELECT * FROM kotak_instruments WHERE trading_symbol = 'RELIANCE';")
        print("  SELECT psymbol FROM kotak_instruments WHERE trading_symbol LIKE 'RELIANCE%';")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = download_and_store_instruments()
    sys.exit(0 if success else 1)
