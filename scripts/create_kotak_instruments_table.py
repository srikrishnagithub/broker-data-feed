"""
Script to create kotak_instruments table for storing KOTAK NEO instrument master data.
This table stores the mapping between symbols and exchange tokens for KOTAK NEO API.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, Column, String, Integer, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config.config import Config
config = Config()

Base = declarative_base()

class KotakInstrument(Base):
    __tablename__ = 'kotak_instruments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    exchange_token = Column(String(50), nullable=False)
    trading_symbol = Column(String(50), nullable=False)
    exchange_segment = Column(String(20), nullable=False)
    instrument_token = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

def create_table():
    """Create kotak_instruments table"""
    print("=" * 70)
    print("KOTAK NEO Instrument Table Creation")
    print("=" * 70)
    print()
    
    try:
        # Create database engine
        print("1. Connecting to database...")
        db_config = config.get_database_config()
        engine = create_engine(db_config['connection_string'])
        print("✅ Database connection established")
        print()
        
        # Create table
        print("2. Creating kotak_instruments table...")
        Base.metadata.create_all(engine)
        print("✅ Table created successfully")
        print()
        
        # Verify table exists
        print("3. Verifying table...")
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'kotak_instruments'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            
            if columns:
                print("✅ Table verified with columns:")
                for col in columns:
                    print(f"   - {col[0]:<20} ({col[1]})")
            else:
                print("❌ Table not found")
                return False
        
        print()
        print("=" * 70)
        print("✅ SUCCESS: kotak_instruments table is ready!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Run: python scripts/download_kotak_instruments.py")
        print("2. This will populate the table with instrument data")
        print()
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_table()
    sys.exit(0 if success else 1)
