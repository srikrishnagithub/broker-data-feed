"""
Hourly candle builder for forming incomplete hourly candles from 15-minute data.

Provides functionality to build "forming" hourly candles by aggregating 15-minute
candles from the current incomplete hour, enabling real-time hourly EMA calculations
for signal generation without waiting for the hour to complete.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd


def build_forming_hourly_candle(
    symbol: str,
    current_datetime: datetime,
    candles_15min: pd.DataFrame,
    instrument_token: Optional[int] = None,
    logger=None
) -> Optional[Dict[str, Any]]:
    """
    Build a forming hourly candle from 15-minute candles in the current hour.
    
    Aggregates all available 15-minute candles from the current hour into a single
    hourly candle with OHLCV data. This allows calculation of hourly EMAs without
    waiting for the hour to complete.
    
    Args:
        symbol: Trading symbol (e.g., 'RELIANCE')
        current_datetime: Current time when signal is being evaluated
        candles_15min: DataFrame of 15-minute candles with columns:
                      [datetime, open, high, low, close, volume]
        instrument_token: Optional instrument token for the symbol
        logger: Optional logging function
        
    Returns:
        Dictionary representing a single hourly candle with keys:
        {
            'datetime': datetime object for hour start (e.g., 13:00:00)
            'symbol': Trading symbol
            'instrument_token': Instrument token
            'open': Open price (from first 15-min candle)
            'high': Maximum high price
            'low': Minimum low price
            'close': Close price (from last 15-min candle)
            'volume': Sum of all volumes
            'source': 'forming' to indicate this is not a completed candle
            'tick_count': Number of 15-min candles aggregated
        }
        
        Returns None if:
        - No 15-minute candles exist in the current hour
        - Input DataFrame is empty
        - Current hour has no valid candle data
    """
    if logger is None:
        logger = _default_logger
    
    # Get current hour boundaries (e.g., 13:00:00 - 13:59:59)
    hour_start = current_datetime.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1) - timedelta(seconds=1)
    
    # Filter 15-min candles for current hour
    if candles_15min.empty:
        logger(f"No 15-minute candles available for {symbol}", "WARNING")
        return None
    
    # Create mask for current hour
    # Handle both datetime and pandas Timestamp
    if not isinstance(candles_15min.index, pd.DatetimeIndex):
        # If datetime is in a column, use it
        if 'datetime' in candles_15min.columns:
            df_to_filter = candles_15min.copy()
            df_to_filter['datetime_obj'] = pd.to_datetime(df_to_filter['datetime'])
        else:
            logger(f"No datetime column found in 15-min candles for {symbol}", "ERROR")
            return None
    else:
        # If datetime is the index
        df_to_filter = candles_15min.copy()
        df_to_filter['datetime_obj'] = df_to_filter.index
    
    # Filter for current hour
    hour_candles = df_to_filter[
        (df_to_filter['datetime_obj'] >= hour_start) & 
        (df_to_filter['datetime_obj'] <= hour_end)
    ]
    
    if hour_candles.empty:
        logger(
            f"No 15-minute candles found in current hour [{hour_start.strftime('%H:%M')} - {hour_end.strftime('%H:%M')}] for {symbol}",
            "INFO"
        )
        return None
    
    # Sort by datetime to ensure proper order
    hour_candles = hour_candles.sort_values('datetime_obj')
    
    try:
        # Extract OHLCV values - handle both column names and variations
        if 'open' in hour_candles.columns:
            open_prices = hour_candles['open']
        else:
            open_prices = hour_candles.iloc[:, 0]
            
        if 'high' in hour_candles.columns:
            high_prices = hour_candles['high']
        else:
            high_prices = hour_candles.iloc[:, 2]
            
        if 'low' in hour_candles.columns:
            low_prices = hour_candles['low']
        else:
            low_prices = hour_candles.iloc[:, 3]
            
        if 'close' in hour_candles.columns:
            close_prices = hour_candles['close']
        else:
            close_prices = hour_candles.iloc[:, 4]
            
        if 'volume' in hour_candles.columns:
            volumes = hour_candles['volume']
        else:
            volumes = hour_candles.iloc[:, 5]
        
        # Build forming hourly candle
        forming_candle = {
            'datetime': hour_start,
            'symbol': symbol,
            'instrument_token': instrument_token,
            'open': float(open_prices.iloc[0]),  # First 15-min candle open
            'high': float(high_prices.max()),    # Highest high
            'low': float(low_prices.min()),      # Lowest low
            'close': float(close_prices.iloc[-1]),  # Last 15-min candle close
            'volume': int(volumes.sum()),        # Sum of volumes
            'source': 'forming',                 # Mark as forming candle
            'tick_count': len(hour_candles)      # Number of 15-min candles aggregated
        }
        
        logger(
            f"Built forming hourly candle for {symbol} @ {hour_start.strftime('%Y-%m-%d %H:%M')}: "
            f"O={forming_candle['open']:.2f} H={forming_candle['high']:.2f} "
            f"L={forming_candle['low']:.2f} C={forming_candle['close']:.2f} "
            f"V={forming_candle['volume']} (from {forming_candle['tick_count']} x 15min)",
            "INFO"
        )
        
        return forming_candle
        
    except Exception as e:
        logger(
            f"Error building forming hourly candle for {symbol}: {e}",
            "ERROR"
        )
        return None


def append_forming_hourly_candle(
    hourly_df: pd.DataFrame,
    forming_candle: Dict[str, Any],
    logger=None
) -> pd.DataFrame:
    """
    Append a forming hourly candle to completed hourly candles DataFrame.
    
    Ensures the forming candle is added at the end so that hourly EMAs
    include the most recent forming data.
    
    Args:
        hourly_df: DataFrame of completed hourly candles
        forming_candle: Dictionary with forming candle data from build_forming_hourly_candle()
        logger: Optional logging function
        
    Returns:
        Updated DataFrame with forming candle appended
    """
    if logger is None:
        logger = _default_logger
    
    if forming_candle is None:
        return hourly_df
    
    try:
        # Convert forming candle dict to DataFrame
        forming_df = pd.DataFrame([forming_candle])
        
        # Append to existing hourly candles
        result_df = pd.concat([hourly_df, forming_df], ignore_index=True)
        
        logger(
            f"Appended forming candle at {forming_candle['datetime']} for {forming_candle['symbol']}",
            "DEBUG"
        )
        
        return result_df
        
    except Exception as e:
        logger(f"Error appending forming candle: {e}", "ERROR")
        return hourly_df


def is_in_incomplete_hour(current_datetime: datetime) -> bool:
    """
    Check if current time is in an incomplete hour (minute != 0).
    
    Args:
        current_datetime: Current datetime to check
        
    Returns:
        True if minute != 0 (incomplete hour), False otherwise
    """
    return current_datetime.minute != 0


def get_current_hour_start(current_datetime: datetime) -> datetime:
    """
    Get the start time of the current hour.
    
    Args:
        current_datetime: Current datetime
        
    Returns:
        datetime object with minute, second, microsecond set to 0
    """
    return current_datetime.replace(minute=0, second=0, microsecond=0)


def get_current_hour_end(current_datetime: datetime) -> datetime:
    """
    Get the end time of the current hour.
    
    Args:
        current_datetime: Current datetime
        
    Returns:
        datetime object for the last second of the hour
    """
    hour_start = current_datetime.replace(minute=0, second=0, microsecond=0)
    return hour_start + timedelta(hours=1) - timedelta(seconds=1)


def log_forming_candle_usage(
    symbol: str,
    forming_candle: Dict[str, Any],
    hourly_ema20: Optional[float],
    hourly_ema50: Optional[float],
    logger=None
):
    """
    Log when a forming candle is used for hourly EMA calculation.
    
    Args:
        symbol: Trading symbol
        forming_candle: Dictionary with forming candle data
        hourly_ema20: Calculated EMA20 value
        hourly_ema50: Calculated EMA50 value
        logger: Optional logging function
    """
    if logger is None:
        logger = _default_logger
    
    hour_str = forming_candle['datetime'].strftime('%Y-%m-%d %H:%M')
    tick_count = forming_candle['tick_count']
    
    logger(
        f"Using forming hourly candle for {symbol} [{hour_str}] "
        f"aggregated from {tick_count} x 15-min candles",
        "INFO"
    )
    
    logger(
        f"  Forming candle OHLC: O={forming_candle['open']:.4f} "
        f"H={forming_candle['high']:.4f} L={forming_candle['low']:.4f} "
        f"C={forming_candle['close']:.4f} V={forming_candle['volume']}",
        "DEBUG"
    )
    
    if hourly_ema20 is not None and hourly_ema50 is not None:
        logger(
            f"  Hourly EMAs (with forming data): EMA20={hourly_ema20:.4f}, EMA50={hourly_ema50:.4f}",
            "INFO"
        )


def _default_logger(message: str, level: str = "INFO"):
    """Default logger that prints to console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")
