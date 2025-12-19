"""
Candle aggregator for converting tick data to OHLC candles.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import threading


class Candle:
    """Represents an OHLC candle."""
    
    def __init__(self, symbol: str, interval: int, timestamp: datetime):
        self.symbol = symbol
        self.interval = interval  # in minutes
        self.timestamp = timestamp
        self.open: Optional[float] = None
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.close: Optional[float] = None
        self.volume: int = 0
        self.tick_count: int = 0
    
    def update(self, price: float, volume: int = 0):
        """Update candle with new tick data."""
        if self.open is None:
            self.open = price
        
        if self.high is None or price > self.high:
            self.high = price
        
        if self.low is None or price < self.low:
            self.low = price
        
        self.close = price
        self.volume += volume
        self.tick_count += 1
    
    def is_complete(self) -> bool:
        """Check if candle has all required data."""
        return all([
            self.open is not None,
            self.high is not None,
            self.low is not None,
            self.close is not None
        ])
    
    def to_dict(self) -> Dict:
        """Convert candle to dictionary."""
        return {
            'symbol': self.symbol,
            'datetime': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'tick_count': self.tick_count
        }


class CandleAggregator:
    """
    Aggregates tick data into OHLC candles.
    Supports multiple timeframes simultaneously.
    """
    
    def __init__(self, intervals: List[int], logger=None):
        """
        Initialize candle aggregator.
        
        Args:
            intervals: List of candle intervals in minutes (e.g., [1, 5, 15])
            logger: Optional logging function
        """
        self.intervals = sorted(intervals)
        self.logger = logger or self._default_logger
        
        # Active candles: {interval: {symbol: Candle}}
        self.active_candles: Dict[int, Dict[str, Candle]] = {
            interval: {} for interval in intervals
        }
        
        # Lock for thread safety
        self._lock = threading.Lock()
        
        # Completed candles callback
        self.on_candle_complete = None
    
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def _get_candle_timestamp(self, timestamp: datetime, interval: int) -> datetime:
        """
        Get the candle start timestamp for a given tick timestamp.
        
        Args:
            timestamp: Tick timestamp
            interval: Candle interval in minutes
            
        Returns:
            Candle start timestamp
        """
        minutes = (timestamp.minute // interval) * interval
        return timestamp.replace(minute=minutes, second=0, microsecond=0)
    
    def process_tick(self, symbol: str, price: float, timestamp: datetime, volume: int = 0):
        """
        Process a tick and update candles.
        
        Args:
            symbol: Trading symbol
            price: Tick price
            timestamp: Tick timestamp
            volume: Tick volume
        """
        with self._lock:
            completed_candles = []
            
            for interval in self.intervals:
                candle_ts = self._get_candle_timestamp(timestamp, interval)
                
                # Get or create active candle
                if symbol not in self.active_candles[interval]:
                    self.active_candles[interval][symbol] = Candle(symbol, interval, candle_ts)
                
                active_candle = self.active_candles[interval][symbol]
                
                # Check if we need to close current candle and start new one
                if active_candle.timestamp != candle_ts:
                    # Close current candle if complete
                    if active_candle.is_complete():
                        completed_candles.append(active_candle)
                    
                    # Start new candle
                    self.active_candles[interval][symbol] = Candle(symbol, interval, candle_ts)
                    active_candle = self.active_candles[interval][symbol]
                
                # Update candle with tick data
                active_candle.update(price, volume)
            
            # Notify about completed candles
            if completed_candles and self.on_candle_complete:
                try:
                    self.on_candle_complete(completed_candles)
                except Exception as e:
                    self.logger(f"Error in candle complete callback: {e}", "ERROR")
    
    def get_active_candles(self, interval: int, symbol: Optional[str] = None) -> List[Candle]:
        """
        Get active candles for an interval.
        
        Args:
            interval: Candle interval in minutes
            symbol: Optional symbol filter
            
        Returns:
            List of active candles
        """
        with self._lock:
            if interval not in self.active_candles:
                return []
            
            if symbol:
                candle = self.active_candles[interval].get(symbol)
                return [candle] if candle else []
            
            return list(self.active_candles[interval].values())
    
    def force_close_all(self) -> List[Candle]:
        """
        Force close all active candles (e.g., on shutdown).
        
        Returns:
            List of closed candles
        """
        with self._lock:
            closed_candles = []
            
            for interval in self.intervals:
                for symbol, candle in self.active_candles[interval].items():
                    if candle.is_complete():
                        closed_candles.append(candle)
                
                # Clear active candles
                self.active_candles[interval].clear()
            
            return closed_candles
    
    def get_statistics(self) -> Dict:
        """Get aggregator statistics."""
        with self._lock:
            stats = {
                'intervals': self.intervals,
                'active_candles_count': {}
            }
            
            for interval in self.intervals:
                stats['active_candles_count'][f'{interval}min'] = len(self.active_candles[interval])
            
            return stats
