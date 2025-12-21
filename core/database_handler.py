"""
Database handler for storing OHLC candles.
"""
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
import pandas as pd

load_dotenv()


class DatabaseHandler:
    """Handles database operations for candle storage."""
    
    def __init__(self, connection_string: Optional[str] = None, logger=None):
        """
        Initialize database handler.
        
        Args:
            connection_string: Database connection string (default: from PG_CONN_STR env)
            logger: Optional logging function
        """
        self.logger = logger or self._default_logger
        
        # Get connection string
        conn_str = connection_string or os.getenv('PG_CONN_STR')
        if not conn_str:
            raise ValueError("Database connection string not provided. Set PG_CONN_STR environment variable.")
        
        # Create engine
        try:
            self.engine = create_engine(conn_str, pool_pre_ping=True)
            self.logger("Database engine created successfully", "SUCCESS")
        except Exception as e:
            self.logger(f"Failed to create database engine: {e}", "ERROR")
            raise
    
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def test_connection(self) -> bool:
        """
        Test database connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self.logger("Database connection test successful", "SUCCESS")
            return True
        except Exception as e:
            self.logger(f"Database connection test failed: {e}", "ERROR")
            return False
    
    def check_table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            True if table exists, False otherwise
        """
        try:
            inspector = inspect(self.engine)
            exists = table_name in inspector.get_table_names()
            if exists:
                self.logger(f"Table '{table_name}' exists", "INFO")
            else:
                self.logger(f"Table '{table_name}' does not exist", "WARNING")
            return exists
        except Exception as e:
            self.logger(f"Error checking table existence: {e}", "ERROR")
            return False
    
    def save_candles(self, candles: List, table_name: str = 'live_candles_5min') -> int:
        """
        Save candles to database.
        
        Args:
            candles: List of Candle objects
            table_name: Target table name
            
        Returns:
            Number of candles saved
        """
        if not candles:
            return 0
        
        try:
            # Filter out zero-volume candles
            valid_candles = []
            for candle in candles:
                if candle.volume == 0:
                    self.logger(
                        f"Skipping zero-volume candle in database save: {candle.symbol} at {candle.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                        "WARNING"
                    )
                else:
                    valid_candles.append(candle)
            
            if not valid_candles:
                self.logger("No valid candles to save (all had zero volume)", "WARNING")
                return 0
            
            # Convert valid candles to dataframe
            candle_dicts = [c.to_dict() for c in valid_candles]
            df = pd.DataFrame(candle_dicts)
            
            # Remove tick_count column if it exists (not in current table schema)
            if 'tick_count' in df.columns:
                df = df.drop(columns=['tick_count'])
            
            # Ensure datetime is datetime type
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
            
            # Save to database
            with self.engine.connect() as conn:
                df.to_sql(
                    table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi'
                )
            
            self.logger(f"Saved {len(valid_candles)} candles to {table_name}", "SUCCESS")
            return len(valid_candles)
            
        except Exception as e:
            self.logger(f"Error saving candles to database: {e}", "ERROR")
            return 0
    
    def get_latest_candle(self, symbol: str, table_name: str = 'merged_candles_5min') -> Optional[Dict[str, Any]]:
        """
        Get the latest candle for a symbol.
        
        Args:
            symbol: Trading symbol
            table_name: Source table name
            
        Returns:
            Dictionary with candle data or None
        """
        try:
            query = text(f"""
                SELECT datetime, open, high, low, close, volume
                FROM {table_name}
                WHERE tradingsymbol = :symbol
                ORDER BY datetime DESC
                LIMIT 1
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query, {"symbol": symbol}).fetchone()
                
                if result:
                    return {
                        'datetime': result[0],
                        'open': float(result[1]),
                        'high': float(result[2]),
                        'low': float(result[3]),
                        'close': float(result[4]),
                        'volume': int(result[5])
                    }
                
                return None
                
        except Exception as e:
            self.logger(f"Error fetching latest candle: {e}", "ERROR")
            return None
    
    def get_candle_count(self, symbol: Optional[str] = None, table_name: str = 'merged_candles_5min') -> int:
        """
        Get count of candles in database.
        
        Args:
            symbol: Optional symbol filter
            table_name: Source table name
            
        Returns:
            Count of candles
        """
        try:
            if symbol:
                query = text(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE tradingsymbol = :symbol
                """)
                params = {"symbol": symbol}
            else:
                query = text(f"SELECT COUNT(*) FROM {table_name}")
                params = {}
            
            with self.engine.connect() as conn:
                result = conn.execute(query, params).scalar()
                return result or 0
                
        except Exception as e:
            self.logger(f"Error getting candle count: {e}", "ERROR")
            return 0
    
    def close(self):
        """Close database connection."""
        try:
            self.engine.dispose()
            self.logger("Database connection closed", "INFO")
        except Exception as e:
            self.logger(f"Error closing database connection: {e}", "WARNING")
