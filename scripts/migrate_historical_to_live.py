"""
Script to migrate historical candle data to live tables for a given date and before a specific time.
"""
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from core.database_handler import DatabaseHandler
from sqlalchemy import text
import pandas as pd


def migrate_historical_to_live(
    db_handler: DatabaseHandler,
    date_str: str,
    time_str: str,
    interval: int,
    logger=None,
    on_duplicate: str = 'skip'
) -> int:
    """
    Migrate historical candle data to live table.
    
    Args:
        db_handler: Database handler instance
        date_str: Date in format YYYY-MM-DD (e.g., '2025-12-22')
        time_str: Time in format HH:MM:SS (e.g., '15:30:00')
        interval: Candle interval in minutes (5, 15, 60, etc.)
        logger: Optional logging function
        on_duplicate: How to handle duplicates - 'skip' or 'replace' (default: 'skip')
        
    Returns:
        Number of rows migrated
    """
    if not logger:
        logger = print
    
    try:
        # Parse inputs
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        target_time = datetime.strptime(time_str, '%H:%M:%S').time()
        
        # Construct datetime for filtering
        cutoff_datetime = datetime.combine(target_date.date(), target_time)
        
        source_table = f'historical_{interval}min'
        target_table = f'live_candles_{interval}min'
        
        logger(f"Starting migration from {source_table} to {target_table}")
        logger(f"Migration criteria: Date={date_str}, Before Time={time_str} (cutoff: {cutoff_datetime})")
        
        # Check if source table exists
        if not db_handler.check_table_exists(source_table):
            logger(f"Source table {source_table} does not exist", "ERROR")
            return 0
        
        # Check if target table exists
        if not db_handler.check_table_exists(target_table):
            logger(f"Target table {target_table} does not exist. Creating...", "WARNING")
            # The target table should exist, but we'll proceed
        
        # Query to get data from historical table
        with db_handler.engine.connect() as conn:
            # Get count of records to migrate
            count_query = text(f"""
                SELECT COUNT(*) 
                FROM {source_table}
                WHERE datetime <= :cutoff_datetime
                AND DATE(datetime) = :target_date
            """)
            
            result = conn.execute(count_query, {
                'cutoff_datetime': cutoff_datetime,
                'target_date': target_date.date()
            })
            record_count = result.fetchone()[0]
            
            if record_count == 0:
                logger(f"No records found to migrate from {source_table}", "WARNING")
                return 0
            
            logger(f"Found {record_count} records to migrate")
            
            # Read data from historical table using pandas
            read_query = f"""
                SELECT 
                    instrument_token,
                    tradingsymbol,
                    datetime,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM {source_table}
                WHERE datetime <= '{cutoff_datetime}'
                AND DATE(datetime) = '{target_date.date()}'
                ORDER BY instrument_token, datetime
            """
            
            df = pd.read_sql_query(read_query, db_handler.engine)
            
            if df.empty:
                logger(f"No data retrieved from {source_table}", "WARNING")
                return 0
            
            logger(f"Retrieved {len(df)} records from {source_table}")
            logger(f"Data date range: {df['datetime'].min()} to {df['datetime'].max()}")
            
            # Insert into target table with conflict handling
            try:
                with db_handler.engine.begin() as insert_conn:
                    if on_duplicate.lower() == 'replace':
                        logger(f"Using REPLACE mode for duplicates", "INFO")
                        # Use UPSERT: replace existing records
                        for _, row in df.iterrows():
                            insert_query = text(f"""
                                INSERT INTO {target_table} 
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
                            insert_conn.execute(insert_query, {
                                'token': int(row['instrument_token']),
                                'symbol': str(row['tradingsymbol']),
                                'dt': row['datetime'],
                                'o': float(row['open']),
                                'h': float(row['high']),
                                'l': float(row['low']),
                                'c': float(row['close']),
                                'v': float(row['volume'])
                            })
                    else:
                        logger(f"Using SKIP mode for duplicates", "INFO")
                        # Use INSERT with skip duplicates
                        for _, row in df.iterrows():
                            insert_query = text(f"""
                                INSERT INTO {target_table} 
                                (instrument_token, tradingsymbol, datetime, open, high, low, close, volume)
                                VALUES (:token, :symbol, :dt, :o, :h, :l, :c, :v)
                                ON CONFLICT (instrument_token, datetime) 
                                DO NOTHING
                            """)
                            insert_conn.execute(insert_query, {
                                'token': int(row['instrument_token']),
                                'symbol': str(row['tradingsymbol']),
                                'dt': row['datetime'],
                                'o': float(row['open']),
                                'h': float(row['high']),
                                'l': float(row['low']),
                                'c': float(row['close']),
                                'v': float(row['volume'])
                            })
                    
                logger(f"Successfully migrated {len(df)} records to {target_table}", "SUCCESS")
                return len(df)
                
            except Exception as e:
                logger(f"Error inserting data into {target_table}: {e}", "ERROR")
                return 0
                
    except ValueError as e:
        logger(f"Invalid date or time format: {e}", "ERROR")
        logger("Expected date format: YYYY-MM-DD (e.g., 2025-12-22)", "ERROR")
        logger("Expected time format: HH:MM:SS (e.g., 15:30:00)", "ERROR")
        return 0
    except Exception as e:
        logger(f"Error during migration: {e}", "ERROR")
        return 0


def migrate_all_intervals(
    db_handler: DatabaseHandler,
    date_str: str,
    time_str: str,
    intervals: list,
    logger=None,
    on_duplicate: str = 'skip'
) -> dict:
    """
    Migrate historical data for multiple intervals.
    
    Args:
        db_handler: Database handler instance
        date_str: Date in format YYYY-MM-DD
        time_str: Time in format HH:MM:SS
        intervals: List of intervals to migrate (e.g., [5, 15, 60])
        logger: Optional logging function
        on_duplicate: How to handle duplicates - 'skip' or 'replace' (default: 'skip')
        
    Returns:
        Dictionary with migration results per interval
    """
    if not logger:
        logger = print
    
    results = {}
    total_migrated = 0
    
    for interval in intervals:
        logger(f"\n{'='*60}")
        logger(f"Migrating {interval}-minute candles...")
        logger(f"{'='*60}")
        
        count = migrate_historical_to_live(db_handler, date_str, time_str, interval, logger, on_duplicate)
        results[interval] = count
        total_migrated += count
    
    logger(f"\n{'='*60}")
    logger("MIGRATION SUMMARY")
    logger(f"{'='*60}")
    for interval, count in results.items():
        logger(f"{interval}min: {count} records migrated")
    logger(f"Total: {total_migrated} records migrated")
    logger(f"{'='*60}\n")
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate historical candle data to live tables'
    )
    parser.add_argument(
        '--date',
        required=True,
        help='Date to migrate (format: YYYY-MM-DD, e.g., 2025-12-22)'
    )
    parser.add_argument(
        '--time',
        required=True,
        help='Cutoff time - migrate data before this time (format: HH:MM:SS, e.g., 15:30:00)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        help='Specific interval to migrate (5, 15, 60, etc.). If not specified, migrates all intervals (5, 15, 60)'
    )
    parser.add_argument(
        '--intervals',
        help='Comma-separated list of intervals (e.g., 5,15,60)'
    )
    parser.add_argument(
        '--on-duplicate',
        choices=['skip', 'replace'],
        default='skip',
        help='How to handle duplicate records: skip (default) or replace'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    def log_message(message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    try:
        # Load configuration
        config = Config()
        
        # Validate configuration
        errors = config.validate()
        if errors:
            for error in errors:
                log_message(f"Config error: {error}", "ERROR")
            return 1
        
        # Initialize database handler
        db_config = config.get_database_config()
        db_handler = DatabaseHandler(db_config['connection_string'], logger=log_message)
        
        # Test connection
        if not db_handler.test_connection():
            return 1
        
        # Determine intervals to migrate
        if args.interval:
            intervals = [args.interval]
        elif args.intervals:
            try:
                intervals = [int(x.strip()) for x in args.intervals.split(',')]
            except ValueError:
                log_message("Invalid intervals format. Use comma-separated numbers (e.g., 5,15,60)", "ERROR")
                return 1
        else:
            intervals = [5, 15, 60]  # Default intervals
        
        # Perform migration
        results = migrate_all_intervals(
            db_handler,
            args.date,
            args.time,
            intervals,
            logger=log_message,
            on_duplicate=args.on_duplicate
        )
        
        # Check if any migration succeeded
        total = sum(results.values())
        if total > 0:
            return 0
        else:
            return 1
            
    except Exception as e:
        log_message(f"Fatal error: {e}", "ERROR")
        return 1


if __name__ == '__main__':
    sys.exit(main())
