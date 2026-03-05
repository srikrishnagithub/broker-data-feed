"""
Startup gap-fill module for broker data feed service.

Handles complete historical data management:
1. Checks if historical data exists up to previous day
2. Fetches missing historical data automatically
3. Handles intraday gaps (during market hours)
4. Handles after-market gaps (fetch today's data and migrate)
"""
import os
import sys
import subprocess
from typing import List, Dict, Optional, Tuple
from datetime import datetime, time, timedelta, date
from pathlib import Path
from sqlalchemy import text

from core.database_handler import DatabaseHandler


class StartupGapFiller:
    """
    Manages comprehensive historical data gap-filling on startup.
    
    Automatically:
    - Checks historical data completeness (up to yesterday)
    - Fetches missing historical data via nse_cli.py
    - Handles intraday gaps (during market hours)
    - Handles after-market gaps (fetch today's full data and migrate)
    """
    
    # NSE market hours (IST)
    MARKET_OPEN_TIME = time(9, 10, 0)  # 9:10 AM
    MARKET_CLOSE_TIME = time(15, 30, 0)  # 3:30 PM
    
    def __init__(self, db_handler: DatabaseHandler, logger=None):
        """
        Initialize gap filler.
        
        Args:
            db_handler: Database handler instance
            logger: Optional logging function
        """
        self.db = db_handler
        
        # Path to nse_cli.py
        self.nse_cli_path = Path(__file__).parent.parent.parent / "Trading-V2" / "nse_cli.py"
        self.logger = logger or self._default_logger
        
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    @property
    def MIN_HISTORICAL_DATE(self) -> date:
        """
        Calculate minimum historical date dynamically as one year prior to current date.
        
        Returns:
            Date object representing one year ago from today
        """
        return (datetime.now().date() - timedelta(days=365))
    
    def is_market_hours(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if given time is within market hours.
        
        Args:
            check_time: Time to check (default: current time)
            
        Returns:
            True if within market hours, False otherwise
        """
        if check_time is None:
            check_time = datetime.now()
        
        # Check if weekday
        if check_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check time range
        current_time = check_time.time()
        return self.MARKET_OPEN_TIME <= current_time <= self.MARKET_CLOSE_TIME
    
    def should_perform_gap_fill(self) -> Dict[str, any]:
        """
        Determine if gap-fill is needed based on current time and existing data.
        
        Returns:
            Dictionary with:
                - needs_fill: Boolean indicating if gap-fill is needed
                - reason: String explaining why
                - market_open_today: DateTime of today's market open
                - current_time: Current datetime
        """
        now = datetime.now()
        
        # Check if currently in market hours
        if not self.is_market_hours(now):
            return {
                'needs_fill': False,
                'reason': 'Not in market hours',
                'market_open_today': None,
                'current_time': now
            }
        
        # Market open time for today
        market_open_today = datetime.combine(now.date(), self.MARKET_OPEN_TIME)
        
        # Check if we started after market open
        if now <= market_open_today:
            return {
                'needs_fill': False,
                'reason': 'Started before or at market open',
                'market_open_today': market_open_today,
                'current_time': now
            }
        
        # Check time difference
        time_diff = now - market_open_today
        
        # If started more than 5 minutes after market open, we need gap-fill
        if time_diff.total_seconds() > 300:  # 5 minutes
            return {
                'needs_fill': True,
                'reason': f'Started {time_diff.total_seconds()/60:.1f} minutes after market open',
                'market_open_today': market_open_today,
                'current_time': now
            }
        
        return {
            'needs_fill': False,
            'reason': 'Started within 5 minutes of market open',
            'market_open_today': market_open_today,
            'current_time': now
        }
    
    def fetch_historical_data(
        self,
        symbols: List[str],
        start_time: datetime,
        end_time: datetime,
        intervals: List[int] = [5, 15, 60]
    ) -> Dict[str, any]:
        """
        Fetch historical data using nse_cli.py from Trading-V2.
        
        Args:
            symbols: List of symbols to fetch
            start_time: Start datetime
            end_time: End datetime
            intervals: List of intervals to fetch (default: [5, 15, 60])
            
        Returns:
            Dictionary with fetch results
        """
        self.logger(f"Fetching historical data for {len(symbols)} symbols", "INFO")
        self.logger(f"Time range: {start_time} to {end_time}", "INFO")
        
        # Path to nse_cli.py in Trading-V2
        trading_v2_path = Path(__file__).parent.parent.parent / "Trading-V2"
        nse_cli_path = trading_v2_path / "nse_cli.py"
        
        if not nse_cli_path.exists():
            self.logger(f"nse_cli.py not found at {nse_cli_path}", "ERROR")
            return {'success': False, 'error': 'nse_cli.py not found'}
        
        results = {}
        
        # Map intervals to nse_cli interval names
        interval_map = {
            5: '5',
            15: '15',
            60: 'hourly'
        }
        
        for interval in intervals:
            interval_name = interval_map.get(interval, '15')
            
            self.logger(f"Fetching {interval}-minute candles...", "INFO")

            self.logger(f"Processing configured symbols list ({len(symbols)} symbols)", "INFO")

            interval_success = True
            for symbol in symbols:
                try:
                    self._fetch_single_symbol(
                        nse_cli_path,
                        symbol,
                        start_time,
                        end_time,
                        interval_name
                    )
                except Exception as e:
                    self.logger(f"Error fetching {symbol}: {e}", "ERROR")
                    interval_success = False

            results[interval] = {'success': interval_success}
        
        return results
    
    def _fetch_single_symbol(
        self,
        nse_cli_path: Path,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str
    ):
        """Fetch historical data for a single symbol."""
        cli_cwd = str(nse_cli_path.parent)
        venv_python = nse_cli_path.parent / "venv" / "Scripts" / "python.exe"
        python_exe = os.getenv("TRADING_V2_PYTHON") or (str(venv_python) if venv_python.exists() else sys.executable)
        cmd = [
            python_exe,
            str(nse_cli_path),
            '--mode', 'data',
            '--interval', interval,
            '--symbol', symbol,
            '--start_date', start_time.strftime('%Y-%m-%d'),
            '--end_date', end_time.strftime('%Y-%m-%d'),
            '--run_id', f'GAPFILL_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        ]
        
        self.logger(f"Executing: {' '.join(cmd)}", "DEBUG")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cli_cwd,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode != 0:
            error_output = (result.stderr or result.stdout or "").strip()
            self.logger(f"nse_cli.py failed for {symbol}: {error_output}", "ERROR")
            raise RuntimeError(f"Failed to fetch {symbol}")
        
        self.logger(f"Successfully fetched {symbol} {interval} data", "SUCCESS")
    
    def _fetch_all_symbols(
        self,
        nse_cli_path: Path,
        start_time: datetime,
        end_time: datetime,
        interval: str
    ):
        """Fetch historical data for all symbols."""
        cli_cwd = str(nse_cli_path.parent)
        venv_python = nse_cli_path.parent / "venv" / "Scripts" / "python.exe"
        python_exe = os.getenv("TRADING_V2_PYTHON") or (str(venv_python) if venv_python.exists() else sys.executable)
        cmd = [
            python_exe,
            str(nse_cli_path),
            '--mode', 'data',
            '--interval', interval,
            '--start_date', start_time.strftime('%Y-%m-%d'),
            '--end_date', end_time.strftime('%Y-%m-%d'),
            '--run_id', f'GAPFILL_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        ]
        
        self.logger(f"Executing: {' '.join(cmd)}", "DEBUG")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cli_cwd,
            timeout=600  # 10 minutes timeout for all symbols
        )
        
        if result.returncode != 0:
            error_output = (result.stderr or result.stdout or "").strip()
            self.logger(f"nse_cli.py failed: {error_output}", "ERROR")
            raise RuntimeError("Failed to fetch historical data")
        
        self.logger(f"Successfully fetched {interval} data for all symbols", "SUCCESS")
    
    def migrate_to_live_tables(
        self,
        date_str: str,
        time_str: str,
        intervals: List[int] = [5, 15, 60]
    ) -> Dict[int, int]:
        """
        Migrate historical data to live tables using existing migration logic.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM:SS format
            intervals: List of intervals to migrate
            
        Returns:
            Dictionary mapping interval to number of records migrated
        """
        from scripts.migrate_historical_to_live import migrate_historical_to_live
        
        results = {}
        
        for interval in intervals:
            self.logger(f"Migrating {interval}min candles to live tables...", "INFO")
            
            try:
                count = migrate_historical_to_live(
                    db_handler=self.db,
                    date_str=date_str,
                    time_str=time_str,
                    interval=interval,
                    logger=self.logger,
                    on_duplicate='update'
                )
                
                results[interval] = count
                self.logger(f"Migrated {count} records for {interval}min", "SUCCESS")
                
            except Exception as e:
                self.logger(f"Error migrating {interval}min: {e}", "ERROR")
                results[interval] = 0
        
        return results
    
    def check_historical_data_completeness(
        self,
        symbols: List[str],
        intervals: List[int] = [5, 15, 60]
    ) -> Dict[str, any]:
        """
        Check if historical data exists up to yesterday for all symbols and intervals.
        
        Args:
            symbols: List of symbols to check
            intervals: List of intervals to check
            
        Returns:
            Dictionary with:
                - has_complete_data: Boolean
                - missing_ranges: List of (start_date, end_date) tuples
                - latest_date: Latest date with data
                - symbols_checked: Number of symbols checked
        """
        self.logger("Checking historical data completeness...", "INFO")
        
        yesterday = date.today() - timedelta(days=1)
        
        try:
            # Check each interval
            missing_ranges = []
            latest_dates = []
            missing_symbols_by_table = {}
            all_missing_symbols = set()
            
            for interval in intervals:
                table_name = f'historical_{interval}min'
                
                if not self.db.check_table_exists(table_name):
                    self.logger(f"Table {table_name} does not exist", "WARNING")
                    missing_symbols_by_table[table_name] = list(symbols)
                    all_missing_symbols.update(symbols)
                    missing_ranges.append((self.MIN_HISTORICAL_DATE, yesterday))
                    continue
                
                # Get latest date per symbol
                query = text(f"""
                    SELECT tradingsymbol, MAX(DATE(datetime)) as latest_date
                    FROM {table_name}
                    WHERE tradingsymbol = ANY(:symbols)
                    GROUP BY tradingsymbol
                """)
                
                with self.db.engine.connect() as conn:
                    rows = conn.execute(query, {"symbols": symbols}).fetchall()
                    
                    if rows:
                        latest_by_symbol = {row[0]: row[1] for row in rows if row[1]}
                        symbols_with_data = set(latest_by_symbol.keys())
                        missing_symbols = [s for s in symbols if s not in symbols_with_data]
                        
                        latest_dates_for_interval = [d for d in latest_by_symbol.values() if d]
                        min_latest = min(latest_dates_for_interval) if latest_dates_for_interval else None
                        max_latest = max(latest_dates_for_interval) if latest_dates_for_interval else None
                        
                        if min_latest:
                            latest_dates.append(min_latest)
                            self.logger(
                                f"{table_name}: Latest data range = {min_latest} to {max_latest}",
                                "INFO"
                            )
                        else:
                            self.logger(f"{table_name}: No valid dates found", "WARNING")
                        
                        if missing_symbols:
                            missing_symbols_by_table[table_name] = missing_symbols
                            all_missing_symbols.update(missing_symbols)
                            preview = ', '.join(missing_symbols[:10])
                            suffix = '...' if len(missing_symbols) > 10 else ''
                            self.logger(
                                f"{table_name}: Missing data for {len(missing_symbols)} symbols [{preview}{suffix}]",
                                "WARNING"
                            )
                            missing_ranges.append((self.MIN_HISTORICAL_DATE, yesterday))
                        
                        # Check if all symbols are up to yesterday
                        # Convert to dates to avoid timezone comparison issues
                        min_latest_date = min_latest.date() if min_latest and hasattr(min_latest, 'date') else min_latest
                        if min_latest_date is None or min_latest_date < yesterday:
                            gap_start = (min_latest + timedelta(days=1)) if min_latest else self.MIN_HISTORICAL_DATE
                            missing_ranges.append((gap_start, yesterday))
                            self.logger(f"  Missing data from {gap_start} to {yesterday}", "WARNING")
                    else:
                        self.logger(f"{table_name}: No data found", "WARNING")
                        missing_symbols_by_table[table_name] = list(symbols)
                        all_missing_symbols.update(symbols)
                        missing_ranges.append((self.MIN_HISTORICAL_DATE, yesterday))
            
            # Determine if complete
            has_complete_data = len(missing_ranges) == 0
            latest_date = min(latest_dates) if latest_dates else None
            
            return {
                'has_complete_data': has_complete_data,
                'missing_ranges': missing_ranges,
                'latest_date': latest_date,
                'symbols_checked': len(symbols),
                'yesterday': yesterday,
                'missing_symbols': sorted(all_missing_symbols),
                'missing_symbols_by_table': missing_symbols_by_table
            }
            
        except Exception as e:
            self.logger(f"Error checking historical data: {e}", "ERROR")
            return {
                'has_complete_data': False,
                'missing_ranges': [(self.MIN_HISTORICAL_DATE, yesterday)],
                'latest_date': None,
                'symbols_checked': len(symbols),
                'yesterday': yesterday,
                'missing_symbols': [],
                'missing_symbols_by_table': {}
            }
    
    def fetch_missing_historical_data(
        self,
        start_date: date,
        end_date: date,
        symbols: Optional[List[str]] = None
    ) -> bool:
        """
        Fetch missing historical data using nse_cli.py.
        
        Args:
            start_date: Start date for fetch
            end_date: End date for fetch
            symbols: Optional list of specific symbols (None = all from DB)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.nse_cli_path.exists():
            self.logger(f"nse_cli.py not found at {self.nse_cli_path}", "ERROR")
            self.logger("Please ensure Trading-V2 is in the correct location", "ERROR")
            return False
        
        self.logger(f"Fetching historical data from {start_date} to {end_date}", "INFO")
        
        try:
            cli_cwd = str(self.nse_cli_path.parent)
            venv_python = self.nse_cli_path.parent / "venv" / "Scripts" / "python.exe"
            python_exe = os.getenv("TRADING_V2_PYTHON") or (str(venv_python) if venv_python.exists() else sys.executable)
            cmd = [
                python_exe,
                str(self.nse_cli_path),
                '--mode', 'data',
                '--interval', 'both',  # Fetch all intervals
                '--start_date', start_date.strftime('%Y-%m-%d'),
                '--end_date', end_date.strftime('%Y-%m-%d'),
                '--run_id', f'AUTOFILL_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            ]
            
            if symbols:
                # Process only requested symbols (strict symbols list mode)
                failed_symbols = []
                for symbol in symbols:
                    symbol_cmd = cmd + ['--symbol', symbol]
                    self.logger(f"Fetching {symbol}...", "INFO")
                    
                    result = subprocess.run(
                        symbol_cmd,
                        capture_output=True,
                        text=True,
                        cwd=cli_cwd,
                        timeout=600
                    )
                    
                    if result.returncode != 0:
                        error_output = (result.stderr or result.stdout or "").strip()
                        self.logger(f"Warning: Failed to fetch {symbol}: {error_output}", "WARNING")
                        failed_symbols.append(symbol)

                success_count = len(symbols) - len(failed_symbols)
                self.logger(
                    f"Historical data fetch completed for {start_date} to {end_date} "
                    f"(success: {success_count}, failed: {len(failed_symbols)})",
                    "SUCCESS"
                )
                if failed_symbols:
                    self.logger(
                        f"Failed symbols: {', '.join(failed_symbols[:10])}{'...' if len(failed_symbols) > 10 else ''}",
                        "WARNING"
                    )
            else:
                # Fetch all symbols at once
                self.logger(f"Executing: {' '.join(cmd)}", "DEBUG")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=cli_cwd,
                    timeout=1800  # 30 minutes for large fetches
                )
                
                if result.returncode != 0:
                    error_output = (result.stderr or result.stdout or "").strip()
                    self.logger(f"nse_cli.py failed: {error_output}", "ERROR")
                    return False
                
                self.logger(
                    f"Historical data fetch completed for {start_date} to {end_date}",
                    "SUCCESS"
                )
            
            return True
            
        except subprocess.TimeoutExpired:
            self.logger("Historical data fetch timed out", "ERROR")
            return False
        except Exception as e:
            self.logger(f"Error fetching historical data: {e}", "ERROR")
            return False
    
    def handle_after_market_hours(
        self,
        symbols: List[str],
        intervals: List[int] = [5, 15, 60]
    ) -> bool:
        """
        Handle scenario when starting after market hours.
        
        Fetches today's complete data and migrates to live tables.
        
        Args:
            symbols: List of symbols
            intervals: List of intervals
            
        Returns:
            True if successful
        """
        today = date.today()
        
        self.logger("After market hours detected - fetching today's complete data", "INFO")
        
        # Fetch today's data (goes to historical tables)
        if not self.fetch_missing_historical_data(today, today, symbols):
            self.logger("Failed to fetch today's data", "ERROR")
            return False
        
        # Wait a moment for data to be written
        import time
        time.sleep(3)
        
        # Migrate to live tables
        from scripts.migrate_historical_to_live import migrate_historical_to_live
        
        for interval in intervals:
            self.logger(f"Migrating today's {interval}min data to live tables...", "INFO")
            
            try:
                count = migrate_historical_to_live(
                    db_handler=self.db,
                    date_str=today.strftime('%Y-%m-%d'),
                    time_str='15:30:00',  # Full day up to market close
                    interval=interval,
                    logger=self.logger,
                    on_duplicate='update'
                )
                
                self.logger(f"Migrated {count} records for {interval}min", "SUCCESS")
                
            except Exception as e:
                self.logger(f"Error migrating {interval}min: {e}", "ERROR")
        
        return True
    
    def perform_comprehensive_gap_fill(
        self,
        symbols: List[str],
        intervals: List[int] = [5, 15, 60]
    ) -> bool:
        """
        Perform comprehensive gap-fill (MAIN ENTRY POINT).
        
        This is the main method that handles all scenarios:
        1. Check historical data completeness (up to yesterday)
        2. Fetch missing historical data
        3. Handle today's data (intraday or after-market)
        
        Args:
            symbols: List of symbols to process
            intervals: List of intervals to process
            
        Returns:
            True if successful
        """
        self.logger("="*80, "INFO")
        self.logger("COMPREHENSIVE DATA GAP-FILL", "INFO")
        self.logger("="*80, "INFO")
        
        # Step 1: Check historical data completeness (up to yesterday)
        hist_check = self.check_historical_data_completeness(symbols, intervals)
        
        if not hist_check['has_complete_data']:
            self.logger("Historical data is incomplete!", "WARNING")
            missing_symbols = hist_check.get('missing_symbols', [])
            if missing_symbols:
                preview = ', '.join(missing_symbols[:20])
                suffix = '...' if len(missing_symbols) > 20 else ''
                self.logger(
                    f"Missing symbols ({len(missing_symbols)}): {preview}{suffix}",
                    "WARNING"
                )
            self.logger(f"Latest data: {hist_check['latest_date']}", "INFO")
            self.logger(f"Expected up to: {hist_check['yesterday']}", "INFO")
            
            # Fetch missing historical data
            unique_ranges = []
            seen_ranges = set()
            for start_date, end_date in hist_check['missing_ranges']:
                key = (start_date, end_date)
                if key not in seen_ranges:
                    seen_ranges.add(key)
                    unique_ranges.append(key)

            for start_date, end_date in unique_ranges:
                self.logger(f"Fetching missing data: {start_date} to {end_date}", "INFO")
                
                if not self.fetch_missing_historical_data(start_date, end_date, symbols):
                    self.logger("Failed to fetch some historical data (continuing anyway)", "WARNING")
        else:
            self.logger("Historical data is complete up to yesterday", "SUCCESS")
        
        # Step 2: Handle today's data
        now = datetime.now()
        today = now.date()
        current_time = now.time()
        
        # Check if we're past market close
        if current_time > self.MARKET_CLOSE_TIME:
            self.logger("Past market close - fetching today's complete data", "INFO")
            return self.handle_after_market_hours(symbols, intervals)
        
        # Check if we're in market hours
        elif self.MARKET_OPEN_TIME <= current_time <= self.MARKET_CLOSE_TIME:
            # Check if it's a weekday
            if now.weekday() < 5:
                self.logger("During market hours - performing intraday gap-fill", "INFO")
                return self.perform_gap_fill(symbols, intervals)
            else:
                self.logger("Weekend - no intraday gap-fill needed", "INFO")
                return True
        
        else:
            self.logger("Before market open - no today's data fetch needed", "INFO")
            return True
    
    def perform_gap_fill(self, symbols: List[str], intervals: List[int] = [5, 15, 60]) -> bool:
        """
        Perform complete gap-fill process.
        
        1. Check if gap-fill is needed
        2. Fetch historical data from market open to current time
        3. Migrate to live tables
        4. Repeat until caught up
        
        Args:
            symbols: List of symbols to process
            intervals: List of intervals to process
            
        Returns:
            True if successful, False otherwise
        """
        self.logger("="*80, "INFO")
        self.logger("STARTUP GAP-FILL PROCESS", "INFO")
        self.logger("="*80, "INFO")
        
        # Check if gap-fill is needed
        gap_check = self.should_perform_gap_fill()
        
        if not gap_check['needs_fill']:
            self.logger(f"Gap-fill not needed: {gap_check['reason']}", "INFO")
            return True
        
        self.logger(f"Gap-fill needed: {gap_check['reason']}", "INFO")
        
        market_open = gap_check['market_open_today']
        current_time = gap_check['current_time']
        
        # Round current time down to nearest 5-minute boundary
        current_minutes = (current_time.minute // 5) * 5
        fill_until_time = current_time.replace(minute=current_minutes, second=0, microsecond=0)
        
        self.logger(f"Fetching data from {market_open} to {fill_until_time}", "INFO")
        
        # Fetch historical data
        fetch_results = self.fetch_historical_data(
            symbols=symbols,
            start_time=market_open,
            end_time=fill_until_time,
            intervals=intervals
        )
        
        # Wait a moment for data to be written to database
        import time
        time.sleep(2)
        
        # Migrate to live tables
        migrate_results = self.migrate_to_live_tables(
            date_str=market_open.strftime('%Y-%m-%d'),
            time_str=fill_until_time.strftime('%H:%M:%S'),
            intervals=intervals
        )
        
        # Summary
        self.logger("="*80, "INFO")
        self.logger("GAP-FILL SUMMARY", "INFO")
        self.logger("="*80, "INFO")
        
        total_migrated = sum(migrate_results.values())
        for interval, count in migrate_results.items():
            self.logger(f"  {interval}min: {count} candles migrated", "INFO")
        
        self.logger(f"Total: {total_migrated} candles migrated", "SUCCESS")
        self.logger("="*80, "INFO")
        
        # Check if we need another iteration (if we're still significantly behind)
        now = datetime.now()
        time_behind = (now - fill_until_time).total_seconds()
        
        if time_behind > 600:  # More than 10 minutes behind
            self.logger(f"Still {time_behind/60:.1f} minutes behind. Performing another gap-fill iteration...", "INFO")
            return self.perform_gap_fill(symbols, intervals)
        
        return True
