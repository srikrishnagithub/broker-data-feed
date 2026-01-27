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
    
    def get_latest_candle_timestamp(self, table_name: str = 'live_candles_5min', symbol: Optional[str] = None) -> Optional[datetime]:
        """
        Get the timestamp of the most recent candle in a table.
        
        Args:
            table_name: Table to query
            symbol: Optional symbol filter (if None, checks across all symbols)
        
        Returns:
            Latest candle timestamp or None if no data
        """
        try:
            with self.engine.connect() as conn:
                if symbol:
                    query = text(f"""
                        SELECT MAX(datetime) as latest_timestamp
                        FROM {table_name}
                        WHERE tradingsymbol = :symbol
                    """)
                    result = conn.execute(query, {"symbol": symbol})
                else:
                    query = text(f"""
                        SELECT MAX(datetime) as latest_timestamp
                        FROM {table_name}
                    """)
                    result = conn.execute(query)
                
                row = result.fetchone()
                if row and row[0]:
                    return row[0]
                return None
        except Exception as e:
            self.logger(f"Error getting latest candle timestamp: {e}", "ERROR")
            return None
    
    def get_data_age_minutes(self, table_name: str = 'live_candles_5min', symbol: Optional[str] = None) -> Optional[float]:
        """
        Get the age in minutes of the most recent candle.
        
        Args:
            table_name: Table to query
            symbol: Optional symbol filter
        
        Returns:
            Age in minutes or None if no data
        """
        latest_timestamp = self.get_latest_candle_timestamp(table_name, symbol)
        if latest_timestamp:
            # Ensure timezone awareness
            import pytz
            IST = pytz.timezone('Asia/Kolkata')
            now = datetime.now(IST)
            
            # Make latest_timestamp timezone-aware if needed
            if latest_timestamp.tzinfo is None:
                latest_timestamp = IST.localize(latest_timestamp)
            else:
                latest_timestamp = latest_timestamp.astimezone(IST)
            
            age_seconds = (now - latest_timestamp).total_seconds()
            return age_seconds / 60
        return None
    
    def check_data_health(self, table_name: str = 'live_candles_5min', max_age_minutes: float = 10) -> Dict[str, Any]:
        """
        Check health of live data feed.
        
        Args:
            table_name: Table to check
            max_age_minutes: Maximum acceptable age in minutes
        
        Returns:
            Dictionary with health status
        """
        health = {
            'healthy': False,
            'latest_timestamp': None,
            'age_minutes': None,
            'message': ''
        }
        
        try:
            latest_timestamp = self.get_latest_candle_timestamp(table_name)
            if not latest_timestamp:
                health['message'] = f"No data found in {table_name}"
                self.logger(f"[HEALTH CHECK] {health['message']}", "WARNING")
                return health
            
            age_minutes = self.get_data_age_minutes(table_name)
            health['latest_timestamp'] = latest_timestamp
            health['age_minutes'] = age_minutes
            
            if age_minutes is not None and age_minutes > max_age_minutes:
                health['healthy'] = False
                health['message'] = f"Data is stale: {age_minutes:.1f} minutes old (threshold: {max_age_minutes} min)"
                self.logger(f"[HEALTH CHECK] {health['message']}", "WARNING")
            else:
                health['healthy'] = True
                health['message'] = f"Data is healthy: {age_minutes:.1f} minutes old"
                self.logger(f"[HEALTH CHECK] {health['message']}", "INFO")
            
            return health
            
        except Exception as e:
            health['message'] = f"Health check failed: {e}"
            self.logger(f"[HEALTH CHECK] {health['message']}", "ERROR")
            return health
    
    def aggregate_5min_to_15min(self, symbol: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        """
        Aggregate latest 5-minute candles into a 15-minute candle.
        
        Groups the latest 3 consecutive 5-minute candles into one 15-minute candle.
        
        Args:
            symbol: Trading symbol
            limit: Maximum number of 5-min candles to fetch (default 100)
        
        Returns:
            Dictionary with aggregated 15-minute candle data, or None if insufficient data
        """
        try:
            query = text("""
                SELECT 
                    datetime, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume,
                    instrument_token
                FROM live_candles_5min
                WHERE tradingsymbol = :symbol
                ORDER BY datetime DESC
                LIMIT :limit
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query, {"symbol": symbol, "limit": limit}).fetchall()
            
            if not result or len(result) < 3:
                self.logger(f"Insufficient 5-minute candles for {symbol}: {len(result) if result else 0}", "WARNING")
                return None
            
            # Reverse to get chronological order (newest first, so reverse back)
            candles = list(reversed(result))
            
            # Get the first 3 candles for aggregation
            agg_candles = candles[:3]
            
            # Calculate 15-minute candle timestamp
            first_datetime = agg_candles[0][0]  # datetime column
            if isinstance(first_datetime, str):
                from datetime import datetime as dt
                first_datetime = dt.fromisoformat(first_datetime)
            
            minutes = (first_datetime.minute // 15) * 15
            candle_15min_timestamp = first_datetime.replace(minute=minutes, second=0, microsecond=0)
            
            # Aggregate data
            result_dict = {
                'datetime': candle_15min_timestamp,
                'symbol': symbol,
                'instrument_token': agg_candles[0][6],  # instrument_token from first candle
                'open': float(agg_candles[0][1]),  # open from first candle
                'high': max(float(c[2]) for c in agg_candles),  # max high
                'low': min(float(c[3]) for c in agg_candles),  # min low
                'close': float(agg_candles[-1][4]),  # close from last candle
                'volume': sum(int(c[5]) for c in agg_candles),  # sum of volumes
                'tick_count': 3,
                'source': 'aggregated'
            }
            
            self.logger(f"Aggregated 3 x 5-min candles for {symbol} into 15-min candle at {candle_15min_timestamp}", "DEBUG")
            return result_dict
            
        except Exception as e:
            self.logger(f"Error aggregating 5-min to 15-min candles for {symbol}: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
            return None
    
    def close(self):
        """Close database connection."""
        try:
            self.engine.dispose()
            self.logger("Database connection closed", "INFO")
        except Exception as e:
            self.logger(f"Error closing database connection: {e}", "WARNING")
    
    def backfill_missing_15min_candles(self, symbol: str) -> int:
        """
        Detect and backfill missing 15-minute candles from 5-minute candles.
        
        Checks for gaps in the 15-minute candles table and fills them using
        available 5-minute candles.
        
        Args:
            symbol: Trading symbol to backfill
        
        Returns:
            Number of 15-minute candles backfilled
        """
        try:
            # Get all 5-minute candles
            query_5min = text("""
                SELECT 
                    datetime, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume,
                    instrument_token
                FROM live_candles_5min
                WHERE tradingsymbol = :symbol
                ORDER BY datetime ASC
            """)
            
            with self.engine.connect() as conn:
                result_5min = conn.execute(query_5min, {"symbol": symbol}).fetchall()
            
            if not result_5min or len(result_5min) < 3:
                self.logger(f"Insufficient 5-minute candles for {symbol}: {len(result_5min) if result_5min else 0}", "WARNING")
                return 0
            
            # Convert to DataFrame for easier manipulation
            df_5min = pd.DataFrame(result_5min, columns=[
                'datetime', 'open', 'high', 'low', 'close', 'volume', 'instrument_token'
            ])
            df_5min['datetime'] = pd.to_datetime(df_5min['datetime'])
            
            # Get existing 15-minute candles
            query_15min = text("""
                SELECT datetime
                FROM live_candles_15min
                WHERE tradingsymbol = :symbol
                ORDER BY datetime ASC
            """)
            
            with self.engine.connect() as conn:
                result_15min = conn.execute(query_15min, {"symbol": symbol}).fetchall()
            
            existing_15min_datetimes = set(pd.to_datetime([r[0] for r in result_15min])) if result_15min else set()
            
            # Generate expected 15-minute timestamps from 5-minute candles
            backfilled_candles = []
            i = 0
            
            while i + 2 < len(df_5min):
                # Get 3 consecutive 5-minute candles
                candle_group = df_5min.iloc[i:i+3]
                
                # Calculate 15-minute timestamp
                first_datetime = candle_group.iloc[0]['datetime']
                minutes = (first_datetime.minute // 15) * 15
                candle_15min_ts = first_datetime.replace(minute=minutes, second=0, microsecond=0)
                
                # Check if this 15-minute candle already exists
                if candle_15min_ts not in existing_15min_datetimes:
                    # Create aggregated candle
                    agg_candle = {
                        'datetime': candle_15min_ts,
                        'symbol': symbol,
                        'instrument_token': int(candle_group.iloc[0]['instrument_token']),
                        'open': float(candle_group.iloc[0]['open']),
                        'high': float(candle_group['high'].max()),
                        'low': float(candle_group['low'].min()),
                        'close': float(candle_group.iloc[-1]['close']),
                        'volume': int(candle_group['volume'].sum()),
                        'tick_count': 3,
                        'source': 'backfilled'
                    }
                    backfilled_candles.append(agg_candle)
                    self.logger(f"Backfill 15-min: {symbol} at {candle_15min_ts}", "DEBUG")
                
                i += 3
            
            # Save backfilled candles
            if backfilled_candles:
                from core.candle_aggregator import Candle
                
                candle_objects = []
                for candle_dict in backfilled_candles:
                    candle = Candle(
                        symbol=candle_dict['symbol'],
                        interval=15,
                        timestamp=candle_dict['datetime'],
                        instrument_token=candle_dict['instrument_token']
                    )
                    candle.open = candle_dict['open']
                    candle.high = candle_dict['high']
                    candle.low = candle_dict['low']
                    candle.close = candle_dict['close']
                    candle.volume = candle_dict['volume']
                    candle.tick_count = candle_dict['tick_count']
                    candle_objects.append(candle)
                
                saved = self.save_candles(candle_objects, table_name='live_candles_15min', on_duplicate='update')
                self.logger(f"Backfilled {saved} 15-minute candles for {symbol}", "INFO")
                return saved
            else:
                self.logger(f"No missing 15-minute candles to backfill for {symbol}", "INFO")
                return 0
            
        except Exception as e:
            self.logger(f"Error backfilling 15-minute candles for {symbol}: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
            return 0
    
    def backfill_missing_60min_candles(self, symbol: str) -> int:
        """
        Detect and backfill missing 60-minute candles from 15-minute candles.
        
        Checks for gaps in the 60-minute candles table and fills them using
        available 15-minute candles.
        
        Args:
            symbol: Trading symbol to backfill
        
        Returns:
            Number of 60-minute candles backfilled
        """
        try:
            # Get all 15-minute candles
            query_15min = text("""
                SELECT 
                    datetime, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume,
                    instrument_token
                FROM live_candles_15min
                WHERE tradingsymbol = :symbol
                ORDER BY datetime ASC
            """)
            
            with self.engine.connect() as conn:
                result_15min = conn.execute(query_15min, {"symbol": symbol}).fetchall()
            
            if not result_15min or len(result_15min) < 4:
                self.logger(f"Insufficient 15-minute candles for {symbol}: {len(result_15min) if result_15min else 0}", "WARNING")
                return 0
            
            # Convert to DataFrame
            df_15min = pd.DataFrame(result_15min, columns=[
                'datetime', 'open', 'high', 'low', 'close', 'volume', 'instrument_token'
            ])
            df_15min['datetime'] = pd.to_datetime(df_15min['datetime'])
            
            # Get existing 60-minute candles
            query_60min = text("""
                SELECT datetime
                FROM live_candles_60min
                WHERE tradingsymbol = :symbol
                ORDER BY datetime ASC
            """)
            
            with self.engine.connect() as conn:
                result_60min = conn.execute(query_60min, {"symbol": symbol}).fetchall()
            
            existing_60min_datetimes = set(pd.to_datetime([r[0] for r in result_60min])) if result_60min else set()
            
            # Generate expected 60-minute timestamps from 15-minute candles
            backfilled_candles = []
            i = 0
            
            while i + 3 < len(df_15min):
                # Get 4 consecutive 15-minute candles (4 * 15 = 60 minutes)
                candle_group = df_15min.iloc[i:i+4]
                
                # Calculate 60-minute timestamp
                first_datetime = candle_group.iloc[0]['datetime']
                hour = first_datetime.hour
                candle_60min_ts = first_datetime.replace(minute=0, second=0, microsecond=0)
                
                # Check if this 60-minute candle already exists
                if candle_60min_ts not in existing_60min_datetimes:
                    # Create aggregated candle
                    agg_candle = {
                        'datetime': candle_60min_ts,
                        'symbol': symbol,
                        'instrument_token': int(candle_group.iloc[0]['instrument_token']),
                        'open': float(candle_group.iloc[0]['open']),
                        'high': float(candle_group['high'].max()),
                        'low': float(candle_group['low'].min()),
                        'close': float(candle_group.iloc[-1]['close']),
                        'volume': int(candle_group['volume'].sum()),
                        'tick_count': 4,
                        'source': 'backfilled'
                    }
                    backfilled_candles.append(agg_candle)
                    self.logger(f"Backfill 60-min: {symbol} at {candle_60min_ts}", "DEBUG")
                
                i += 4
            
            # Save backfilled candles
            if backfilled_candles:
                from core.candle_aggregator import Candle
                
                candle_objects = []
                for candle_dict in backfilled_candles:
                    candle = Candle(
                        symbol=candle_dict['symbol'],
                        interval=60,
                        timestamp=candle_dict['datetime'],
                        instrument_token=candle_dict['instrument_token']
                    )
                    candle.open = candle_dict['open']
                    candle.high = candle_dict['high']
                    candle.low = candle_dict['low']
                    candle.close = candle_dict['close']
                    candle.volume = candle_dict['volume']
                    candle.tick_count = candle_dict['tick_count']
                    candle_objects.append(candle)
                
                saved = self.save_candles(candle_objects, table_name='live_candles_60min', on_duplicate='update')
                self.logger(f"Backfilled {saved} 60-minute candles for {symbol}", "INFO")
                return saved
            else:
                self.logger(f"No missing 60-minute candles to backfill for {symbol}", "INFO")
                return 0
            
        except Exception as e:
            self.logger(f"Error backfilling 60-minute candles for {symbol}: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
            return 0
    
    def startup_backfill_all_symbols(self) -> Dict[str, Dict[str, int]]:
        """
        Run backfill for all symbols on startup.
        
        Checks all symbols in live_candles_5min and backfills any missing
        15-minute and 60-minute candles.
        
        Returns:
            Dictionary with backfill results:
            {
                'symbol_name': {
                    '15min_backfilled': int,
                    '60min_backfilled': int
                },
                ...
            }
        """
        try:
            # Get all symbols from 5-minute table
            query = text("""
                SELECT DISTINCT tradingsymbol
                FROM live_candles_5min
                ORDER BY tradingsymbol
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query)
                symbols = [row[0] for row in result]
            
            if not symbols:
                self.logger("No symbols found for backfill", "WARNING")
                return {}
            
            self.logger(f"Starting backfill for {len(symbols)} symbols", "INFO")
            
            results = {}
            for symbol in symbols:
                self.logger(f"\nBackfilling {symbol}...", "INFO")
                
                # Backfill 15-minute candles
                backfilled_15min = self.backfill_missing_15min_candles(symbol)
                
                # Backfill 60-minute candles (depends on 15-min being complete)
                backfilled_60min = self.backfill_missing_60min_candles(symbol)
                
                results[symbol] = {
                    '15min_backfilled': backfilled_15min,
                    '60min_backfilled': backfilled_60min
                }
            
            # Print summary
            self.logger("\n" + "="*80, "INFO")
            self.logger("BACKFILL SUMMARY", "INFO")
            self.logger("="*80, "INFO")
            
            total_15min = 0
            total_60min = 0
            
            for symbol, counts in results.items():
                self.logger(f"{symbol}: 15-min={counts['15min_backfilled']}, 60-min={counts['60min_backfilled']}", "INFO")
                total_15min += counts['15min_backfilled']
                total_60min += counts['60min_backfilled']
            
            self.logger(f"\nTOTAL: 15-min={total_15min}, 60-min={total_60min}", "INFO")
            self.logger("="*80, "INFO")
            
            return results
            
        except Exception as e:
            self.logger(f"Error in startup backfill: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
            return {}
