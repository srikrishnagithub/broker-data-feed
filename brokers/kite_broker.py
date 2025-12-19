"""
Kite broker implementation for data feed service.
"""
import os
import sys
import time
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from broker_data_feed.core.base_broker import BaseBroker, TickData

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
        
        # Instrument token to symbol mapping
        self._token_to_symbol: Dict[int, str] = {}
    
    def connect(self) -> bool:
        """Establish connection to Kite WebSocket."""
        try:
            self.logger("Initializing Kite WebSocket connection...", "INFO")
            
            # Initialize KiteConnect API
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Test authentication
            try:
                profile = self.kite.profile()
                self.logger(f"Authenticated as: {profile.get('user_name', 'Unknown')}", "SUCCESS")
            except Exception as e:
                self.logger(f"Authentication failed: {e}", "ERROR")
                return False
            
            # Initialize KiteTicker
            self.kws = KiteTicker(self.api_key, self.access_token)
            
            # Set callbacks
            self.kws.on_connect = self._on_connect
            self.kws.on_close = self._on_close
            self.kws.on_error = self._on_error
            self.kws.on_ticks = self._on_ticks
            self.kws.on_reconnect = self._on_reconnect
            self.kws.on_noreconnect = self._on_noreconnect
            
            # Connect (this is blocking, so we'll run it in background)
            import threading
            connect_thread = threading.Thread(
                target=self.kws.connect,
                kwargs={'threaded': False},
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
                self.logger(f"Connection timeout after {timeout}s", "ERROR")
                return False
                
        except Exception as e:
            self.logger(f"Failed to connect to Kite: {e}", "ERROR")
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
            self.kws.subscribe(instruments)
            
            # Set mode to full (includes OHLC, volume, etc.)
            self.kws.set_mode(self.kws.MODE_FULL, instruments)
            
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
            
            self.kws.unsubscribe(instruments)
            
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
            
            # Convert Kite ticks to standardized TickData
            tick_data_list = []
            
            for tick in ticks:
                instrument_token = tick.get('instrument_token')
                symbol = self._token_to_symbol.get(instrument_token, f"TOKEN_{instrument_token}")
                
                tick_data = TickData(
                    instrument_token=instrument_token,
                    symbol=symbol,
                    last_price=tick.get('last_price', 0),
                    timestamp=datetime.now(),
                    volume=tick.get('volume', 0),
                    oi=tick.get('oi', 0),
                    depth=tick.get('depth', {})
                )
                
                tick_data_list.append(tick_data)
            
            # Call the tick callback
            self._tick_callback(tick_data_list)
            
        except Exception as e:
            self.logger(f"Error processing ticks: {e}", "ERROR")
