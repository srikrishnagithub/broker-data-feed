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
        self._off_market_heartbeat_interval = 600  # 10 minutes (off-market hours)
        
        self.logger("Data feed service initialized", "SUCCESS")
    
    def _is_market_hours(self) -> bool:
        """
        Check if current time is within market hours.
        
        NSE market hours: Monday-Friday, 9:10 AM - 3:45 PM IST
        
        Returns:
            True if market is open, False otherwise
        """
        now = datetime.now()
        
        # Check if it's a weekday (Monday = 0, Sunday = 6)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check time: 9:10 AM to 3:45 PM IST
        market_open = now.replace(hour=9, minute=10, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=45, second=0, microsecond=0)
        
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
            self.logger(f"_on_candle_complete called with {len(candles)} candles", "DEBUG")
            
            # Check if we're in market hours before saving
            if not self._is_market_hours():
                self.logger(f"Off-market hours: Skipping save for {len(candles)} candles", "INFO")
                return
            
            # Process candles without volume filtering
            valid_candles = list(candles)

            # Only save valid candles
            if valid_candles:
                # Group candles by interval and save to respective tables
                candles_by_interval = {}
                for candle in valid_candles:
                    interval = candle.interval
                    if interval not in candles_by_interval:
                        candles_by_interval[interval] = []
                    candles_by_interval[interval].append(candle)

                # Save candles to their respective tables
                for interval, candles_list in candles_by_interval.items():
                    table_name = f'live_candles_{interval}min'
                    self.logger(f"Saving {len(candles_list)} candles to {table_name}", "DEBUG")
                    saved_count = self.database.save_candles(candles_list, table_name)
                    self.logger(f"Saved {saved_count} candles to {table_name}", "DEBUG")
                    with self._stats_lock:
                        self.candle_count += saved_count
                
                # Real-time aggregation: 5-min -> 15-min -> 60-min
                self._aggregate_candles_realtime(valid_candles)
            else:
                self.logger(f"No valid candles to save", "DEBUG")

        except Exception as e:
            self.logger(f"Error saving candles: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
    
    def _aggregate_candles_realtime(self, completed_candles: List[Candle]):
        """
        Aggregate completed candles into higher timeframes in real-time.
        
        When 5-minute candles complete, check if we can form 15-minute candles.
        When 15-minute candles complete, check if we can form 60-minute candles.
        
        Args:
            completed_candles: List of completed candles
        """
        try:
            # Extract 5-minute candles
            candles_5min = [c for c in completed_candles if c.interval == 5]
            
            if not candles_5min:
                return
            
            # Aggregate 5-min to 15-min
            self._try_create_15min_candles(candles_5min)
            
            # Aggregate 15-min to 60-min (if 15-min candles were just completed)
            candles_15min = [c for c in completed_candles if c.interval == 15]
            if candles_15min:
                self._try_create_60min_candles(candles_15min)
        
        except Exception as e:
            self.logger(f"Error in real-time aggregation: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "ERROR")
    
    def _try_create_15min_candles(self, candles_5min: List[Candle]):
        """
        Try to create 15-minute candles from completed 5-minute candles.
        
        For each symbol in the completed 5-min candles, check if we now have
        3 consecutive 5-min candles that can form a 15-min candle.
        
        Args:
            candles_5min: List of completed 5-minute candles
        """
        try:
            # Group by symbol
            symbols_to_check = set(c.symbol for c in candles_5min)
            
            for symbol in symbols_to_check:
                try:
                    # Get last 6 5-minute candles for this symbol
                    import pandas as pd
                    from sqlalchemy import text
                    
                    query = text("""
                        SELECT 
                            datetime, open, high, low, close, volume, instrument_token
                        FROM live_candles_5min
                        WHERE tradingsymbol = :symbol
                        ORDER BY datetime DESC
                        LIMIT 6
                    """)
                    
                    with self.database.engine.connect() as conn:
                        result = conn.execute(query, {"symbol": symbol}).fetchall()
                    
                    if not result or len(result) < 3:
                        continue
                    
                    # Reverse to get chronological order
                    candles = list(reversed(result))
                    
                    # Get existing 15-min candles for this symbol
                    query_15min = text("""
                        SELECT datetime
                        FROM live_candles_15min
                        WHERE tradingsymbol = :symbol
                        ORDER BY datetime DESC
                        LIMIT 6
                    """)
                    
                    with self.database.engine.connect() as conn:
                        result_15min = conn.execute(query_15min, {"symbol": symbol}).fetchall()
                    
                    existing_15min_datetimes = set(pd.to_datetime([r[0] for r in result_15min])) if result_15min else set()
                    
                    # Try to form 15-minute candles from groups of 3 consecutive 5-min candles
                    for i in range(len(candles) - 2):
                        group = candles[i:i+3]
                        
                        # Calculate expected 15-min timestamp
                        first_datetime = pd.to_datetime(group[0][0])
                        minutes = (first_datetime.minute // 15) * 15
                        ts_15min = first_datetime.replace(minute=minutes, second=0, microsecond=0)
                        
                        # Check if this 15-min candle already exists
                        if ts_15min in existing_15min_datetimes:
                            continue
                        
                        # Create aggregated 15-min candle
                        agg_candle = Candle(
                            symbol=symbol,
                            interval=15,
                            timestamp=ts_15min,
                            instrument_token=int(group[0][6])
                        )
                        agg_candle.open = float(group[0][1])
                        agg_candle.high = max(float(c[2]) for c in group)
                        agg_candle.low = min(float(c[3]) for c in group)
                        agg_candle.close = float(group[-1][4])
                        agg_candle.volume = sum(int(c[5]) for c in group)
                        agg_candle.tick_count = 3
                        
                        # Save the aggregated candle
                        saved = self.database.save_candles([agg_candle], 'live_candles_15min', on_duplicate='update')
                        if saved > 0:
                            self.logger(f"[REAL-TIME] Created 15-min candle for {symbol} at {ts_15min}", "INFO")
                            with self._stats_lock:
                                self.candle_count += saved
                
                except Exception as e:
                    self.logger(f"Error creating 15-min candles for {symbol}: {e}", "DEBUG")
        
        except Exception as e:
            self.logger(f"Error in _try_create_15min_candles: {e}", "ERROR")
    
    def _try_create_60min_candles(self, candles_15min: List[Candle]):
        """
        Try to create 60-minute candles from completed 15-minute candles.
        
        For each symbol in the completed 15-min candles, check if we now have
        4 consecutive 15-min candles that can form a 60-min candle.
        
        Args:
            candles_15min: List of completed 15-minute candles
        """
        try:
            # Group by symbol
            symbols_to_check = set(c.symbol for c in candles_15min)
            
            for symbol in symbols_to_check:
                try:
                    # Get last 8 15-minute candles for this symbol
                    import pandas as pd
                    from sqlalchemy import text
                    
                    query = text("""
                        SELECT 
                            datetime, open, high, low, close, volume, instrument_token
                        FROM live_candles_15min
                        WHERE tradingsymbol = :symbol
                        ORDER BY datetime DESC
                        LIMIT 8
                    """)
                    
                    with self.database.engine.connect() as conn:
                        result = conn.execute(query, {"symbol": symbol}).fetchall()
                    
                    if not result or len(result) < 4:
                        continue
                    
                    # Reverse to get chronological order
                    candles = list(reversed(result))
                    
                    # Get existing 60-min candles for this symbol
                    query_60min = text("""
                        SELECT datetime
                        FROM live_candles_60min
                        WHERE tradingsymbol = :symbol
                        ORDER BY datetime DESC
                        LIMIT 6
                    """)
                    
                    with self.database.engine.connect() as conn:
                        result_60min = conn.execute(query_60min, {"symbol": symbol}).fetchall()
                    
                    existing_60min_datetimes = set(pd.to_datetime([r[0] for r in result_60min])) if result_60min else set()
                    
                    # Try to form 60-minute candles from groups of 4 consecutive 15-min candles
                    for i in range(len(candles) - 3):
                        group = candles[i:i+4]
                        
                        # Calculate expected 60-min timestamp
                        first_datetime = pd.to_datetime(group[0][0])
                        ts_60min = first_datetime.replace(minute=0, second=0, microsecond=0)
                        
                        # Check if this 60-min candle already exists
                        if ts_60min in existing_60min_datetimes:
                            continue
                        
                        # Create aggregated 60-min candle
                        agg_candle = Candle(
                            symbol=symbol,
                            interval=60,
                            timestamp=ts_60min,
                            instrument_token=int(group[0][6])
                        )
                        agg_candle.open = float(group[0][1])
                        agg_candle.high = max(float(c[2]) for c in group)
                        agg_candle.low = min(float(c[3]) for c in group)
                        agg_candle.close = float(group[-1][4])
                        agg_candle.volume = sum(int(c[5]) for c in group)
                        agg_candle.tick_count = 4
                        
                        # Save the aggregated candle
                        saved = self.database.save_candles([agg_candle], 'live_candles_60min', on_duplicate='update')
                        if saved > 0:
                            self.logger(f"[REAL-TIME] Created 60-min candle for {symbol} at {ts_60min}", "INFO")
                            with self._stats_lock:
                                self.candle_count += saved
                
                except Exception as e:
                    self.logger(f"Error creating 60-min candles for {symbol}: {e}", "DEBUG")
        
        except Exception as e:
            self.logger(f"Error in _try_create_60min_candles: {e}", "ERROR")
    
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
                    f"Candles saved: {stats['candle_count']}"
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
    
    def _polling_loop(self):
        """
        Polling loop for REST API brokers (e.g., KOTAK NEO).
        Polls quotes every 30 seconds synchronized to clock (at :05 and :35 seconds).
        """
        self.logger("REST API polling loop started", "INFO")
        
        poll_interval = 30  # Poll every 30 seconds
        offset_seconds = 5  # Poll at :05 and :35 seconds
        
        while not self.shutdown_event.is_set():
            try:
                # Calculate time to next poll interval aligned to clock
                now = datetime.now()
                current_second = now.second
                current_microsecond = now.microsecond
                
                # Find next poll time (either :05 or :35 seconds)
                if current_second < offset_seconds:
                    # Wait until :05 seconds
                    wait_seconds = offset_seconds - current_second - (current_microsecond / 1000000.0)
                elif current_second < offset_seconds + poll_interval:
                    # Wait until :35 seconds
                    wait_seconds = (offset_seconds + poll_interval) - current_second - (current_microsecond / 1000000.0)
                else:
                    # Wait until next minute :05 seconds
                    wait_seconds = (60 - current_second) + offset_seconds - (current_microsecond / 1000000.0)
                
                # Ensure we don't wait negative time
                if wait_seconds < 0:
                    wait_seconds = 0
                
                # Wait until next poll time
                if self.shutdown_event.wait(wait_seconds):
                    break  # Shutdown requested
                
                # Poll quotes from broker
                if hasattr(self.broker, 'poll_quotes'):
                    self.broker.poll_quotes()
                
            except Exception as e:
                self.logger(f"Error in polling loop: {e}", "ERROR")
                # Wait a bit before retrying
                self.shutdown_event.wait(5)
        
        self.logger("REST API polling stopped", "INFO")
    
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
            
            # Check if broker needs polling (REST API mode)
            if hasattr(self.broker, 'poll_quotes'):
                self.logger("Starting REST API polling thread...", "INFO")
                self._polling_thread = threading.Thread(
                    target=self._polling_loop,
                    daemon=True,
                    name="rest_api_polling"
                )
                self._polling_thread.start()
            
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
            # Group remaining candles by interval
            remaining_by_interval = {}
            for candle in remaining_candles:
                interval = candle.interval
                if interval not in remaining_by_interval:
                    remaining_by_interval[interval] = []
                remaining_by_interval[interval].append(candle)
            
            # Save to respective tables
            for interval, candles_list in remaining_by_interval.items():
                table_name = f'live_candles_{interval}min'
                self.database.save_candles(candles_list, table_name)
            
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
