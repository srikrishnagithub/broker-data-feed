"""
Kite broker implementation for data feed service.
"""
import os
import sys
import time
import threading
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from pathlib import Path

from core.base_broker import BaseBroker, TickData

# Import KiteConnect
try:
    from kiteconnect import KiteTicker, KiteConnect
except ImportError:
    raise ImportError("kiteconnect package not installed. Install with: pip install kiteconnect")

from dotenv import load_dotenv
load_dotenv()


class KiteBroker(BaseBroker):
    """Kite broker implementation."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[Callable] = None):
        """
        Initialize Kite broker.
        
        Args:
            config: Configuration dictionary with api_key and access_token
            logger: Optional logging function
        """
        super().__init__(config, logger)
        
        # Get credentials from config or environment
        self.api_key = config.get('api_key') or os.getenv('KITE_API_KEY')
        self.access_token = config.get('access_token') or os.getenv('KITE_ACCESS_TOKEN')
        
        if not self.api_key or not self.access_token:
            raise ValueError("KITE_API_KEY and KITE_ACCESS_TOKEN must be provided")
        
        self.kws: Optional[KiteTicker] = None
        self.kite: Optional[KiteConnect] = None
        self._tick_callback: Optional[Callable] = None
        self._connection_established = False
        self._reconnect_lock = threading.Lock()
        
        # Instrument token to symbol mapping
        self._token_to_symbol: Dict[int, str] = {}
    
    def connect(self) -> bool:
        """Establish connection to Kite WebSocket.
        
        Returns:
            True if connection successful, False otherwise.
            Specific error message is logged via the logger.
        """
        try:
            self.logger("Initializing Kite WebSocket connection...", "INFO")
            
            # Initialize KiteConnect API
            self.logger(f"api_key: {self.api_key}", "INFO")
            self.kite = KiteConnect(api_key=self.api_key)

            self.logger(f"access_token: {self.access_token}", "INFO")
            self.kite.set_access_token(self.access_token)
            
            # Test authentication
            try:
                profile = self.kite.profile()  # type: ignore
                self.logger(f"Authenticated as: {profile.get('user_name', 'Unknown')}", "SUCCESS")  # type: ignore
            except Exception as e:
                error_message = f"Authentication failed: {e}"
                self.logger(error_message, "ERROR")
                return False
            
            # Initialize KiteTicker
            self.kws = KiteTicker(self.api_key, self.access_token)
            
            # Set callbacks
            self.kws.on_connect = self._on_connect  # type: ignore
            self.kws.on_close = self._on_close  # type: ignore
            self.kws.on_error = self._on_error  # type: ignore
            self.kws.on_ticks = self._on_ticks  # type: ignore
            self.kws.on_reconnect = self._on_reconnect  # type: ignore
            self.kws.on_noreconnect = self._on_noreconnect  # type: ignore
            
            # Connect (this is blocking, so we'll run it in background)
            import threading
            connect_thread = threading.Thread(
                target=self._connect_websocket,
                daemon=True,
                name="kite_websocket"
            )
            connect_thread.start()
            
            # Wait for connection to establish
            timeout = 10
            start = time.time()
            while not self._connection_established and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if self._connection_established:
                self._connected = True
                self.logger("Kite WebSocket connected successfully", "SUCCESS")
                return True
            else:
                error_message = f"Connection timeout after {timeout}s"
                self.logger(error_message, "ERROR")
                return False
                
        except Exception as e:
            error_message = f"Failed to connect to Kite: {e}"
            self.logger(error_message, "ERROR")
            return False
    
    def _connect_websocket(self):
        """Connect to WebSocket in background thread."""
        import sys
        import os
        import signal as signal_module
        from contextlib import redirect_stderr
        from io import StringIO
        
        # Monkey patch signal.signal to suppress the specific error
        original_signal = signal_module.signal
        def patched_signal(signum, handler):
            try:
                return original_signal(signum, handler)
            except ValueError as e:
                if "signal only works in main thread" in str(e):
                    # Suppress this specific error - it's non-fatal
                    return None
                else:
                    raise
        
        signal_module.signal = patched_signal
        stderr_capture = StringIO()
        
        try:
            # Suppress any remaining stderr output
            with redirect_stderr(stderr_capture):
                self.kws.connect(threaded=False)  # type: ignore
        except ValueError as e:
            if "signal only works in main thread" in str(e):
                # This is a known issue with Twisted in background threads
                # The connection still works despite this error
                self.logger("WebSocket signal handler warning (non-fatal)", "WARNING")
            else:
                raise
        finally:
            # Restore original signal function
            signal_module.signal = original_signal
            
            # Check if we captured any error in stderr
            captured_output = stderr_capture.getvalue()
            if captured_output and "signal only works in main thread" in captured_output:
                self.logger("WebSocket signal handler warning suppressed (non-fatal)", "WARNING")

    def _rebuild_websocket(self) -> bool:
        """Rebuild KiteTicker instance and reconnect, preserving subscriptions.
        
        Returns:
            True if rebuilt and connected, False otherwise.
        """
        try:
            # Close existing socket if any
            try:
                if self.kws:
                    self.kws.close()  # type: ignore
            except Exception:
                pass

            # Create new KiteTicker with current credentials
            self.kws = KiteTicker(self.api_key, self.access_token)

            # Reattach callbacks
            self.kws.on_connect = self._on_connect  # type: ignore
            self.kws.on_close = self._on_close  # type: ignore
            self.kws.on_error = self._on_error  # type: ignore
            self.kws.on_ticks = self._on_ticks  # type: ignore
            self.kws.on_reconnect = self._on_reconnect  # type: ignore
            self.kws.on_noreconnect = self._on_noreconnect  # type: ignore

            # Reset connection flags
            self._connection_established = False
            self._connected = False

            # Connect in background
            connect_thread = threading.Thread(
                target=self._connect_websocket,
                daemon=True,
                name="kite_websocket_rebuild"
            )
            connect_thread.start()

            # Wait for connection to establish
            timeout = 10
            start = time.time()
            while not self._connection_established and (time.time() - start) < timeout:
                time.sleep(0.1)

            if not self._connection_established:
                self.logger("Rebuilt WebSocket connection timed out", "ERROR")
                return False

            self._connected = True
            self.logger("Rebuilt Kite WebSocket with updated credentials", "SUCCESS")

            # Resubscribe handled in _on_connect, but do it defensively here too
            if self._instruments:
                try:
                    self.kws.subscribe(self._instruments)  # type: ignore
                    self.kws.set_mode(self.kws.MODE_FULL, self._instruments)  # type: ignore
                except Exception as sub_e:
                    self.logger(f"Resubscribe after rebuild failed: {sub_e}", "WARNING")

            return True
        except Exception as e:
            self.logger(f"Failed to rebuild WebSocket: {e}", "ERROR")
            return False

    def _maybe_reload_token(self) -> bool:
        """Reload .env and refresh tokens if changed. Returns True if token updated."""
        try:
            # Reload environment (override existing values)
            load_dotenv(override=True)

            new_api_key = os.getenv('KITE_API_KEY') or self.api_key
            new_access_token = os.getenv('KITE_ACCESS_TOKEN')

            if not new_access_token:
                return False

            if new_access_token != self.access_token or new_api_key != self.api_key:
                old_api_mask = (self.api_key[:6] + "..." + self.api_key[-4:]) if self.api_key and len(self.api_key) > 10 else "SET"
                old_tok_mask = (self.access_token[:6] + "..." + self.access_token[-4:]) if self.access_token and len(self.access_token) > 10 else "SET"
                new_api_mask = (new_api_key[:6] + "..." + new_api_key[-4:]) if new_api_key and len(new_api_key) > 10 else "SET"
                new_tok_mask = (new_access_token[:6] + "..." + new_access_token[-4:]) if len(new_access_token) > 10 else "SET"

                self.logger(
                    f"Detected credential change. API {old_api_mask} -> {new_api_mask}; TOKEN {old_tok_mask} -> {new_tok_mask}",
                    "INFO"
                )

                # Update in-memory credentials
                self.api_key = new_api_key
                self.access_token = new_access_token

                # Update KiteConnect REST client
                try:
                    if self.kite:
                        self.kite.set_access_token(self.access_token)
                except Exception as e:
                    self.logger(f"Failed to update KiteConnect token: {e}", "WARNING")

                # Rebuild websocket with new token
                return self._rebuild_websocket()

            return False
        except Exception as e:
            self.logger(f"Token reload check failed: {e}", "WARNING")
            return False
    
    def disconnect(self):
        """Disconnect from Kite WebSocket."""
        try:
            if self.kws:
                self.logger("Disconnecting from Kite WebSocket...", "INFO")
                self.kws.close()
                self._connected = False
                self._connection_established = False
                self.logger("Disconnected from Kite WebSocket", "INFO")
        except Exception as e:
            self.logger(f"Error during disconnection: {e}", "WARNING")
    
    def subscribe(self, instruments: List[int]) -> bool:
        """Subscribe to instrument ticks."""
        try:
            if not self.is_connected():
                self.logger("Cannot subscribe: Not connected", "ERROR")
                return False
            
            if not instruments:
                self.logger("No instruments to subscribe", "WARNING")
                return False
            
            # Subscribe to instruments
            self.kws.subscribe(instruments)  # type: ignore
            
            # Set mode to full (includes OHLC, volume, etc.)
            self.kws.set_mode(self.kws.MODE_FULL, instruments)  # type: ignore
            
            self._instruments.extend(instruments)
            self.logger(f"Subscribed to {len(instruments)} instruments", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger(f"Error subscribing to instruments: {e}", "ERROR")
            return False
    
    def unsubscribe(self, instruments: List[int]) -> bool:
        """Unsubscribe from instrument ticks."""
        try:
            if not self.is_connected():
                self.logger("Cannot unsubscribe: Not connected", "ERROR")
                return False
            
            self.kws.unsubscribe(instruments)  # type: ignore
            
            # Remove from internal list
            self._instruments = [i for i in self._instruments if i not in instruments]
            
            self.logger(f"Unsubscribed from {len(instruments)} instruments", "INFO")
            return True
            
        except Exception as e:
            self.logger(f"Error unsubscribing from instruments: {e}", "ERROR")
            return False
    
    def is_connected(self) -> bool:
        """Check if connected to Kite."""
        return self._connected and self._connection_established
    
    def set_tick_callback(self, callback: Callable[[List[TickData]], None]):
        """Set callback for tick data."""
        self._tick_callback = callback
    
    def get_broker_name(self) -> str:
        """Get broker name."""
        return "Kite (Zerodha)"
    
    def load_instruments(self, symbols: List[str]) -> Dict[str, int]:
        """
        Load instrument tokens for given symbols.
        
        Args:
            symbols: List of trading symbols (e.g., ['RELIANCE', 'INFY'])
            
        Returns:
            Dictionary mapping symbols to instrument tokens
        """
        try:
            if not self.kite:
                self.logger("KiteConnect not initialized", "ERROR")
                return {}
            
            # Get all instruments
            self.logger("Fetching instrument list from Kite...", "INFO")
            all_instruments = self.kite.instruments("NSE")
            
            # Create mapping
            symbol_to_token = {}
            for symbol in symbols:
                found = False
                for inst in all_instruments:
                    if inst['tradingsymbol'] == symbol:
                        token = inst['instrument_token']
                        symbol_to_token[symbol] = token
                        self._token_to_symbol[token] = symbol
                        found = True
                        break
                
                if not found:
                    self.logger(f"Instrument not found: {symbol}", "WARNING")
            
            self.logger(f"Loaded {len(symbol_to_token)} instrument tokens", "SUCCESS")
            return symbol_to_token
            
        except Exception as e:
            self.logger(f"Error loading instruments: {e}", "ERROR")
            return {}
    
    # WebSocket callbacks
    
    def _on_connect(self, ws, response):
        """WebSocket connection established."""
        self._connection_established = True
        self.logger("Kite WebSocket connection established", "SUCCESS")
        # Ensure subscriptions are active after any (re)connect
        try:
            if self._instruments and self.kws:
                self.kws.subscribe(self._instruments)  # type: ignore
                self.kws.set_mode(self.kws.MODE_FULL, self._instruments)  # type: ignore
                self.logger(f"Re-subscribed to {len(self._instruments)} instruments", "INFO")
        except Exception as e:
            self.logger(f"Auto-resubscribe failed: {e}", "WARNING")
    
    def _on_close(self, ws, code, reason):
        """WebSocket connection closed."""
        self._connection_established = False
        self._connected = False
        self.logger(f"Kite WebSocket closed: {reason} (code: {code})", "WARNING")
    
    def _on_error(self, ws, code, reason):
        """WebSocket error."""
        self.logger(f"Kite WebSocket error: {reason} (code: {code})", "ERROR")
    
    def _on_reconnect(self, ws, attempts_count):
        """WebSocket reconnecting."""
        self.logger(f"Kite WebSocket reconnecting (attempt {attempts_count})...", "INFO")
        # Attempt token hot-reload once per reconnect cycle
        if self._reconnect_lock.acquire(blocking=False):
            try:
                updated = self._maybe_reload_token()
                if updated:
                    self.logger("Token updated; websocket rebuilt and reconnect initiated", "SUCCESS")
            finally:
                self._reconnect_lock.release()
    
    def _on_noreconnect(self, ws):
        """WebSocket reconnection failed."""
        self._connection_established = False
        self._connected = False
        self.logger("Kite WebSocket reconnection failed", "ERROR")
    
    def _on_ticks(self, ws, ticks):
        """Process incoming ticks."""
        try:
            if not self._tick_callback:
                return
            
            # Check if this is a heartbeat (single byte or empty data)
            if not ticks or (isinstance(ticks, bytes) and len(ticks) == 1):
                # This is a heartbeat, ignore it
                self.logger("Received heartbeat from Kite (ignored)", "INFO")
                return
            
            # Ensure ticks is a list
            if not isinstance(ticks, list):
                self.logger(f"Unexpected tick data type: {type(ticks)}", "WARNING")
                return
            
            # Convert Kite ticks to standardized TickData
            tick_data_list = []
            debug_logged = False
            
            for tick in ticks:
                # Skip if tick is not a valid dictionary
                if not isinstance(tick, dict):
                    continue
                    
                instrument_token = tick.get('instrument_token')
                if instrument_token is None:
                    continue
                
                # Debug: Log tick structure for first tick only
                if not debug_logged:
                    self.logger(f"DEBUG: Kite tick keys: {list(tick.keys())}", "DEBUG")
                    debug_logged = True
                    
                symbol = self._token_to_symbol.get(instrument_token, f"TOKEN_{instrument_token}")
                
                # Extract volume: Try multiple Kite API field names in priority order
                    # 'last_traded_quantity' = volume traded in this specific tick (CORRECT FIELD)
                    # 'last_quantity' = alternative field name 
                    # 'volume_traded' = cumulative volume for the day (fallback - NOTE: this won't accumulate properly in candles)
                volume = (
                        tick.get('last_traded_quantity') or 
                        tick.get('last_quantity') or 
                        tick.get('volume_traded') or 
                        tick.get('volume') or 
                    0
                )
                
                # DEBUG: If all volume fields are 0, log a sample tick to understand structure
                if volume == 0 and instrument_token in [6401, 2952193]:  # Log for specific stocks
                    self.logger(f"DEBUG: Zero volume tick for {symbol}: {tick}", "WARNING")
                
                tick_data = TickData(
                    instrument_token=instrument_token,
                    symbol=symbol,
                    last_price=tick.get('last_price', 0),
                    timestamp=datetime.now(),
                    volume=volume,
                    oi=tick.get('oi', 0),
                    depth=tick.get('depth', {})
                )
                
                tick_data_list.append(tick_data)
            
            # Only call callback if we have valid tick data
            if tick_data_list:
                self._tick_callback(tick_data_list)
            
        except Exception as e:
            self.logger(f"Error processing ticks: {e}", "ERROR")
