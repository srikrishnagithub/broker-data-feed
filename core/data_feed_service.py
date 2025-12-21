"""
Main data feed service that coordinates broker connection, tick processing,
candle aggregation, and database storage.
"""
import time
import signal
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.base_broker import BaseBroker, TickData
from core.candle_aggregator import CandleAggregator, Candle
from core.database_handler import DatabaseHandler


class DataFeedService:
    """
    Main data feed service coordinating all components.
    """
    
    def __init__(
        self,
        broker: BaseBroker,
        database: DatabaseHandler,
        candle_intervals: List[int],
        mqtt_publisher=None,
        logger=None
    ):
        """
        Initialize data feed service.
        
        Args:
            broker: Broker implementation instance
            database: Database handler instance
            candle_intervals: List of candle intervals in minutes
            mqtt_publisher: Optional MQTT publisher for heartbeats
            logger: Optional logging function
        """
        self.broker = broker
        self.database = database
        self.mqtt_publisher = mqtt_publisher
        self.logger = logger or self._default_logger
        
        # Initialize candle aggregator
        self.aggregator = CandleAggregator(candle_intervals, logger=self.logger)
        self.aggregator.on_candle_complete = self._on_candle_complete # pyright: ignore[reportAttributeAccessIssue]
        
        # Symbol to instrument token mapping
        self._symbol_to_token: Dict[str, int] = {}
        
        # Statistics
        self.tick_count = 0
        self.candle_count = 0
        self.last_tick_time: Optional[datetime] = None
        self._stats_lock = threading.Lock()
        
        # Shutdown flag
        self.shutdown_event = threading.Event()
        
        # Heartbeat thread
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_interval = 30  # seconds (market hours)
        self._off_market_heartbeat_interval = 300  # 5 minutes (off-market hours)
        
        self.logger("Data feed service initialized", "SUCCESS")
    
    def _is_market_hours(self) -> bool:
        """
        Check if current time is within market hours.
        
        NSE market hours: Monday-Friday, 9:15 AM - 3:30 PM IST
        
        Returns:
            True if market is open, False otherwise
        """
        now = datetime.now()
        
        # Check if it's a weekday (Monday = 0, Sunday = 6)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check time: 9:15 AM to 3:30 PM IST
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        return market_open <= now <= market_close
    
    def _get_current_heartbeat_interval(self) -> int:
        """
        Get the appropriate heartbeat interval based on market hours.
        
        Returns:
            Heartbeat interval in seconds
        """
        return self._heartbeat_interval if self._is_market_hours() else self._off_market_heartbeat_interval
    
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def _on_tick_received(self, ticks: List[TickData]):
        """
        Callback when ticks are received from broker.
        
        Args:
            ticks: List of tick data
        """
        try:
            with self._stats_lock:
                self.tick_count += len(ticks)
                self.last_tick_time = datetime.now()
            
            # Process each tick
            for tick in ticks:
                # Skip ticks with zero volume and generate warning
                if tick.volume == 0:
                    self.logger(
                        f"Skipping zero-volume tick for {tick.symbol} at {tick.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(price: {tick.last_price:.2f}, market_hours: {self._is_market_hours()})",
                        "WARNING"
                    )
                    continue
                
                self.aggregator.process_tick(
                    symbol=tick.symbol,
                    price=tick.last_price,
                    timestamp=tick.timestamp,
                    volume=tick.volume
                )
            
            # Log every 100 ticks
            if self.tick_count % 100 == 0:
                self.logger(f"Processed {self.tick_count} ticks", "INFO")
                
        except Exception as e:
            self.logger(f"Error processing ticks: {e}", "ERROR")
    
    def _on_candle_complete(self, candles: List[Candle]):
        """
        Callback when candles are completed.
        
        Args:
            candles: List of completed candles
        """
        try:
            # Filter out zero-volume candles
            valid_candles = []
            for candle in candles:
                if candle.volume == 0:
                    self.logger(
                        f"Skipping zero-volume candle {candle.interval}min {candle.symbol} at {candle.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(O={candle.open:.2f} H={candle.high:.2f} L={candle.low:.2f} C={candle.close:.2f}, market_hours: {self._is_market_hours()})",
                        "WARNING"
                    )
                else:
                    valid_candles.append(candle)
            
            # Only save valid candles
            if valid_candles:
                saved_count = self.database.save_candles(valid_candles)
                
                with self._stats_lock:
                    self.candle_count += saved_count
                
                # Log candle completion
                for candle in valid_candles:
                    self.logger(
                        f"Candle {candle.interval}min {candle.symbol}: "
                        f"O={candle.open:.2f} H={candle.high:.2f} L={candle.low:.2f} C={candle.close:.2f} "
                        f"V={candle.volume} ({candle.tick_count} ticks)",
                        "INFO"
                    )
                
        except Exception as e:
            self.logger(f"Error saving candles: {e}", "ERROR")
    
    def _heartbeat_loop(self):
        """Background heartbeat loop."""
        self.logger(f"Heartbeat started (market hours: {self._heartbeat_interval}s, off-market: {self._off_market_heartbeat_interval}s)", "INFO")
        
        while not self.shutdown_event.is_set():
            try:
                # Get current heartbeat interval based on market hours
                current_interval = self._get_current_heartbeat_interval()
                
                # Wait for heartbeat interval or shutdown
                if self.shutdown_event.wait(timeout=current_interval):
                    break
                
                # Get market status for logging
                market_open = self._is_market_hours()
                market_status = "market hours" if market_open else "off-market hours"
                
                # Get statistics
                with self._stats_lock:
                    stats = {
                        'tick_count': self.tick_count,
                        'candle_count': self.candle_count,
                        'last_tick_time': self.last_tick_time.isoformat() if self.last_tick_time else None,
                        'market_hours': market_open
                    }
                
                # Add aggregator statistics
                stats.update(self.aggregator.get_statistics())
                
                # Log heartbeat
                time_since_tick = ""
                if self.last_tick_time:
                    elapsed = (datetime.now() - self.last_tick_time).total_seconds()
                    
                    # Format elapsed time in a human-readable way
                    if elapsed < 60:
                        time_since_tick = f", last tick {elapsed:.1f}s ago"
                    elif elapsed < 3600:  # Less than 1 hour
                        minutes = int(elapsed // 60)
                        seconds = int(elapsed % 60)
                        time_since_tick = f", last tick {minutes}m {seconds}s ago"
                    else:  # 1 hour or more
                        hours = int(elapsed // 3600)
                        minutes = int((elapsed % 3600) // 60)
                        time_since_tick = f", last tick {hours}h {minutes}m ago"
                
                self.logger(
                    f"[HEARTBEAT] Ticks: {stats['tick_count']}, "
                    f"Candles: {stats['candle_count']}"
                    f"{time_since_tick} ({market_status})",
                    "INFO"
                )
                
                # Publish to MQTT if available (more frequent during market hours)
                if self.mqtt_publisher and self.mqtt_publisher.is_connected():
                    # During market hours, publish every heartbeat
                    # During off-market hours, only publish every 10 minutes (every 2 heartbeats)
                    should_publish = market_open or (current_interval >= 300 and (int(datetime.now().timestamp()) // 600) % 2 == 0)
                    
                    if should_publish:
                        heartbeat_data = {
                            'timestamp': datetime.now().isoformat(),
                            'service': 'broker_data_feed',
                            'status': 'active',
                            'broker': self.broker.get_broker_name(),
                            'market_hours': market_open,
                            'statistics': stats
                        }
                        self.mqtt_publisher.publish('heartbeat/data_feed', heartbeat_data, qos=1)
                    
            except Exception as e:
                self.logger(f"Error in heartbeat loop: {e}", "ERROR")
        
        self.logger("Heartbeat stopped", "INFO")
    
    def start(self, instruments: List[int], symbols: List[str]):
        """
        Start the data feed service.
        
        Args:
            instruments: List of instrument tokens to subscribe
            symbols: List of symbol names (for mapping)
        """
        try:
            self.logger("Starting data feed service...", "INFO")
            
            # Test database connection
            self.logger("Testing database connection...", "INFO")
            if not self.database.test_connection():
                raise RuntimeError("Database connection test failed")
            
            # Create symbol to instrument token mapping
            self._symbol_to_token = dict(zip(symbols, instruments))
            
            # Initialize candle aggregator with instrument tokens
            self.aggregator.set_instrument_tokens(self._symbol_to_token)
            
            # Check if target table exists
            if not self.database.check_table_exists('live_candles_5min'):
                self.logger("Warning: live_candles_5min table does not exist", "WARNING")
            
            # Set tick callback
            self.broker.set_tick_callback(self._on_tick_received)
            
            # Connect to broker
            self.logger(f"Connecting to {self.broker.get_broker_name()}...", "INFO")
            
            if not self.broker.connect():
                raise RuntimeError("Broker connection failed")
            
            # Subscribe to instruments
            self.logger(f"Subscribing to {len(instruments)} instruments...", "INFO")
            self.broker.subscribe(instruments)
            
            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name="heartbeat"
            )
            self._heartbeat_thread.start()
            
            # Log market status
            market_status = "market hours" if self._is_market_hours() else "off-market hours"
            self.logger(f"Service started successfully during {market_status}", "SUCCESS")
            
            # Wait for shutdown signal
            while not self.shutdown_event.is_set():
                time.sleep(1)
                
        except RuntimeError as e:
            self.logger(f"Service startup failed: {e}", "ERROR")
            raise  # Re-raise to be caught by main
            
        except Exception as e:
            self.logger(f"An unexpected error occurred: {e}", "ERROR")
            raise RuntimeError(f"Unexpected error: {e}") from e
        
        finally:
            self.logger("Service shutting down...", "INFO")

    def stop(self):
        """Stop the data feed service."""
        try:
            self.logger("Stopping data feed service...", "INFO")
            
            # Set shutdown event
            self.shutdown_event.set()
            
            # Wait for heartbeat thread
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                self._heartbeat_thread.join(timeout=2)
            
            # Disconnect from broker
            self.broker.disconnect()
            
            # Force close any remaining candles
            remaining_candles = self.aggregator.force_close_all()
            if remaining_candles:
                self.logger(f"Saving {len(remaining_candles)} remaining candles...", "INFO")
                self.database.save_candles(remaining_candles)
            
            # Close database connection
            self.database.close()
            
            # Final statistics
            self.logger(
                f"Final statistics - Ticks: {self.tick_count}, Candles: {self.candle_count}",
                "INFO"
            )
            
            self.logger("Data feed service stopped", "INFO")
            
        except Exception as e:
            self.logger(f"Error during shutdown: {e}", "ERROR")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get service statistics."""
        with self._stats_lock:
            stats = {
                'tick_count': self.tick_count,
                'candle_count': self.candle_count,
                'last_tick_time': self.last_tick_time.isoformat() if self.last_tick_time else None,
                'broker': self.broker.get_broker_name(),
                'broker_connected': self.broker.is_connected()
            }
        
        # Add aggregator stats
        stats.update(self.aggregator.get_statistics())
        
        return stats
