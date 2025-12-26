"""
KOTAK NEO broker implementation for data feed service.
"""
import os
import sys
import time
import json
import threading
import requests
import websocket
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from pathlib import Path

from core.base_broker import BaseBroker, TickData

from dotenv import load_dotenv
load_dotenv()


class KotakNeoBroker(BaseBroker):
    """KOTAK NEO broker implementation."""
    
    # WebSocket constants
    WS_URL = "wss://mlhsi.kotaksecurities.com"
    API_BASE_URL = "https://gw-napi.kotaksecurities.com/login"
    
    # Subscription modes
    MODE_FULL = "mf"  # Full mode with OHLC, volume, etc.
    
    # Symbol limits
    MAX_SYMBOLS_PER_CONNECTION = 100
    
    def __init__(self, config: Dict[str, Any], logger: Optional[Callable] = None):
        """
        Initialize KOTAK NEO broker.
        
        Args:
            config: Configuration dictionary with consumer_key, consumer_secret, etc.
            logger: Optional logging function
        """
        super().__init__(config, logger)
        
        # Get credentials from config or environment
        self.consumer_key = config.get('consumer_key') or os.getenv('KOTAK_CONSUMER_KEY')
        self.consumer_secret = config.get('consumer_secret') or os.getenv('KOTAK_CONSUMER_SECRET')
        self.mobile_number = config.get('mobile_number') or os.getenv('KOTAK_MOBILE_NUMBER')
        self.password = config.get('password') or os.getenv('KOTAK_PASSWORD')
        self.mpin = config.get('mpin') or os.getenv('KOTAK_MPIN')
        
        if not all([self.consumer_key, self.consumer_secret, self.mobile_number, 
                   self.password, self.mpin]):
            raise ValueError("All KOTAK NEO credentials must be provided")
        
        self.ws: Optional[websocket.WebSocketApp] = None
        self.access_token: Optional[str] = None
        self.sid: Optional[str] = None
        self.server_id: Optional[str] = None
        
        self._tick_callback: Optional[Callable] = None
        self._connection_established = False
        self._reconnect_lock = threading.Lock()
        self._ws_thread: Optional[threading.Thread] = None
        
        # Instrument token to symbol mapping
        self._token_to_symbol: Dict[int, str] = {}
        
        # Track authentication expiry
        self._auth_timestamp: Optional[float] = None
        self._auth_ttl = 86400  # 24 hours in seconds (adjust based on API docs)
    
    def _authenticate(self) -> bool:
        """
        Authenticate with KOTAK NEO API.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            self.logger("Authenticating with KOTAK NEO API...", "INFO")
            
            # Step 1: Login with credentials
            login_url = f"{self.API_BASE_URL}/1.0/login/v2/validate"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.consumer_key}:{self.consumer_secret}"
            }
            
            payload = {
                "mobileNumber": self.mobile_number,
                "password": self.password
            }
            
            response = requests.post(login_url, json=payload, headers=headers, timeout=10)
            
            if response.status_code != 200:
                self.logger(f"Login failed: {response.status_code} - {response.text}", "ERROR")
                return False
            
            login_data = response.json()
            
            # Step 2: Verify MPIN
            verify_url = f"{self.API_BASE_URL}/1.0/login/v2/validate"
            
            verify_payload = {
                "userId": login_data.get("userId"),
                "mpin": self.mpin
            }
            
            verify_response = requests.post(verify_url, json=verify_payload, headers=headers, timeout=10)
            
            if verify_response.status_code != 200:
                self.logger(f"MPIN verification failed: {verify_response.status_code}", "ERROR")
                return False
            
            auth_data = verify_response.json()
            
            # Extract authentication tokens
            self.access_token = auth_data.get("data", {}).get("token")
            self.sid = auth_data.get("data", {}).get("sid")
            self.server_id = auth_data.get("data", {}).get("serverId", "1")
            
            if not self.access_token or not self.sid:
                self.logger("Authentication successful but tokens not received", "ERROR")
                return False
            
            # Mark authentication timestamp
            self._auth_timestamp = time.time()
            
            self.logger("Authentication successful", "SUCCESS")
            return True
            
        except requests.exceptions.Timeout:
            self.logger("Authentication request timed out", "ERROR")
            return False
        except Exception as e:
            self.logger(f"Authentication error: {e}", "ERROR")
            return False
    
    def _is_auth_expired(self) -> bool:
        """Check if authentication has expired."""
        if not self._auth_timestamp:
            return True
        
        elapsed = time.time() - self._auth_timestamp
        # Check if 90% of TTL has passed (re-auth before actual expiry)
        return elapsed >= (self._auth_ttl * 0.9)
    
    def _maybe_reauthenticate(self) -> bool:
        """Re-authenticate if token is expired or about to expire."""
        if self._is_auth_expired():
            self.logger("Authentication expired or expiring soon, re-authenticating...", "INFO")
            
            # Disconnect existing websocket
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            
            # Re-authenticate
            if self._authenticate():
                self.logger("Re-authentication successful", "SUCCESS")
                return True
            else:
                self.logger("Re-authentication failed", "ERROR")
                return False
        
        return True  # No re-auth needed
    
    def connect(self) -> bool:
        """
        Establish connection to KOTAK NEO WebSocket.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Authenticate first
            if not self._authenticate():
                self.logger("Failed to authenticate with KOTAK NEO", "ERROR")
                return False
            
            # Check symbol count limit
            if len(self._instruments) > self.MAX_SYMBOLS_PER_CONNECTION:
                self.logger(
                    f"Symbol count ({len(self._instruments)}) exceeds maximum "
                    f"({self.MAX_SYMBOLS_PER_CONNECTION})",
                    "ERROR"
                )
                return False
            
            self.logger("Initializing KOTAK NEO WebSocket connection...", "INFO")
            
            # Construct WebSocket URL with authentication
            ws_url = f"{self.WS_URL}?sId={self.sid}&serverId={self.server_id}"
            
            # Create WebSocket connection
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                header={
                    "Authorization": f"Bearer {self.access_token}"
                }
            )
            
            # Start WebSocket in background thread
            self._ws_thread = threading.Thread(
                target=self._run_websocket,
                daemon=True,
                name="kotak_neo_websocket"
            )
            self._ws_thread.start()
            
            # Wait for connection to establish
            timeout = 10
            start = time.time()
            while not self._connection_established and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if self._connection_established:
                self._connected = True
                self.logger("KOTAK NEO WebSocket connected successfully", "SUCCESS")
                return True
            else:
                self.logger(f"Connection timeout after {timeout}s", "ERROR")
                return False
                
        except Exception as e:
            self.logger(f"Failed to connect to KOTAK NEO: {e}", "ERROR")
            return False
    
    def _run_websocket(self):
        """Run WebSocket connection in background thread."""
        try:
            self.ws.run_forever()
        except Exception as e:
            self.logger(f"WebSocket run error: {e}", "ERROR")
    
    def disconnect(self):
        """Disconnect from KOTAK NEO WebSocket."""
        try:
            if self.ws:
                self.logger("Disconnecting from KOTAK NEO WebSocket...", "INFO")
                self.ws.close()
                self._connected = False
                self._connection_established = False
                self.logger("Disconnected from KOTAK NEO WebSocket", "INFO")
        except Exception as e:
            self.logger(f"Error during disconnection: {e}", "WARNING")
    
    def subscribe(self, instruments: List[int]) -> bool:
        """
        Subscribe to instrument ticks.
        
        Args:
            instruments: List of instrument tokens to subscribe
        """
        try:
            if not self.is_connected():
                self.logger("Cannot subscribe: Not connected", "ERROR")
                return False
            
            if not instruments:
                self.logger("No instruments to subscribe", "WARNING")
                return False
            
            # Check symbol count limit
            total_symbols = len(self._instruments) + len(instruments)
            if total_symbols > self.MAX_SYMBOLS_PER_CONNECTION:
                self.logger(
                    f"Cannot subscribe: Total symbols ({total_symbols}) would exceed "
                    f"maximum ({self.MAX_SYMBOLS_PER_CONNECTION})",
                    "ERROR"
                )
                return False
            
            # Re-authenticate if needed
            if not self._maybe_reauthenticate():
                self.logger("Cannot subscribe: Re-authentication failed", "ERROR")
                return False
            
            # Format instruments for KOTAK NEO
            # Assuming format: {"k":"instrument_token"}
            instrument_list = [{"k": str(token)} for token in instruments]
            
            # Subscribe message
            subscribe_msg = {
                "a": "subscribe",
                "v": instrument_list,
                "m": self.MODE_FULL
            }
            
            # Send subscription message
            self.ws.send(json.dumps(subscribe_msg))
            
            self._instruments.extend(instruments)
            self.logger(f"Subscribed to {len(instruments)} instruments", "SUCCESS")
            return True
            
        except Exception as e:
            self.logger(f"Error subscribing to instruments: {e}", "ERROR")
            return False
    
    def unsubscribe(self, instruments: List[int]) -> bool:
        """
        Unsubscribe from instrument ticks.
        
        Args:
            instruments: List of instrument tokens to unsubscribe
        """
        try:
            if not self.is_connected():
                self.logger("Cannot unsubscribe: Not connected", "ERROR")
                return False
            
            # Format instruments for KOTAK NEO
            instrument_list = [{"k": str(token)} for token in instruments]
            
            # Unsubscribe message
            unsubscribe_msg = {
                "a": "unsubscribe",
                "v": instrument_list
            }
            
            # Send unsubscribe message
            self.ws.send(json.dumps(unsubscribe_msg))
            
            # Remove from internal list
            self._instruments = [i for i in self._instruments if i not in instruments]
            
            self.logger(f"Unsubscribed from {len(instruments)} instruments", "INFO")
            return True
            
        except Exception as e:
            self.logger(f"Error unsubscribing from instruments: {e}", "ERROR")
            return False
    
    def is_connected(self) -> bool:
        """Check if connected to KOTAK NEO."""
        return self._connected and self._connection_established
    
    def set_tick_callback(self, callback: Callable[[List[TickData]], None]):
        """Set callback for tick data."""
        self._tick_callback = callback
    
    def get_broker_name(self) -> str:
        """Get broker name."""
        return "KOTAK NEO"
    
    def load_instruments(self, symbols: List[str]) -> Dict[str, int]:
        """
        Load instrument tokens for given symbols.
        
        Args:
            symbols: List of trading symbols
            
        Returns:
            Dictionary mapping symbols to instrument tokens
        """
        try:
            self.logger("Loading instruments from KOTAK NEO API...", "INFO")
            
            if not self.access_token:
                if not self._authenticate():
                    self.logger("Cannot load instruments: Authentication failed", "ERROR")
                    return {}
            
            # Fetch instruments list from KOTAK NEO API
            instruments_url = f"{self.API_BASE_URL}/scripmaster/v1/instrumentDump"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            response = requests.get(instruments_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                self.logger(f"Failed to fetch instruments: {response.status_code}", "ERROR")
                return {}
            
            all_instruments = response.json()
            
            # Create mapping
            symbol_to_token = {}
            for symbol in symbols:
                found = False
                for inst in all_instruments:
                    if inst.get('tradingsymbol') == symbol:
                        token = int(inst.get('instrument_token'))
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
    
    def _on_open(self, ws):
        """WebSocket connection opened."""
        self._connection_established = True
        self.logger("KOTAK NEO WebSocket connection established", "SUCCESS")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed."""
        self._connection_established = False
        self._connected = False
        self.logger(f"KOTAK NEO WebSocket closed: {close_msg} (code: {close_status_code})", "WARNING")
        
        # Attempt to reconnect
        self._attempt_reconnect()
    
    def _on_error(self, ws, error):
        """WebSocket error."""
        self.logger(f"KOTAK NEO WebSocket error: {error}", "ERROR")
        
        # Check if error is authentication-related
        error_str = str(error).lower()
        if "401" in error_str or "unauthorized" in error_str or "token" in error_str:
            self.logger("Detected authentication error, will re-authenticate on reconnect", "WARNING")
            self._auth_timestamp = 0  # Force re-authentication
    
    def _on_message(self, ws, message):
        """Process incoming WebSocket message."""
        try:
            if not self._tick_callback:
                return
            
            # Parse message
            data = json.loads(message)
            
            # Check if this is a heartbeat
            if data.get("t") == "h":
                self.logger("Received heartbeat from KOTAK NEO (ignored)", "INFO")
                return
            
            # Check if this is tick data
            if data.get("t") != "tk":
                return
            
            # Extract ticks
            ticks = data.get("d", [])
            if not ticks:
                return
            
            # Convert KOTAK NEO ticks to standardized TickData
            tick_data_list = []
            
            for tick in ticks:
                instrument_token = int(tick.get("tk"))
                symbol = self._token_to_symbol.get(instrument_token, f"TOKEN_{instrument_token}")
                
                tick_data = TickData(
                    instrument_token=instrument_token,
                    symbol=symbol,
                    last_price=float(tick.get("lp", 0)),
                    timestamp=datetime.now(),
                    volume=int(tick.get("v", 0)),
                    oi=int(tick.get("oi", 0)),
                    depth=tick.get("depth", {})
                )
                
                tick_data_list.append(tick_data)
            
            # Call callback with tick data
            if tick_data_list:
                self._tick_callback(tick_data_list)
            
        except Exception as e:
            self.logger(f"Error processing WebSocket message: {e}", "ERROR")
    
    def _attempt_reconnect(self):
        """Attempt to reconnect to WebSocket."""
        if not self._reconnect_lock.acquire(blocking=False):
            return  # Reconnection already in progress
        
        try:
            self.logger("Attempting to reconnect to KOTAK NEO...", "INFO")
            
            # Re-authenticate if needed
            if not self._maybe_reauthenticate():
                self.logger("Reconnection failed: Re-authentication failed", "ERROR")
                return
            
            # Wait a bit before reconnecting
            time.sleep(2)
            
            # Reconnect
            if self.connect():
                self.logger("Reconnection successful", "SUCCESS")
                
                # Re-subscribe to instruments
                if self._instruments:
                    self.subscribe(self._instruments)
            else:
                self.logger("Reconnection failed", "ERROR")
                
        finally:
            self._reconnect_lock.release()
