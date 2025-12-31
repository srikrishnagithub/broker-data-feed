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
        
        print("[OK] Table created successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Error creating table: {e}")
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
        
        print("[OK] Configuration loaded")
        
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
            print("[ERROR] Authentication failed")
            return False
        
        print("[OK] Authentication successful")
        
        # Fetch instrument master
        print("\n5. Downloading instrument master...")
        if not broker.fetch_instrument_master():
            print("[ERROR] Failed to download instrument master")
            return False
        
        if not hasattr(broker, '_instrument_master') or not broker._instrument_master:
            print("[ERROR] No instrument data received")
            return False
        
        instruments = broker._instrument_master
        print(f"[OK] Downloaded {len(instruments)} instruments")
        
        # Clear existing data
        print("\n6. Clearing old data...")
        try:
            with db_handler.engine.connect() as conn:
                conn.execute(text("DELETE FROM kotak_instruments"))
                conn.commit()
            print("[OK] Old data cleared")
        except Exception as e:
            print(f"[ERROR] Error clearing old data: {e}")
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
                        # Extract fields from KOTAK CSV structure
                        # Token is the exchange token (numeric ID) used for API calls
                        # Trading symbol is the symbol name used for lookup (e.g., 'RELIANCE')
                        exchange = inst.get('pExchange') or ''
                        exchange_segment = inst.get('pExchSeg') or ''
                        token = inst.get('pSymbol') or ''  # Exchange token (numeric) - REQUIRED for API quotes
                        trading_symbol = inst.get('pTrdSymbol') or ''  # Trading symbol like 'RELIANCE' - for lookup
                        name = inst.get('pDesc') or inst.get('pSymbolName') or ''
                        instrument_type = inst.get('pInstType') or ''
                        psymbol = inst.get('pSymbol') or ''  # Same as token, stored for reference
                        expiry = inst.get('pExpiryDate') or None
                        strike = inst.get('dStrikePrice;') or 0
                        lot_size = inst.get('lLotSize') or inst.get('iLotSize') or 1
                        tick_size = inst.get('dTickSize ') or 0.05
                        
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
        print(f"[OK] Total instruments downloaded: {len(instruments)}")
        print(f"[OK] Successfully inserted: {inserted}")
        if failed > 0:
            print(f"[WARN] Failed: {failed}")
        print()
        print("You can now query instruments with:")
        print("  SELECT * FROM kotak_instruments WHERE trading_symbol = 'RELIANCE';")
        print("  SELECT psymbol FROM kotak_instruments WHERE trading_symbol LIKE 'RELIANCE%';")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = download_and_store_instruments()
    sys.exit(0 if success else 1)
