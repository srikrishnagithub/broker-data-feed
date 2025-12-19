"""
Main data feed service that coordinates broker connection, tick processing,
candle aggregation, and database storage.
"""
import time
import signal
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

from broker_data_feed.core.base_broker import BaseBroker, TickData
from broker_data_feed.core.candle_aggregator import CandleAggregator, Candle
from broker_data_feed.core.database_handler import DatabaseHandler


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
        self.aggregator.on_candle_complete = self._on_candle_complete
        
        # Statistics
        self.tick_count = 0
        self.candle_count = 0
        self.last_tick_time: Optional[datetime] = None
        self._stats_lock = threading.Lock()
        
        # Shutdown flag
        self.shutdown_event = threading.Event()
        
        # Heartbeat thread
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_interval = 30  # seconds
        
        self.logger("Data feed service initialized", "SUCCESS")
    
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
            # Save to database
            saved_count = self.database.save_candles(candles)
            
            with self._stats_lock:
                self.candle_count += saved_count
            
            # Log candle completion
            for candle in candles:
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
        self.logger(f"Heartbeat started (interval: {self._heartbeat_interval}s)", "INFO")
        
        while not self.shutdown_event.is_set():
            try:
                # Wait for heartbeat interval or shutdown
                if self.shutdown_event.wait(timeout=self._heartbeat_interval):
                    break
                
                # Get statistics
                with self._stats_lock:
                    stats = {
                        'tick_count': self.tick_count,
                        'candle_count': self.candle_count,
                        'last_tick_time': self.last_tick_time.isoformat() if self.last_tick_time else None
                    }
                
                # Add aggregator statistics
                stats.update(self.aggregator.get_statistics())
                
                # Log heartbeat
                time_since_tick = ""
                if self.last_tick_time:
                    elapsed = (datetime.now() - self.last_tick_time).total_seconds()
                    time_since_tick = f", last tick {elapsed:.1f}s ago"
                
                self.logger(
                    f"[HEARTBEAT] Ticks: {stats['tick_count']}, "
                    f"Candles: {stats['candle_count']}"
                    f"{time_since_tick}",
                    "INFO"
                )
                
                # Publish to MQTT if available
                if self.mqtt_publisher and self.mqtt_publisher.is_connected():
                    heartbeat_data = {
                        'timestamp': datetime.now().isoformat(),
                        'service': 'broker_data_feed',
                        'status': 'active',
                        'broker': self.broker.get_broker_name(),
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
            
            # Check if target table exists
            if not self.database.check_table_exists('merged_candles_5min'):
                self.logger("Warning: merged_candles_5min table does not exist", "WARNING")
            
            # Set tick callback
            self.broker.set_tick_callback(self._on_tick_received)
            
            # Connect to broker
            self.logger(f"Connecting to {self.broker.get_broker_name()}...", "INFO")
            if not self.broker.connect():
                raise RuntimeError("Failed to connect to broker")
            
            # Subscribe to instruments
            self.logger(f"Subscribing to {len(instruments)} instruments...", "INFO")
            if not self.broker.subscribe(instruments):
                raise RuntimeError("Failed to subscribe to instruments")
            
            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name="heartbeat"
            )
            self._heartbeat_thread.start()
            
            self.logger("Data feed service started successfully", "SUCCESS")
            self.logger("Press Ctrl+C to stop", "INFO")
            
            # Keep service running
            while not self.shutdown_event.is_set():
                self.shutdown_event.wait(timeout=1)
                
        except KeyboardInterrupt:
            self.logger("Keyboard interrupt received", "INFO")
        except Exception as e:
            self.logger(f"Error in data feed service: {e}", "ERROR")
            raise
        finally:
            self.stop()
    
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
