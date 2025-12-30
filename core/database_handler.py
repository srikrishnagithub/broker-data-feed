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
    
    def save_candles(self, candles: List, table_name: str = 'live_candles_5min', on_duplicate: str = 'update') -> int:
        """
        Save candles to database with duplicate handling using efficient bulk insert.
        
        Args:
            candles: List of Candle objects
            table_name: Target table name
            on_duplicate: How to handle duplicates - 'update' (default), 'skip', or 'error'
            
        Returns:
            Number of candles saved
        """
        if not candles:
            return 0

        try:
            # Process all candles without volume filtering
            valid_candles = list(candles)

            if not valid_candles:
                self.logger("No valid candles to save (all had zero volume)", "WARNING")
                return 0

            # Convert valid candles to dataframe
            candle_dicts = [c.to_dict() for c in valid_candles]
            df = pd.DataFrame(candle_dicts)

            # Remove tick_count column if it exists (not in current table schema)
            if 'tick_count' in df.columns:
                df = df.drop(columns=['tick_count'])
            
            # Remove created_at column if it exists (not in table schema)
            if 'created_at' in df.columns:
                df = df.drop(columns=['created_at'])

            # Ensure datetime columns are Python datetime objects (not pandas Timestamp)
            if 'datetime' in df.columns:
                df['datetime'] = df['datetime'].apply(lambda x: x.to_pydatetime() if hasattr(x, 'to_pydatetime') else x)
                
                with self.engine.connect() as conn:
                    for _, row in df.iterrows():
                        # Skip candles with invalid instrument_token
                        if pd.isna(row['instrument_token']) or row['instrument_token'] is None:
                            self.logger(f"Skipping candle with None token: {row['tradingsymbol']}", "WARNING")
                            continue
                        
                        if on_duplicate == 'update':
                            query = text(f"""
                                INSERT INTO {table_name}
                                (instrument_token, tradingsymbol, datetime, open, high, low, close, volume)
                                VALUES (:token, :symbol, :dt, :o, :h, :l, :c, :v)
                                ON CONFLICT (instrument_token, datetime)
                                DO UPDATE SET
                                    tradingsymbol = EXCLUDED.tradingsymbol,
                                    open = EXCLUDED.open,
                                    high = EXCLUDED.high,
                                    low = EXCLUDED.low,
                                    close = EXCLUDED.close,
                                    volume = EXCLUDED.volume
                            """)
                        elif on_duplicate == 'skip':
                            query = text(f"""
                                INSERT INTO {table_name}
                                (instrument_token, tradingsymbol, datetime, open, high, low, close, volume)
                                VALUES (:token, :symbol, :dt, :o, :h, :l, :c, :v)
                                ON CONFLICT (instrument_token, datetime)
                                DO NOTHING
                            """)
                        else:
                            query = text(f"""
                                INSERT INTO {table_name}
                                (instrument_token, tradingsymbol, datetime, open, high, low, close, volume)
                                VALUES (:token, :symbol, :dt, :o, :h, :l, :c, :v)
                            """)

                        conn.execute(query, {
                            'token': int(row['instrument_token']),
                            'symbol': str(row['tradingsymbol']),
                            'dt': row['datetime'],
                            'o': float(row['open']),
                            'h': float(row['high']),
                            'l': float(row['low']),
                            'c': float(row['close']),
                            'v': float(row['volume'])
                        })
                    conn.commit()

            return len(valid_candles)
            
        except Exception as e:
            self.logger(f"Error saving candles to database: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
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
    
    def aggregate_candles_on_startup(self, source_interval: int = 5, target_intervals: List[int] = None) -> Dict[int, int]:
        """
        Aggregate lower timeframe candles into higher timeframes on startup.
        
        Args:
            source_interval: Source interval in minutes (default: 5)
            target_intervals: List of target intervals to aggregate into (default: [15, 60])
            
        Returns:
            Dictionary with count of candles created per interval
        """
        if target_intervals is None:
            target_intervals = [15, 60]
        
        results = {}
        source_table = f'live_candles_{source_interval}min'
        
        try:
            # Check if source table exists and has data
            if not self.check_table_exists(source_table):
                self.logger(f"Source table {source_table} does not exist", "WARNING")
                return results
            
            for target_interval in target_intervals:
                if target_interval <= source_interval:
                    self.logger(f"Target interval {target_interval} must be greater than source {source_interval}", "WARNING")
                    continue
                
                if target_interval % source_interval != 0:
                    self.logger(f"Target interval {target_interval} must be a multiple of source {source_interval}", "WARNING")
                    continue
                
                target_table = f'live_candles_{target_interval}min'
                
                # Check if target table exists
                if not self.check_table_exists(target_table):
                    self.logger(f"Target table {target_table} does not exist", "WARNING")
                    continue
                
                self.logger(f"Aggregating {source_interval}min to {target_interval}min...", "INFO")
                
                # Aggregate using SQL
                # Group by instrument and time periods that align with target interval
                with self.engine.begin() as conn:
                    # Use date_trunc to group by target interval
                    aggregate_query = text(f"""
                        INSERT INTO {target_table} 
                        (instrument_token, tradingsymbol, datetime, open, high, low, close, volume)
                        SELECT 
                            instrument_token,
                            tradingsymbol,
                            date_trunc('hour', datetime) + 
                                (EXTRACT(minute FROM datetime)::int / {target_interval}) * INTERVAL '{target_interval} minutes' as datetime,
                            (array_agg(open ORDER BY datetime ASC))[1] as open,
                            MAX(high) as high,
                            MIN(low) as low,
                            (array_agg(close ORDER BY datetime DESC))[1] as close,
                            SUM(volume) as volume
                        FROM {source_table}
                        GROUP BY instrument_token, tradingsymbol, 
                            date_trunc('hour', datetime) + 
                            (EXTRACT(minute FROM datetime)::int / {target_interval}) * INTERVAL '{target_interval} minutes'
                        ON CONFLICT (instrument_token, datetime) 
                        DO UPDATE SET
                            tradingsymbol = EXCLUDED.tradingsymbol,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume
                    """)
                    
                    result = conn.execute(aggregate_query)
                    count = result.rowcount
                    results[target_interval] = count
                    self.logger(f"Aggregated {count} candles into {target_table}", "SUCCESS")
            
            return results
            
        except Exception as e:
            self.logger(f"Error during candle aggregation: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
            return results
    
    def close(self):
        """Close database connection."""
        try:
            self.engine.dispose()
            self.logger("Database connection closed", "INFO")
        except Exception as e:
            self.logger(f"Error closing database connection: {e}", "WARNING")
