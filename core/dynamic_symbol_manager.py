"""
Dynamic Symbol Manager for broker data feed service.

Monitors a configuration file for new symbols and manages their addition
to the live data feed, including historical data verification and backfill.
"""
import os
import time
import threading
from typing import List, Dict, Set, Optional, Callable
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import text
import json

from core.database_handler import DatabaseHandler


class DynamicSymbolManager:
    """
    Manages dynamic addition of symbols to the data feed.
    
    Monitors a config file for new symbols, verifies historical data availability,
    and coordinates gap-filling before starting live tracking.
    """
    
    def __init__(
        self,
        config_file: str,
        db_handler: DatabaseHandler,
        broker,
        on_symbols_added: Optional[Callable] = None,
        logger=None
    ):
        """
        Initialize dynamic symbol manager.
        
        Args:
            config_file: Path to symbols configuration file (JSON format)
            db_handler: Database handler instance
            broker: Broker instance for instrument token resolution
            on_symbols_added: Callback when new symbols are added (receives symbol_to_token dict)
            logger: Optional logging function
        """
        self.config_file = Path(config_file)
        self.db = db_handler
        self.broker = broker
        self.on_symbols_added = on_symbols_added
        self.logger = logger or self._default_logger
        
        # Tracking
        self._current_symbols: Set[str] = set()
        self._file_mtime: Optional[float] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Historical data requirements
        self.min_historical_date = datetime(2024, 1, 1)  # Data should exist from 2024
        
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def load_symbols_from_config(self) -> Set[str]:
        """
        Load symbols from configuration file.
        
        Expected YAML format:
        symbols:
          - RELIANCE
          - INFY
          - TCS
        enabled: true
        
        Or JSON format:
        {
            "symbols": ["RELIANCE", "INFY", "TCS"],
            "enabled": true
        }
        
        Or simple text format (one symbol per line).
        
        Returns:
            Set of symbols
        """
        if not self.config_file.exists():
            self.logger(f"Config file not found: {self.config_file}", "WARNING")
            return set()
        
        try:
            content = self.config_file.read_text().strip()
            
            # Try YAML format first (most common for this project)
            if content.startswith('symbols:') or content.startswith('#'):
                import yaml
                data = yaml.safe_load(content)
                if data and 'symbols' in data:
                    symbols = set(data['symbols'])
                    self.logger(f"Loaded {len(symbols)} symbols from YAML config", "INFO")
                    return symbols
            
            # Try JSON format
            elif content.startswith('{'):
                data = json.loads(content)
                if 'symbols' in data:
                    symbols = set(data['symbols'])
                    self.logger(f"Loaded {len(symbols)} symbols from JSON config", "INFO")
                    return symbols
            
            # Fallback to text format (one symbol per line)
            symbols = set(line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#'))
            self.logger(f"Loaded {len(symbols)} symbols from text config", "INFO")
            return symbols
            
        except Exception as e:
            self.logger(f"Error reading config file: {e}", "ERROR")
            return set()
    
    def initialize(self, initial_symbols: List[str]):
        """
        Initialize with current symbols being tracked.
        
        Args:
            initial_symbols: List of symbols currently in the data feed
        """
        self._current_symbols = set(initial_symbols)
        self.logger(f"Initialized with {len(self._current_symbols)} symbols", "INFO")
        
        # Create config file if it doesn't exist
        if not self.config_file.exists():
            self._create_default_config(initial_symbols)
    
    def _create_default_config(self, symbols: List[str]):
        """Create default config file with current symbols."""
        try:
            import yaml
            config_data = {
                "symbols": sorted(symbols),
                "enabled": True,
                "last_updated": datetime.now().isoformat(),
                "description": "Symbol configuration for broker data feed. Add or remove symbols to dynamically manage subscriptions."
            }
            
            self.config_file.write_text(yaml.dump(config_data, default_flow_style=False, sort_keys=False))
            self.logger(f"Created default config file: {self.config_file}", "INFO")
            
        except Exception as e:
            self.logger(f"Error creating config file: {e}", "ERROR")
    
    def verify_instrument_token(self, symbol: str) -> Optional[int]:
        """
        Verify that symbol has an instrument token in the database.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Instrument token if found, None otherwise
        """
        try:
            # Check instruments table (for Kite)
            query = text("""
                SELECT instrument_token
                FROM instruments
                WHERE tradingsymbol = :symbol
                LIMIT 1
            """)
            
            with self.db.engine.connect() as conn:
                result = conn.execute(query, {"symbol": symbol}).fetchone()
                
                if result:
                    return int(result[0])
            
            # Check kotak_instruments table (for Kotak)
            query = text("""
                SELECT psymbol
                FROM kotak_instruments
                WHERE trading_symbol = :symbol
                   OR trading_symbol = :symbol || '-EQ'
                   OR trading_symbol = :symbol || '-BL'
                LIMIT 1
            """)
            
            with self.db.engine.connect() as conn:
                result = conn.execute(query, {"symbol": symbol}).fetchone()
                
                if result:
                    return int(result[0])
            
            self.logger(f"Instrument token not found for {symbol}", "ERROR")
            return None
            
        except Exception as e:
            self.logger(f"Error verifying instrument token for {symbol}: {e}", "ERROR")
            return None
    
    def verify_historical_data(self, symbol: str, min_date: Optional[datetime] = None) -> Dict[str, any]:
        """
        Verify if historical data exists for a symbol.
        
        Args:
            symbol: Trading symbol
            min_date: Minimum date from which data should exist (default: 2024-01-01)
            
        Returns:
            Dictionary with:
                - has_data: Boolean
                - earliest_date: Earliest available date
                - latest_date: Latest available date
                - record_count: Number of records
                - intervals: List of intervals with data
        """
        if min_date is None:
            min_date = self.min_historical_date
        
        result = {
            'has_data': False,
            'earliest_date': None,
            'latest_date': None,
            'record_count': 0,
            'intervals': []
        }
        
        try:
            # Check each historical table
            for interval in [5, 15, 60]:
                table_name = f'historical_{interval}min'
                
                if not self.db.check_table_exists(table_name):
                    continue
                
                query = text(f"""
                    SELECT 
                        MIN(datetime) as earliest,
                        MAX(datetime) as latest,
                        COUNT(*) as count
                    FROM {table_name}
                    WHERE tradingsymbol = :symbol
                """)
                
                with self.db.engine.connect() as conn:
                    row = conn.execute(query, {"symbol": symbol}).fetchone()
                    
                    if row and row[2] > 0:  # Has records
                        earliest = row[0]
                        latest = row[1]
                        count = row[2]
                        
                        result['intervals'].append({
                            'interval': interval,
                            'earliest_date': earliest,
                            'latest_date': latest,
                            'record_count': count
                        })
                        
                        # Update overall stats
                        if result['earliest_date'] is None or earliest < result['earliest_date']:
                            result['earliest_date'] = earliest
                        
                        if result['latest_date'] is None or latest > result['latest_date']:
                            result['latest_date'] = latest
                        
                        result['record_count'] += count
            
            # Check if data meets minimum date requirement
            if result['earliest_date'] and result['earliest_date'] <= min_date:
                result['has_data'] = True
            
            return result
            
        except Exception as e:
            self.logger(f"Error verifying historical data for {symbol}: {e}", "ERROR")
            return result
    
    def fetch_historical_data_for_symbol(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> bool:
        """
        Fetch historical data for a symbol using nse_cli.py.
        
        Args:
            symbol: Trading symbol
            start_date: Start date (default: 2024-01-01)
            end_date: End date (default: today)
            
        Returns:
            True if successful, False otherwise
        """
        import sys
        import subprocess
        
        if start_date is None:
            start_date = self.min_historical_date
        
        if end_date is None:
            end_date = datetime.now()
        
        self.logger(f"Fetching historical data for {symbol} from {start_date.date()} to {end_date.date()}", "INFO")
        
        # Path to nse_cli.py
        trading_v2_path = Path(__file__).parent.parent.parent / "Trading-V2"
        nse_cli_path = trading_v2_path / "nse_cli.py"
        
        if not nse_cli_path.exists():
            self.logger(f"nse_cli.py not found at {nse_cli_path}", "ERROR")
            return False
        
        # Fetch for all intervals
        for interval in ['5', '15', 'hourly']:
            try:
                cmd = [
                    sys.executable,
                    str(nse_cli_path),
                    '--mode', 'data',
                    '--interval', interval,
                    '--symbol', symbol,
                    '--start_date', start_date.strftime('%Y-%m-%d'),
                    '--end_date', end_date.strftime('%Y-%m-%d'),
                    '--run_id', f'NEWSYM_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                ]
                
                self.logger(f"Fetching {interval} data for {symbol}...", "INFO")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes
                )
                
                if result.returncode != 0:
                    self.logger(f"Failed to fetch {interval} data: {result.stderr}", "ERROR")
                    return False
                
                self.logger(f"Successfully fetched {interval} data for {symbol}", "SUCCESS")
                
            except Exception as e:
                self.logger(f"Error fetching {interval} data for {symbol}: {e}", "ERROR")
                return False
        
        return True
    
    def add_symbol(self, symbol: str) -> bool:
        """
        Add a new symbol to the data feed.
        
        Complete workflow:
        1. Verify instrument token exists
        2. Check historical data availability
        3. Fetch historical data if missing
        4. Perform gap-fill for today's data
        5. Notify callback to start live tracking
        
        Args:
            symbol: Trading symbol to add
            
        Returns:
            True if successful, False otherwise
        """
        self.logger(f"Adding new symbol: {symbol}", "INFO")
        
        # Step 1: Verify instrument token
        instrument_token = self.verify_instrument_token(symbol)
        if not instrument_token:
            self.logger(f"Cannot add {symbol}: Instrument token not found", "ERROR")
            return False
        
        self.logger(f"Instrument token verified: {symbol} = {instrument_token}", "SUCCESS")
        
        # Step 2: Check historical data
        hist_check = self.verify_historical_data(symbol)
        
        if not hist_check['has_data']:
            self.logger(f"No historical data found for {symbol} (required from 2024)", "WARNING")
            self.logger(f"Fetching historical data for {symbol}...", "INFO")
            
            # Step 3: Fetch historical data
            if not self.fetch_historical_data_for_symbol(symbol):
                self.logger(f"Failed to fetch historical data for {symbol}", "ERROR")
                return False
            
            self.logger(f"Historical data fetched for {symbol}", "SUCCESS")
        else:
            self.logger(f"Historical data exists for {symbol}:", "INFO")
            self.logger(f"  Earliest: {hist_check['earliest_date']}", "INFO")
            self.logger(f"  Latest: {hist_check['latest_date']}", "INFO")
            self.logger(f"  Records: {hist_check['record_count']}", "INFO")
        
        # Step 4: Perform gap-fill for today's data (if market is open)
        from core.startup_gap_fill import StartupGapFiller
        
        gap_filler = StartupGapFiller(self.db, logger=self.logger)
        gap_check = gap_filler.should_perform_gap_fill()
        
        if gap_check['needs_fill']:
            self.logger(f"Performing gap-fill for {symbol} (today's data)", "INFO")
            gap_filler.perform_gap_fill([symbol], intervals=[5, 15, 60])
        
        # Step 5: Notify callback to start live tracking
        if self.on_symbols_added:
            symbol_to_token = {symbol: instrument_token}
            self.logger(f"Notifying data feed to start tracking {symbol}", "INFO")
            self.on_symbols_added(symbol_to_token)
        
        # Update current symbols
        self._current_symbols.add(symbol)
        
        self.logger(f"Successfully added {symbol} to data feed", "SUCCESS")
        return True
    
    def check_for_new_symbols(self) -> List[str]:
        """
        Check config file for new symbols.
        
        Returns:
            List of new symbols to add
        """
        # Check if file was modified
        try:
            current_mtime = self.config_file.stat().st_mtime
            
            if self._file_mtime is None:
                self._file_mtime = current_mtime
                return []
            
            if current_mtime == self._file_mtime:
                return []  # No changes
            
            self._file_mtime = current_mtime
            
        except Exception as e:
            self.logger(f"Error checking config file modification: {e}", "ERROR")
            return []
        
        # Load symbols from config
        config_symbols = self.load_symbols_from_config()
        
        # Find new symbols
        new_symbols = config_symbols - self._current_symbols
        
        if new_symbols:
            self.logger(f"Detected {len(new_symbols)} new symbols: {new_symbols}", "INFO")
        
        return list(new_symbols)
    
    def start_monitoring(self, check_interval: int = 30):
        """
        Start monitoring config file for changes.
        
        Args:
            check_interval: How often to check file (seconds)
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            self.logger("Monitor thread already running", "WARNING")
            return
        
        self.logger(f"Starting config file monitor (checking every {check_interval}s)", "INFO")
        self.logger(f"Monitoring: {self.config_file}", "INFO")
        
        def monitor_loop():
            while not self._stop_event.is_set():
                try:
                    new_symbols = self.check_for_new_symbols()
                    
                    for symbol in new_symbols:
                        try:
                            self.add_symbol(symbol)
                        except Exception as e:
                            self.logger(f"Error adding symbol {symbol}: {e}", "ERROR")
                    
                except Exception as e:
                    self.logger(f"Error in monitor loop: {e}", "ERROR")
                
                # Wait for next check
                self._stop_event.wait(check_interval)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        self.logger("Config file monitor started", "SUCCESS")
    
    def stop_monitoring(self):
        """Stop monitoring config file."""
        if not self._monitor_thread or not self._monitor_thread.is_alive():
            return
        
        self.logger("Stopping config file monitor...", "INFO")
        self._stop_event.set()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        self.logger("Config file monitor stopped", "INFO")
