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
import pyotp
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from pathlib import Path

from core.base_broker import BaseBroker, TickData

from dotenv import load_dotenv
load_dotenv()


class KotakNeoBroker(BaseBroker):
    """KOTAK NEO broker implementation."""
    
    # API endpoints (per official documentation)
    API_BASE_URL = "https://mis.kotaksecurities.com"
    LOGIN_ENDPOINT = "/login/1.0/tradeApiLogin"
    VALIDATE_ENDPOINT = "/login/1.0/tradeApiValidate"
    
    # WebSocket constants (to be determined)
    WS_URL = "wss://mlhsi.kotaksecurities.com"  # May need confirmation
    
    # Subscription modes
    MODE_FULL = "mf"  # Full mode with OHLC, volume, etc.
    
    # Symbol limits
    MAX_SYMBOLS_PER_CONNECTION = 100
    
    def __init__(self, config: Dict[str, Any], logger: Optional[Callable] = None):
        """
        Initialize KOTAK NEO broker.
        
        Args:
            config: Configuration dictionary with access_token, mobile_number, etc.
            logger: Optional logging function
        """
        super().__init__(config, logger)
        
        # Get credentials from config or environment (per official docs)
        self.api_access_token = config.get('access_token') or os.getenv('KOTAK_ACCESS_TOKEN')
        self.mobile_number = config.get('mobile_number') or os.getenv('KOTAK_MOBILE_NUMBER')
        self.ucc = config.get('ucc') or os.getenv('KOTAK_UCC')
        self.totp_secret = config.get('totp_secret') or os.getenv('KOTAK_TOTP_SECRET')
        self.mpin = config.get('mpin') or os.getenv('KOTAK_MPIN')
        
        if not all([self.api_access_token, self.mobile_number, self.ucc, 
                   self.totp_secret, self.mpin]):
            raise ValueError("All KOTAK NEO credentials must be provided: "
                           "access_token, mobile_number, ucc, totp_secret, mpin")
        
        self.ws: Optional[websocket.WebSocketApp] = None
        self.session_token: Optional[str] = None  # Trade token from Step 2
        self.view_token: Optional[str] = None     # View token from Step 1
        self.sid: Optional[str] = None
        self.base_url: Optional[str] = None       # Base URL from auth response
        
        self._tick_callback: Optional[Callable] = None
        self._connection_established = False
        self._reconnect_lock = threading.Lock()
        self._ws_thread: Optional[threading.Thread] = None
        
        # Instrument token to symbol mapping
        self._token_to_symbol: Dict[int, str] = {}
        
        # Track authentication expiry
        self._auth_timestamp: Optional[float] = None
        self._auth_ttl = 86400  # 24 hours in seconds
        
        # Track previous volumes for delta calculation (REST API)
        self._prev_volumes: Dict[int, int] = {}  # instrument_token -> last cumulative volume
        
        # Database handler (optional, for faster instrument lookups)
        self.db = None
    
    def _generate_totp(self) -> str:
        """
        Generate TOTP using the secret key.
        
        Returns:
            6-digit TOTP string
        """
        try:
            totp = pyotp.TOTP(self.totp_secret)
            return totp.now()
        except Exception as e:
            self.logger(f"Error generating TOTP: {e}", "ERROR")
            raise
    
    def _authenticate(self) -> bool:
        """
        Authenticate with KOTAK NEO API using official 2-step flow.
        
        Step 1: Login with TOTP (tradeApiLogin)
        Step 2: Validate with MPIN (tradeApiValidate)
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            self.logger("Authenticating with KOTAK NEO API...", "INFO")
            
            # Generate TOTP
            totp = self._generate_totp()
            self.logger(f"Generated TOTP: {totp}", "INFO")
            
            # Step 1: Login with TOTP
            login_url = f"{self.API_BASE_URL}{self.LOGIN_ENDPOINT}"
            
            login_headers = {
                "Content-Type": "application/json",
                "Authorization": self.api_access_token,  # Plain token from NEO dashboard
                "neo-fin-key": "neotradeapi"
            }
            
            login_payload = {
                "mobileNumber": self.mobile_number,  # Should include +91
                "ucc": self.ucc,
                "totp": totp
            }
            
            self.logger(f"Step 1: Logging in with TOTP to {login_url}", "INFO")
            response = requests.post(login_url, json=login_payload, headers=login_headers, timeout=10)
            
            if response.status_code != 200:
                self.logger(f"Login failed: {response.status_code} - {response.text}", "ERROR")
                return False
            
            login_data = response.json()
            
            # Check if login was successful
            if login_data.get("data", {}).get("status") != "success":
                self.logger(f"Login failed: {login_data.get('message', 'Unknown error')}", "ERROR")
                return False
            
            # Extract view token and session info
            data = login_data.get("data", {})
            self.view_token = data.get("token")
            view_sid = data.get("sid")
            
            if not self.view_token or not view_sid:
                self.logger("Login successful but view token/sid not received", "ERROR")
                self.logger(f"Response data: {data}", "DEBUG")
                return False
            
            self.logger("Step 1: Login with TOTP successful", "SUCCESS")
            
            # Step 2: Validate with MPIN
            validate_url = f"{self.API_BASE_URL}{self.VALIDATE_ENDPOINT}"
            
            validate_headers = {
                "Content-Type": "application/json",
                "Authorization": self.api_access_token,
                "neo-fin-key": "neotradeapi",
                "sid": view_sid,
                "Auth": self.view_token
            }
            
            validate_payload = {
                "mpin": self.mpin
            }
            
            self.logger(f"Step 2: Validating MPIN to {validate_url}", "INFO")
            validate_response = requests.post(validate_url, json=validate_payload, 
                                            headers=validate_headers, timeout=10)
            
            if validate_response.status_code != 200:
                self.logger(f"MPIN validation failed: {validate_response.status_code} - {validate_response.text}", "ERROR")
                return False
            
            auth_data = validate_response.json()
            
            # Check if validation was successful
            if auth_data.get("data", {}).get("status") != "success":
                self.logger(f"MPIN validation failed: {auth_data.get('message', 'Unknown error')}", "ERROR")
                return False
            
            # Extract session token and base URL
            data = auth_data.get("data", {})
            self.session_token = data.get("token")  # This is the Trade token
            self.sid = data.get("sid")
            self.base_url = data.get("baseUrl")
            
            if not self.session_token or not self.sid:
                self.logger("MPIN validation successful but session token/sid not received", "ERROR")
                self.logger(f"Response data: {data}", "DEBUG")
                return False
            
            # Mark authentication timestamp
            self._auth_timestamp = time.time()
            
            self.logger("Step 2: MPIN validation successful", "SUCCESS")
            self.logger(f"Session token obtained (kType: {data.get('kType')})", "SUCCESS")
            self.logger(f"Base URL: {self.base_url}", "INFO")
            
            # Fetch instrument master for correct pSymbol mapping
            self.logger("Fetching instrument master...", "INFO")
            self.fetch_instrument_master()
            
            return True
            
        except requests.exceptions.Timeout:
            self.logger("Authentication request timed out", "ERROR")
            return False
        except Exception as e:
            self.logger(f"Authentication error: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "DEBUG")
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
        
        NOTE: WebSocket implementation is pending - needs confirmation on protocol.
        Currently only authentication is implemented and tested.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Authenticate first
            if not self._authenticate():
                self.logger("Failed to authenticate with KOTAK NEO", "ERROR")
                return False
            
            # Authentication successful!
            self.logger("Authentication completed successfully!", "SUCCESS")
            self.logger("WebSocket implementation pending confirmation from official docs", "INFO")
            
            # TODO: Implement WebSocket connection once protocol is confirmed
            # Options:
            # 1. WebSocket streaming (if available)
            # 2. REST API polling (as per Quotes.txt documentation)
            
            # For now, mark as connected after successful auth
            self._connected = True
            return True
            
            # # Check symbol count limit
            # if len(self._instruments) > self.MAX_SYMBOLS_PER_CONNECTION:
            #     self.logger(
            #         f"Symbol count ({len(self._instruments)}) exceeds maximum "
            #         f"({self.MAX_SYMBOLS_PER_CONNECTION})",
            #         "ERROR"
            #     )
            #     return False
            # 
            # self.logger("Initializing KOTAK NEO WebSocket connection...", "INFO")
            # 
            # # Construct WebSocket URL with authentication
            # # NOTE: This needs to be confirmed against official documentation
            # ws_url = f"{self.WS_URL}?sId={self.sid}"
            # 
            # # Create WebSocket connection
            # self.ws = websocket.WebSocketApp(
            #     ws_url,
            #     on_open=self._on_open,
            #     on_message=self._on_message,
            #     on_error=self._on_error,
            #     on_close=self._on_close,
            #     header={
            #         "Authorization": f"Bearer {self.session_token}"
            #     }
            # )
            # 
            # # Start WebSocket in background thread
            # self._ws_thread = threading.Thread(
            #     target=self._run_websocket,
            #     daemon=True,
            #     name="kotak_neo_websocket"
            # )
            # self._ws_thread.start()
            # 
            # # Wait for connection to establish
            # timeout = 10
            # start = time.time()
            # while not self._connection_established and (time.time() - start) < timeout:
            #     time.sleep(0.1)
            # 
            # if self._connection_established:
            #     self._connected = True
            #     self.logger("KOTAK NEO WebSocket connected successfully", "SUCCESS")
            #     return True
            # else:
            #     self.logger(f"Connection timeout after {timeout}s", "ERROR")
            #     return False
                
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
    
    def fetch_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch quotes for given symbols using REST API.
        
        Args:
            symbols: List of trading symbols (e.g., ['RELIANCE', 'INFY', 'TCS'])
            
        Returns:
            List of quote dictionaries with OHLC and other data
        """
        try:
            if not self.session_token or not self.base_url:
                self.logger("Cannot fetch quotes: Not authenticated", "ERROR")
                return []
            
            # Re-authenticate if needed
            if not self._maybe_reauthenticate():
                self.logger("Cannot fetch quotes: Re-authentication failed", "ERROR")
                return []
            
            # Build query string: nse_cm|TOKEN1,nse_cm|TOKEN2,...
            # KOTAK API requires exchange token (pSymbol field from CSV - numeric)
            queries = []
            unmapped_symbols = []
            
            for symbol in symbols:
                # Find the exchange token for this base symbol
                token = self.find_exchange_token(symbol)
                
                if token:
                    queries.append(f"nse_cm|{token}")
                else:
                    unmapped_symbols.append(symbol)
            
            if unmapped_symbols:
                self.logger(f"Could not map {len(unmapped_symbols)} symbols (no exchange token): {unmapped_symbols[:5]}...", "WARNING")
            
            if not queries:
                self.logger("No valid symbols to query", "ERROR")
                return []
            
            query_string = ",".join(queries)
            
            self.logger(f"Query string: {query_string}", "INFO")
            
            # Construct URL
            url = f"{self.base_url}/script-details/1.0/quotes/neosymbol/{query_string}/all"
            
            self.logger(f"Requesting URL: {url[:100]}...", "DEBUG")
            
            # Headers
            headers = {
                "Authorization": self.api_access_token,
                "Content-Type": "application/json"
            }
            
            # Make request
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                error_msg = response.text
                # Check if it's a temporary error (424, 502, 503, 504)
                if response.status_code in [424, 502, 503, 504]:
                    self.logger(f"Temporary API error ({response.status_code}): {error_msg}", "WARNING")
                    self.logger("Will retry on next poll cycle", "INFO")
                else:
                    self.logger(f"Failed to fetch quotes: {response.status_code} - {error_msg}", "ERROR")
                return []
            
            data = response.json()
            
            # Handle response - could be dict with error or list of quotes
            if isinstance(data, dict):
                # Check for fault/error
                if 'fault' in data:
                    fault = data['fault']
                    self.logger(f"API fault: {fault.get('message')} - {fault.get('description')}", "ERROR")
                    return []
                
                # Check for stat error
                if data.get('stat') == 'Not_Ok':
                    self.logger(f"API error: {data.get('emsg', 'Unknown error')}", "ERROR")
                    return []
                
                # Single quote response - wrap in list
                quotes = [data]
            elif isinstance(data, list):
                quotes = data
            else:
                self.logger(f"Unexpected response format: {type(data)}", "ERROR")
                self.logger(f"Response: {data}", "DEBUG")
                return []
            
            self.logger(f"Fetched {len(quotes)} quotes successfully", "SUCCESS")
            
            # Debug: Log which symbols are missing (if fewer than requested)
            if len(quotes) < len(symbols):
                returned_symbols = set()
                for quote in quotes:
                    # Extract symbol from response
                    display_symbol = quote.get('displaySymbol') or quote.get('symbol') or quote.get('tradingSymbol') or ''
                    symbol = display_symbol.split('-')[0].strip()
                    returned_symbols.add(symbol)
                
                requested_symbols = set(symbols)
                missing_symbols = requested_symbols - returned_symbols
                
                if missing_symbols:
                    self.logger(f"Missing quotes for {len(missing_symbols)} symbols: {sorted(list(missing_symbols))[:10]}...", "WARNING")
            
            return quotes
            
        except requests.exceptions.Timeout:
            self.logger("Quotes request timed out", "ERROR")
            return []
        except Exception as e:
            self.logger(f"Error fetching quotes: {e}", "ERROR")
            return []
    
    def convert_quote_to_tick(self, quote: Dict[str, Any]) -> Optional[TickData]:
        """
        Convert REST API quote to TickData format.
        
        Args:
            quote: Quote dictionary from REST API
            
        Returns:
            TickData object or None if conversion fails
        """
        try:
            # Extract data from quote
            exchange_token = quote.get('exchange_token', '')
            display_symbol = quote.get('display_symbol', '')
            
            # Extract symbol (remove exchange suffix like -EQ, -IN, etc.)
            symbol = display_symbol.split('-')[0] if display_symbol else exchange_token
            
            # Find the instrument token from our mapping
            instrument_token = None
            
            # Try 1: Check if the full display_symbol matches a variant (e.g., RELIANCE-EQ)
            if hasattr(self, '_symbol_variants') and display_symbol in self._symbol_variants:
                instrument_token = self._symbol_variants[display_symbol]
            
            # Try 2: Check if base symbol matches
            if instrument_token is None:
                for token, mapped_symbol in self._token_to_symbol.items():
                    if mapped_symbol == symbol:
                        instrument_token = token
                        break
            
            # Try 3: Check exchange_token
            if instrument_token is None and exchange_token:
                for token, mapped_symbol in self._token_to_symbol.items():
                    if mapped_symbol == exchange_token:
                        instrument_token = token
                        break
            
            # If not found, create a token from the symbol
            if instrument_token is None:
                instrument_token = hash(symbol) % (10 ** 8)
                self.logger(f"WARNING: Created token {instrument_token} for unmapped symbol '{symbol}'", "WARNING")
                # Add to mapping so candle aggregator can use it
                self._token_to_symbol[instrument_token] = symbol
            
            # Get price data
            ltp = float(quote.get('ltp', 0))
            cumulative_volume = int(quote.get('last_volume', 0))
            
            # Calculate volume delta (volume traded since last tick)
            prev_volume = self._prev_volumes.get(instrument_token, None)
            
            if prev_volume is None:
                # First tick - set baseline without volume
                volume_delta = 0
            else:
                # Calculate delta from previous tick
                volume_delta = max(0, cumulative_volume - prev_volume)
            
            # Update previous volume tracker
            self._prev_volumes[instrument_token] = cumulative_volume
            
            # Create TickData
            tick = TickData(
                instrument_token=instrument_token,
                symbol=symbol,
                last_price=ltp,
                timestamp=datetime.now(),
                volume=volume_delta,  # Use delta, not cumulative
                oi=0,  # Not provided in quotes API
                depth={}  # Depth available in full response
            )
            
            return tick
            
        except Exception as e:
            self.logger(f"Error converting quote to tick: {e}", "ERROR")
            self.logger(f"Quote data: {quote}", "DEBUG")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "DEBUG")
            return None
    
    def subscribe(self, instruments: List[int]) -> bool:
        """
        Subscribe to instrument quotes using REST API polling.
        
        For REST API implementation, this stores the instruments for polling.
        
        Args:
            instruments: List of instrument tokens to subscribe
        """
        try:
            if not self.is_connected():
                self.logger("Cannot subscribe: Not authenticated", "ERROR")
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
            
            # For REST API, just store the instruments
            # Actual polling will be done by the service
            self._instruments.extend(instruments)
            self.logger(f"Subscribed to {len(instruments)} instruments (REST API mode)", "SUCCESS")
            
            return True
            
        except Exception as e:
            self.logger(f"Error subscribing to instruments: {e}", "ERROR")
            return False
    
    def unsubscribe(self, instruments: List[int]) -> bool:
        """
        Unsubscribe from instrument quotes.
        
        Args:
            instruments: List of instrument tokens to unsubscribe
        """
        try:
            if not self.is_connected():
                self.logger("Cannot unsubscribe: Not authenticated", "ERROR")
                return False
            
            # For REST API, just remove from instruments list
            self._instruments = [i for i in self._instruments if i not in instruments]
            
            self.logger(f"Unsubscribed from {len(instruments)} instruments", "INFO")
            return True
            
        except Exception as e:
            self.logger(f"Error unsubscribing from instruments: {e}", "ERROR")
            return False
    
    def is_connected(self) -> bool:
        """Check if authenticated with KOTAK NEO."""
        return self._connected
    
    def set_tick_callback(self, callback: Callable[[List[TickData]], None]):
        """Set callback for tick data."""
        self._tick_callback = callback
    
    def get_broker_name(self) -> str:
        """Get broker name."""
        return "KOTAK NEO (REST API)"
    
    def fetch_instrument_master(self) -> bool:
        """
        Fetch instrument master file from KOTAK NEO to get pSymbol mappings.
        
        Uses the /masterscrip/file-paths endpoint to get download URLs.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.session_token or not self.base_url:
                self.logger("Cannot fetch instrument master: Not authenticated", "ERROR")
                return False
            
            # Step 1: Get file paths
            file_paths_url = f"{self.base_url}/script-details/1.0/masterscrip/file-paths"
            
            headers = {
                "accept": "application/json",
                "Authorization": self.api_access_token,
                "sid": self.session_token
            }
            
            self.logger(f"Fetching scrip master file paths from: {file_paths_url}", "INFO")
            
            response = requests.get(file_paths_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                self.logger(f"Failed to get file paths: {response.status_code} - {response.text}", "ERROR")
                return False
            
            file_paths = response.json()
            self.logger(f"Received file paths response", "INFO")
            
            # Step 2: Extract file URLs from response
            # Expected structure: {"data": {"baseFolder": "...", "filesPaths": [...]}}
            download_url = None
            file_list = []
            
            if isinstance(file_paths, dict) and 'data' in file_paths:
                data = file_paths['data']
                if 'filesPaths' in data:
                    file_list = data['filesPaths']
                elif 'filePaths' in data:
                    file_list = data['filePaths']
            
            self.logger(f"Found {len(file_list)} file paths", "INFO")
            
            # Find NSE CM (cash market) file
            for file_url in file_list:
                if 'nse_cm' in file_url.lower() or 'nse-cm' in file_url.lower():
                    download_url = file_url
                    self.logger(f"Found NSE CM file: {file_url}", "SUCCESS")
                    break
            
            # Fallback: use first NSE file
            if not download_url:
                for file_url in file_list:
                    if 'nse' in file_url.lower():
                        download_url = file_url
                        self.logger(f"Using NSE file: {file_url}", "INFO")
                        break
            
            # Last resort: use first file
            if not download_url and file_list:
                download_url = file_list[0]
                self.logger(f"Using first available file: {download_url}", "INFO")
            
            if not download_url:
                self.logger("No download URL found in response", "ERROR")
                return False
            
            # Step 3: Download the file
            self.logger(f"Downloading scrip master from: {download_url}", "INFO")
            
            # Headers for file download (may not need auth)
            file_headers = {
                "accept": "text/csv"
            }
            
            file_response = requests.get(download_url, headers=file_headers, timeout=60)
            
            if file_response.status_code != 200:
                self.logger(f"Failed to download file: {file_response.status_code}", "ERROR")
                return False
            
            # Step 4: Parse the downloaded file
            content_type = file_response.headers.get('Content-Type', '')
            
            if 'json' in content_type:
                data = file_response.json()
                self.logger(f"Received JSON instrument data with {len(data)} instruments", "SUCCESS")
                self._instrument_master = data
                return True
            elif 'csv' in content_type or 'text' in content_type:
                # Parse CSV
                import csv
                import io
                csv_data = io.StringIO(file_response.text)
                reader = csv.DictReader(csv_data)
                instruments = list(reader)
                self.logger(f"Received CSV instrument data with {len(instruments)} instruments", "SUCCESS")
                
                # Log sample instrument to see available fields
                if instruments:
                    self.logger(f"Sample instrument fields: {list(instruments[0].keys())}", "INFO")
                    self.logger(f"Sample instrument data: {instruments[0]}", "INFO")
                
                self._instrument_master = instruments
                return True
            else:
                self.logger(f"Unknown content type: {content_type}", "WARNING")
                self.logger(f"First 200 chars of response: {file_response.text[:200]}", "DEBUG")
                # Try parsing as CSV anyway
                try:
                    import csv
                    import io
                    csv_data = io.StringIO(file_response.text)
                    reader = csv.DictReader(csv_data)
                    instruments = list(reader)
                    self.logger(f"Parsed as CSV: {len(instruments)} instruments", "SUCCESS")
                    
                    # Log sample instrument to see available fields
                    if instruments:
                        self.logger(f"Sample instrument fields: {list(instruments[0].keys())}", "INFO")
                        self.logger(f"First 3 instruments for reference:", "INFO")
                        for i, inst in enumerate(instruments[:3]):
                            self.logger(f"  [{i}] {inst}", "INFO")
                    
                    self._instrument_master = instruments
                    return True
                except Exception as e:
                    self.logger(f"Failed to parse response: {e}", "ERROR")
                    return False
            
        except Exception as e:
            self.logger(f"Error fetching instrument master: {e}", "ERROR")
            import traceback
            self.logger(f"Traceback: {traceback.format_exc()}", "DEBUG")
            return False
    
    def find_psymbol_from_db(self, symbol: str) -> Optional[str]:
        """
        Find pSymbol from database kotak_instruments table.
        
        Args:
            symbol: Base symbol (e.g., 'RELIANCE')
            
        Returns:
            pSymbol if found, None otherwise
        """
        try:
            from sqlalchemy import text
            
            # Get database connection from environment
            import os
            conn_str = os.getenv('PG_CONN_STR')
            if not conn_str:
                return None
            
            from sqlalchemy import create_engine
            engine = create_engine(conn_str)
            
            with engine.connect() as conn:
                # Try exact match first
                query = text("""
                    SELECT trading_symbol FROM kotak_instruments 
                    WHERE trading_symbol = :symbol 
                    AND exchange_segment = 'nse_cm'
                    LIMIT 1
                """)
                result = conn.execute(query, {'symbol': symbol})
                row = result.fetchone()
                
                if row:
                    return row[0]
                
                # Try with -EQ suffix
                query = text("""
                    SELECT trading_symbol FROM kotak_instruments 
                    WHERE trading_symbol = :symbol_eq 
                    AND exchange_segment = 'nse_cm'
                    LIMIT 1
                """)
                result = conn.execute(query, {'symbol_eq': f"{symbol}-EQ"})
                row = result.fetchone()
                
                if row:
                    return row[0]
                
                # Try with pattern matching (starts with)
                query = text("""
                    SELECT trading_symbol FROM kotak_instruments 
                    WHERE trading_symbol LIKE :pattern
                    AND exchange_segment = 'nse_cm'
                    ORDER BY LENGTH(trading_symbol)
                    LIMIT 1
                """)
                result = conn.execute(query, {'pattern': f'{symbol}%'})
                row = result.fetchone()
                
                if row:
                    return row[0]
            
            return None
            
        except Exception as e:
            self.logger(f"Error finding pSymbol from database: {e}", "DEBUG")
            return None
    
    def find_psymbol(self, symbol: str) -> Optional[str]:
        """
        Find the correct pSymbol for a given symbol.
        
        Priority:
        1. Database lookup (kotak_instruments table)
        2. In-memory instrument master
        
        Args:
            symbol: Base symbol (e.g., 'RELIANCE')
            
        Returns:
            pSymbol if found (e.g., 'RELIANCE-EQ'), None otherwise
        """
        # Try database first (fastest)
        psymbol = self.find_psymbol_from_db(symbol)
        if psymbol:
            self.logger(f"Found pSymbol '{psymbol}' for '{symbol}' from database", "DEBUG")
            return psymbol
        
        # Fallback to in-memory instrument master
        if not hasattr(self, '_instrument_master') or not self._instrument_master:
            return None
        
        # Search for matching instrument
        for inst in self._instrument_master:
            # Different possible field names
            trading_symbol = inst.get('tradingsymbol') or inst.get('pSymbol') or inst.get('symbol')
            
            if trading_symbol and symbol.upper() in trading_symbol.upper():
                psymbol = inst.get('pSymbol') or trading_symbol
                self.logger(f"Found pSymbol '{psymbol}' for symbol '{symbol}' from memory", "DEBUG")
                return psymbol
        
        return None
    
    def find_exchange_token(self, symbol: str) -> Optional[str]:
        """
        Find exchange token (pSymbol field from CSV) for a given symbol.
        
        From the CSV structure:
        - pSymbol: Numeric exchange token (e.g., '2885')
        - pTrdSymbol: Trading symbol name (e.g., 'RELIANCE-EQ')
        
        Symbol variants (in priority order):
        1. Base symbol without suffix (e.g., 'RELIANCE')
        2. With -EQ suffix for NSE equity (e.g., 'RELIANCE-EQ') - preferred
        3. With -BL suffix for NSE bulk (e.g., 'RELIANCE-BL')
        4. Any other variant
        
        Args:
            symbol: Base symbol (e.g., 'RELIANCE')
            
        Returns:
            Exchange token as string (e.g., '2885'), None if not found
        """
        # Try database first (fastest)
        if self.db:
            try:
                from sqlalchemy import text
                
                # Check if engine is valid
                if not hasattr(self.db, 'engine') or self.db.engine is None:
                    self.logger(f"Database engine not initialized for {symbol}", "WARNING")
                else:
                    with self.db.engine.connect() as conn:
                        # Priority 1: Exact match
                        result = conn.execute(text("""
                            SELECT psymbol 
                            FROM kotak_instruments 
                            WHERE trading_symbol = :symbol 
                            AND exchange_segment = 'nse_cm'
                            LIMIT 1
                        """), {'symbol': symbol})
                        row = result.fetchone()
                        if row and row[0]:
                            self.logger(f"Found token '{row[0]}' for symbol '{symbol}' (exact match)", "DEBUG")
                            return str(row[0])
                        
                        # Priority 2: With -EQ suffix (preferred for equity traders)
                        symbol_with_eq = f"{symbol}-EQ"
                        result = conn.execute(text("""
                            SELECT psymbol 
                            FROM kotak_instruments 
                            WHERE trading_symbol = :symbol 
                            AND exchange_segment = 'nse_cm'
                            LIMIT 1
                        """), {'symbol': symbol_with_eq})
                        row = result.fetchone()
                        if row and row[0]:
                            self.logger(f"Found token '{row[0]}' for symbol '{symbol}' (with -EQ suffix)", "DEBUG")
                            return str(row[0])
                        
                        # Priority 3: With -BL suffix (bulk segment)
                        symbol_with_bl = f"{symbol}-BL"
                        result = conn.execute(text("""
                            SELECT psymbol 
                            FROM kotak_instruments 
                            WHERE trading_symbol = :symbol 
                            AND exchange_segment = 'nse_cm'
                            LIMIT 1
                        """), {'symbol': symbol_with_bl})
                        row = result.fetchone()
                        if row and row[0]:
                            self.logger(f"Found token '{row[0]}' for symbol '{symbol}' (with -BL suffix)", "DEBUG")
                            return str(row[0])
                        
                        # Priority 4: Any variant starting with the symbol
                        pattern = f"{symbol}%"
                        result = conn.execute(text("""
                            SELECT psymbol 
                            FROM kotak_instruments 
                            WHERE trading_symbol LIKE :pattern
                            AND exchange_segment = 'nse_cm'
                            LIMIT 1
                        """), {'pattern': pattern})
                        row = result.fetchone()
                        if row and row[0]:
                            self.logger(f"Found token '{row[0]}' for symbol '{symbol}' (pattern match)", "DEBUG")
                            return str(row[0])
                        
                        self.logger(f"No token found in database for symbol '{symbol}'", "WARNING")
            except Exception as e:
                self.logger(f"Database lookup failed for {symbol}: {type(e).__name__}: {e}", "WARNING")
                import traceback
                self.logger(f"Traceback: {traceback.format_exc()}", "DEBUG")
        else:
            self.logger(f"No database handler available for {symbol}", "DEBUG")
        
        # Fallback to in-memory instrument master
        if hasattr(self, '_instrument_master') and self._instrument_master:
            for inst in self._instrument_master:
                # pTrdSymbol contains the trading name like 'RELIANCE' or 'RELIANCE-EQ'
                trading_symbol = inst.get('pTrdSymbol')
                
                if trading_symbol and symbol.upper() == trading_symbol.upper():
                    # pSymbol contains the numeric exchange token
                    token = inst.get('pSymbol')
                    if token:
                        self.logger(f"Found token '{token}' for symbol '{symbol}' (from instrument master)", "DEBUG")
                        return str(token)
        
        return None
    
    def _get_exchange_token(self, psymbol: str) -> Optional[str]:
        """
        Get exchange token for a pSymbol.
        
        Args:
            psymbol: pSymbol from instrument master (e.g., 'RELIANCE-EQ')
            
        Returns:
            Exchange token as string (e.g., '2885'), None if not found
        """
        # Try database first
        if self.db:
            try:
                from sqlalchemy import text
                with self.db.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT psymbol 
                        FROM kotak_instruments 
                        WHERE trading_symbol = :psymbol 
                        LIMIT 1
                    """), {'psymbol': psymbol})
                    row = result.fetchone()
                    if row:
                        return str(row[0])
            except Exception as e:
                self.logger(f"Database lookup failed for {psymbol}: {e}", "DEBUG")
        
        # Fallback to in-memory instrument master
        if hasattr(self, '_instrument_master') and self._instrument_master:
            for inst in self._instrument_master:
                inst_psymbol = inst.get('pSymbol') or inst.get('tradingsymbol')
                if inst_psymbol == psymbol:
                    # Try different field names for token
                    token = inst.get('pTrdSymbol') or inst.get('exchange_token') or inst.get('token')
                    if token:
                        return str(token)
        
        return None
    
    def load_instruments(self, symbols: List[str]) -> Dict[str, int]:
        """
        Load instrument tokens for given symbols.
        
        For REST API mode, we use the symbol names directly.
        Returns a mapping of symbol -> hash(symbol) as token.
        
        Args:
            symbols: List of trading symbols (base names like 'RELIANCE', 'INFY')
            
        Returns:
            Dictionary mapping symbols to instrument tokens
        """
        try:
            self.logger("Loading instruments for REST API mode...", "INFO")
            
            # Instrument master should already be fetched during authentication
            # If not, log a warning
            if not hasattr(self, '_instrument_master'):
                self.logger("WARNING: Instrument master not loaded yet", "WARNING")
            
            # For REST API, we don't need actual tokens from API
            # We'll use symbol names in the queries
            # Create simple hash-based tokens for internal use
            symbol_to_token = {}
            for symbol in symbols:
                # Create a numeric token from symbol hash
                token = hash(symbol) % (10 ** 8)
                symbol_to_token[symbol] = token
                
                # Store multiple mappings for this token:
                # 1. Base symbol (RELIANCE)
                self._token_to_symbol[token] = symbol
                
                # 2. Try to find pSymbol from instrument master
                psymbol = self.find_psymbol(symbol)
                if psymbol:
                    if not hasattr(self, '_symbol_variants'):
                        self._symbol_variants = {}
                    self._symbol_variants[psymbol] = token
                    self.logger(f"Mapped {symbol} -> {psymbol} (token: {token})", "INFO")
                else:
                    # 3. Fallback: With -EQ suffix (RELIANCE-EQ) for NSE equity
                    if not symbol.endswith('-EQ'):
                        eq_symbol = f"{symbol}-EQ"
                        if not hasattr(self, '_symbol_variants'):
                            self._symbol_variants = {}
                        self._symbol_variants[eq_symbol] = token
                        self.logger(f"No pSymbol found, using fallback {symbol} -> {eq_symbol} (token: {token})", "INFO")
            
            self.logger(f"Loaded {len(symbol_to_token)} instruments", "SUCCESS")
            self.logger(f"Symbol mappings: {symbol_to_token}", "INFO")
            if hasattr(self, '_symbol_variants'):
                self.logger(f"Symbol variants: {self._symbol_variants}", "INFO")
            return symbol_to_token
            
        except Exception as e:
            self.logger(f"Error loading instruments: {e}", "ERROR")
            return {}
    
    def get_subscribed_symbols(self) -> List[str]:
        """
        Get list of currently subscribed symbols.
        
        Returns:
            List of symbol names
        """
        symbols = []
        for token in self._instruments:
            symbol = self._token_to_symbol.get(token)
            if symbol:
                symbols.append(symbol)
        return symbols
    
    def poll_quotes(self) -> bool:
        """
        Poll quotes for all subscribed instruments and trigger callbacks.
        
        This method should be called periodically by the service (e.g., every 30 seconds).
        
        Returns:
            True if polling successful, False otherwise
        """
        try:
            symbols = self.get_subscribed_symbols()
            
            if not symbols:
                return True  # No symbols to poll
            
            # Fetch quotes
            quotes = self.fetch_quotes(symbols)
            
            if not quotes:
                return False
            
            # Convert to TickData and trigger callback
            if self._tick_callback:
                tick_data_list = []
                for quote in quotes:
                    tick = self.convert_quote_to_tick(quote)
                    if tick:
                        tick_data_list.append(tick)
                
                if tick_data_list:
                    self._tick_callback(tick_data_list)
                    return True
            
            return True
            
        except Exception as e:
            self.logger(f"Error polling quotes: {e}", "ERROR")
            return False
    
    # WebSocket callbacks (not used in REST API mode, kept for interface compatibility)
    
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
