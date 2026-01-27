#!/usr/bin/env python3
"""
Script to aggregate 5-minute candles into 15-minute candles.

This script reads 5-minute candles from the database and creates 15-minute candles
by grouping every 3 consecutive 5-minute candles.

Usage:
    python aggregate_5min_to_15min.py [symbol] [--all]

Examples:
    # Aggregate for a specific symbol
    python aggregate_5min_to_15min.py RELIANCE
    
    # Aggregate for all symbols
    python aggregate_5min_to_15min.py --all
"""

import sys
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(__file__.parent.parent))

from core.database_handler import DatabaseHandler
from core.logger_setup import setup_logger
import pandas as pd


def get_5min_candles_for_symbol(
    db: DatabaseHandler,
    symbol: str,
    limit: int = 1000
) -> pd.DataFrame:
    """
    Fetch 5-minute candles for a symbol from database.
    
    Args:
        db: Database handler
        symbol: Trading symbol
        limit: Maximum number of candles to fetch
    
    Returns:
        DataFrame with 5-minute candles
    """
    try:
        from sqlalchemy import text
        query = text("""
            SELECT 
                datetime, 
                open, 
                high, 
                low, 
                close, 
                volume,
                instrument_token,
                tradingsymbol
            FROM live_candles_5min
            WHERE tradingsymbol = :symbol
            ORDER BY datetime ASC
            LIMIT :limit
        """)
        
        with db.engine.connect() as conn:
            result = conn.execute(query, {"symbol": symbol, "limit": limit})
            rows = result.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=[
            'datetime', 'open', 'high', 'low', 'close', 'volume', 'instrument_token', 'tradingsymbol'
        ])
        
        df['datetime'] = pd.to_datetime(df['datetime'])
        return df
    
    except Exception as e:
        db.logger(f"Error fetching 5-min candles for {symbol}: {e}", "ERROR")
        return pd.DataFrame()


def aggregate_5min_to_15min(
    db: DatabaseHandler,
    symbol: str,
    logger=None
) -> List[Dict[str, Any]]:
    """
    Aggregate 5-minute candles into 15-minute candles.
    
    Args:
        db: Database handler
        symbol: Trading symbol
        logger: Optional logger function
    
    Returns:
        List of aggregated 15-minute candles
    """
    if logger is None:
        logger = db.logger
    
    # Fetch 5-minute candles
    df_5min = get_5min_candles_for_symbol(db, symbol)
    
    if df_5min.empty:
        logger(f"No 5-minute candles found for {symbol}", "WARNING")
        return []
    
    logger(f"Fetched {len(df_5min)} 5-minute candles for {symbol}", "INFO")
    
    # Group candles by 15-minute periods
    aggregated_candles = []
    
    # Get the 15-minute period from the first candle
    first_datetime = df_5min.iloc[0]['datetime']
    minutes = (first_datetime.minute // 15) * 15
    current_15min_period = first_datetime.replace(minute=minutes, second=0, microsecond=0)
    
    current_group = []
    
    for idx, row in df_5min.iterrows():
        row_datetime = row['datetime']
        minutes = (row_datetime.minute // 15) * 15
        row_15min_period = row_datetime.replace(minute=minutes, second=0, microsecond=0)
        
        # If we've moved to a new 15-minute period
        if row_15min_period != current_15min_period:
            # Process the completed group
            if len(current_group) >= 3:
                # We have enough candles for a complete 15-minute candle
                # Take the first 3 candles
                agg_candle = aggregate_group(current_group[:3], symbol)
                aggregated_candles.append(agg_candle)
                logger(f"Aggregated 15-min candle for {symbol} at {current_15min_period}: "
                      f"O={agg_candle['open']:.2f}, H={agg_candle['high']:.2f}, "
                      f"L={agg_candle['low']:.2f}, C={agg_candle['close']:.2f}, "
                      f"V={agg_candle['volume']}", "DEBUG")
            
            # Start new period
            current_15min_period = row_15min_period
            current_group = [row]
        else:
            current_group.append(row)
    
    # Process the last group if it has enough candles
    if len(current_group) >= 3:
        agg_candle = aggregate_group(current_group[:3], symbol)
        aggregated_candles.append(agg_candle)
        logger(f"Aggregated 15-min candle for {symbol} at {current_15min_period}: "
              f"O={agg_candle['open']:.2f}, H={agg_candle['high']:.2f}, "
              f"L={agg_candle['low']:.2f}, C={agg_candle['close']:.2f}, "
              f"V={agg_candle['volume']}", "DEBUG")
    
    logger(f"Created {len(aggregated_candles)} 15-minute candles for {symbol}", "INFO")
    return aggregated_candles


def aggregate_group(group: List[Any], symbol: str) -> Dict[str, Any]:
    """
    Aggregate a group of 5-minute candles into a 15-minute candle.
    
    Args:
        group: List of row objects (first 3 should be used)
        symbol: Trading symbol
    
    Returns:
        Aggregated 15-minute candle dictionary
    """
    # Take first 3 candles
    candles_to_agg = group[:3]
    
    first_candle = candles_to_agg[0]
    first_datetime = first_candle['datetime']
    minutes = (first_datetime.minute // 15) * 15
    candle_15min_timestamp = first_datetime.replace(minute=minutes, second=0, microsecond=0)
    
    return {
        'datetime': candle_15min_timestamp,
        'symbol': symbol,
        'instrument_token': first_candle['instrument_token'],
        'open': float(candles_to_agg[0]['open']),
        'high': max(float(c['high']) for c in candles_to_agg),
        'low': min(float(c['low']) for c in candles_to_agg),
        'close': float(candles_to_agg[-1]['close']),
        'volume': sum(int(c['volume']) for c in candles_to_agg),
        'tick_count': 3,
        'source': 'aggregated'
    }


def save_15min_candles(
    db: DatabaseHandler,
    candles: List[Dict[str, Any]],
    logger=None
) -> int:
    """
    Save aggregated 15-minute candles to database.
    
    Args:
        db: Database handler
        candles: List of candles to save
        logger: Optional logger function
    
    Returns:
        Number of candles saved
    """
    if logger is None:
        logger = db.logger
    
    if not candles:
        logger("No candles to save", "WARNING")
        return 0
    
    # Convert dict candles to Candle objects for saving
    from core.candle_aggregator import Candle
    
    candle_objects = []
    for candle_dict in candles:
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
    
    # Save to database
    saved = db.save_candles(candle_objects, table_name='live_candles_15min', on_duplicate='update')
    logger(f"Saved {saved} 15-minute candles", "INFO")
    
    return saved


def get_all_symbols(db: DatabaseHandler) -> List[str]:
    """
    Get all unique symbols from 5-minute candles table.
    
    Args:
        db: Database handler
    
    Returns:
        List of unique symbols
    """
    try:
        from sqlalchemy import text
        query = text("""
            SELECT DISTINCT tradingsymbol
            FROM live_candles_5min
            ORDER BY tradingsymbol
        """)
        
        with db.engine.connect() as conn:
            result = conn.execute(query)
            symbols = [row[0] for row in result]
        
        return symbols
    
    except Exception as e:
        db.logger(f"Error fetching symbols: {e}", "ERROR")
        return []


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Aggregate 5-minute candles into 15-minute candles'
    )
    parser.add_argument('symbol', nargs='?', help='Trading symbol (e.g., RELIANCE)')
    parser.add_argument('--all', action='store_true', help='Aggregate for all symbols')
    
    args = parser.parse_args()
    
    # Setup logger
    logger = setup_logger('aggregate_5min_to_15min')
    
    # Connect to database
    try:
        db = DatabaseHandler(logger=logger)
        if not db.test_connection():
            logger("Database connection failed", "ERROR")
            sys.exit(1)
    except Exception as e:
        logger(f"Failed to initialize database: {e}", "ERROR")
        sys.exit(1)
    
    # Determine which symbols to process
    if args.all:
        symbols = get_all_symbols(db)
        if not symbols:
            logger("No symbols found in database", "WARNING")
            sys.exit(1)
        logger(f"Found {len(symbols)} symbols to process", "INFO")
    elif args.symbol:
        symbols = [args.symbol]
    else:
        parser.print_help()
        sys.exit(1)
    
    # Process each symbol
    total_candles_saved = 0
    
    for symbol in symbols:
        logger(f"\n=== Processing {symbol} ===", "INFO")
        
        # Aggregate 5-min to 15-min
        aggregated = aggregate_5min_to_15min(db, symbol, logger=logger)
        
        if aggregated:
            # Save to database
            saved = save_15min_candles(db, aggregated, logger=logger)
            total_candles_saved += saved
        else:
            logger(f"No 15-minute candles generated for {symbol}", "WARNING")
    
    logger(f"\n=== Summary ===", "INFO")
    logger(f"Total 15-minute candles saved: {total_candles_saved}", "INFO")
    
    db.close()


if __name__ == '__main__':
    main()
