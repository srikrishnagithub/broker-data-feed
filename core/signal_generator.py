"""
Signal generator with hourly regime filter using forming hourly candles.

Evaluates trading signals with a hourly regime check that uses forming hourly
candles to ensure EMAs include current hour data, preventing false rejections of
valid signals due to stale hourly data.
"""
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from core.hourly_candle_builder import (
    build_forming_hourly_candle,
    append_forming_hourly_candle,
    is_in_incomplete_hour,
    log_forming_candle_usage
)
from core.database_handler import DatabaseHandler


class SignalGenerator:
    """
    Generates trading signals with hourly regime filter using forming candles.
    
    This class evaluates signals based on technical indicators and filters them
    through a hourly regime check. The regime check uses forming hourly candles
    to ensure EMAs always reflect the most current hour's data.
    """
    
    def __init__(
        self,
        database: DatabaseHandler,
        logger=None
    ):
        """
        Initialize signal generator.
        
        Args:
            database: DatabaseHandler instance for querying candles
            logger: Optional logging function
        """
        self.database = database
        self.logger = logger or self._default_logger
    
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def get_hourly_candles(
        self,
        symbol: str,
        lookback_periods: int = 100,
        table_name: str = 'live_candles_60min'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch completed hourly candles from database.
        
        Args:
            symbol: Trading symbol
            lookback_periods: Number of periods to fetch
            table_name: Database table name for hourly candles
            
        Returns:
            DataFrame of hourly candles or None if fetch fails
        """
        try:
            from sqlalchemy import text
            
            query = text(f"""
                SELECT 
                    datetime,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM {table_name}
                WHERE tradingsymbol = :symbol
                ORDER BY datetime DESC
                LIMIT :limit
            """)
            
            with self.database.engine.connect() as conn:
                result = conn.execute(query, {
                    "symbol": symbol,
                    "limit": lookback_periods
                })
                
                rows = result.fetchall()
                if not rows:
                    self.logger(
                        f"No hourly candles found for {symbol}",
                        "WARNING"
                    )
                    return None
                
                # Convert to DataFrame and reverse order (oldest to newest)
                df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
                df = df.sort_values('datetime').reset_index(drop=True)
                
                self.logger(
                    f"Fetched {len(df)} hourly candles for {symbol} "
                    f"(from {df['datetime'].min()} to {df['datetime'].max()})",
                    "DEBUG"
                )
                
                return df
                
        except Exception as e:
            self.logger(
                f"Error fetching hourly candles for {symbol}: {e}",
                "ERROR"
            )
            return None
    
    def get_15min_candles(
        self,
        symbol: str,
        current_datetime: datetime,
        lookback_periods: int = 20,
        table_name: str = 'live_candles_15min'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch 15-minute candles from database.
        
        Args:
            symbol: Trading symbol
            current_datetime: Current datetime (to fetch recent candles)
            lookback_periods: Number of periods to fetch
            table_name: Database table name for 15-min candles
            
        Returns:
            DataFrame of 15-minute candles or None if fetch fails
        """
        try:
            from sqlalchemy import text
            
            # Fetch recent 15-min candles
            query = text(f"""
                SELECT 
                    datetime,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM {table_name}
                WHERE tradingsymbol = :symbol
                ORDER BY datetime DESC
                LIMIT :limit
            """)
            
            with self.database.engine.connect() as conn:
                result = conn.execute(query, {
                    "symbol": symbol,
                    "limit": lookback_periods
                })
                
                rows = result.fetchall()
                if not rows:
                    self.logger(
                        f"No 15-minute candles found for {symbol}",
                        "WARNING"
                    )
                    return None
                
                # Convert to DataFrame and reverse order (oldest to newest)
                df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
                df = df.sort_values('datetime').reset_index(drop=True)
                
                self.logger(
                    f"Fetched {len(df)} 15-min candles for {symbol}",
                    "DEBUG"
                )
                
                return df
                
        except Exception as e:
            self.logger(
                f"Error fetching 15-min candles for {symbol}: {e}",
                "ERROR"
            )
            return None
    
    def calculate_ema(
        self,
        data: pd.Series,
        period: int
    ) -> pd.Series:
        """
        Calculate Exponential Moving Average.
        
        Args:
            data: Series of prices (close prices)
            period: EMA period
            
        Returns:
            Series with EMA values
        """
        return data.ewm(span=period, adjust=False).mean()
    
    def get_hourly_ema_with_forming(
        self,
        symbol: str,
        current_datetime: datetime,
        ema_periods: List[int] = None,
        hourly_table: str = 'live_candles_60min',
        min15_table: str = 'live_candles_15min'
    ) -> Dict[int, float]:
        """
        Calculate hourly EMAs including forming hourly candle data.
        
        This is the key function that ensures hourly EMAs always reflect
        the current hour's data by building a forming hourly candle from
        available 15-minute data.
        
        Args:
            symbol: Trading symbol
            current_datetime: Current datetime
            ema_periods: List of EMA periods to calculate (default: [20, 50])
            hourly_table: Database table with completed hourly candles
            min15_table: Database table with 15-minute candles
            
        Returns:
            Dictionary mapping EMA period to calculated value
            {20: ema20_value, 50: ema50_value, ...}
        """
        if ema_periods is None:
            ema_periods = [20, 50]
        
        ema_values = {}
        
        try:
            # Fetch completed hourly candles
            hourly_df = self.get_hourly_candles(symbol, lookback_periods=100, table_name=hourly_table)
            if hourly_df is None or hourly_df.empty:
                self.logger(f"No completed hourly candles for {symbol}", "WARNING")
                return ema_values
            
            # Check if we're in an incomplete hour
            if is_in_incomplete_hour(current_datetime):
                self.logger(
                    f"Current time is in incomplete hour (minute={current_datetime.minute})",
                    "DEBUG"
                )
                
                # Fetch 15-minute candles
                min15_df = self.get_15min_candles(symbol, current_datetime, lookback_periods=20, table_name=min15_table)
                
                if min15_df is not None and not min15_df.empty:
                    # Build forming hourly candle
                    forming_candle = build_forming_hourly_candle(
                        symbol=symbol,
                        current_datetime=current_datetime,
                        candles_15min=min15_df,
                        logger=self.logger
                    )
                    
                    if forming_candle:
                        # Append forming candle to hourly dataframe
                        hourly_df = append_forming_hourly_candle(
                            hourly_df,
                            forming_candle,
                            logger=self.logger
                        )
                        
                        log_forming_candle_usage(
                            symbol=symbol,
                            forming_candle=forming_candle,
                            hourly_ema20=None,  # Will be calculated next
                            hourly_ema50=None,
                            logger=self.logger
                        )
                    else:
                        self.logger(
                            f"Could not build forming hourly candle for {symbol}",
                            "WARNING"
                        )
                else:
                    self.logger(
                        f"No 15-minute candles available for forming candle {symbol}",
                        "INFO"
                    )
            else:
                self.logger(
                    f"Current time is on hour boundary (minute={current_datetime.minute}), "
                    f"using completed hourly candles only",
                    "DEBUG"
                )
            
            # Calculate EMAs on complete + forming hourly data
            close_prices = hourly_df['close'].values
            
            for period in ema_periods:
                if len(close_prices) >= period:
                    # Calculate EMA
                    ema_series = self.calculate_ema(
                        pd.Series(close_prices),
                        period
                    )
                    ema_value = float(ema_series.iloc[-1])
                    ema_values[period] = ema_value
                    
                    self.logger(
                        f"Calculated EMA{period} for {symbol}: {ema_value:.4f}",
                        "DEBUG"
                    )
                else:
                    self.logger(
                        f"Insufficient data for EMA{period} (have {len(close_prices)}, need {period})",
                        "WARNING"
                    )
            
            return ema_values
            
        except Exception as e:
            self.logger(
                f"Error calculating hourly EMAs for {symbol}: {e}",
                "ERROR"
            )
            return ema_values
    
    def check_hourly_regime(
        self,
        symbol: str,
        current_datetime: datetime,
        signal_type: str = 'LONG'
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if signal passes hourly regime filter.
        
        For LONG signals: EMA20 > EMA50 (uptrend)
        For SHORT signals: EMA20 < EMA50 (downtrend)
        
        This uses forming hourly candles to ensure EMAs always include
        current hour data.
        
        Args:
            symbol: Trading symbol
            current_datetime: Current datetime when signal occurs
            signal_type: 'LONG' or 'SHORT'
            
        Returns:
            Tuple of (passes_filter: bool, details: dict with EMA values and reasoning)
        """
        details = {
            'symbol': symbol,
            'signal_type': signal_type,
            'current_time': current_datetime.isoformat(),
            'ema20': None,
            'ema50': None,
            'regime': None,
            'passes_filter': False,
            'reason': ''
        }
        
        try:
            # Get hourly EMAs with forming candle logic
            ema_values = self.get_hourly_ema_with_forming(
                symbol=symbol,
                current_datetime=current_datetime,
                ema_periods=[20, 50]
            )
            
            if not ema_values or 20 not in ema_values or 50 not in ema_values:
                details['reason'] = 'Could not calculate hourly EMAs'
                self.logger(
                    f"Signal for {symbol} REJECTED: {details['reason']}",
                    "WARNING"
                )
                return False, details
            
            ema20 = ema_values[20]
            ema50 = ema_values[50]
            
            details['ema20'] = ema20
            details['ema50'] = ema50
            
            # Check regime
            if signal_type.upper() == 'LONG':
                # For LONG signals: need EMA20 > EMA50 (uptrend)
                regime_passes = ema20 > ema50
                details['regime'] = 'UPTREND' if ema20 > ema50 else 'DOWNTREND'
                
                if regime_passes:
                    details['reason'] = f'UPTREND: EMA20 ({ema20:.4f}) > EMA50 ({ema50:.4f})'
                    details['passes_filter'] = True
                    self.logger(
                        f"Signal {signal_type} for {symbol} PASSED hourly regime: {details['reason']}",
                        "SUCCESS"
                    )
                else:
                    details['reason'] = f'DOWNTREND: EMA20 ({ema20:.4f}) <= EMA50 ({ema50:.4f})'
                    self.logger(
                        f"Signal {signal_type} for {symbol} REJECTED: {details['reason']}",
                        "WARNING"
                    )
                    
            elif signal_type.upper() == 'SHORT':
                # For SHORT signals: need EMA20 < EMA50 (downtrend)
                regime_passes = ema20 < ema50
                details['regime'] = 'DOWNTREND' if ema20 < ema50 else 'UPTREND'
                
                if regime_passes:
                    details['reason'] = f'DOWNTREND: EMA20 ({ema20:.4f}) < EMA50 ({ema50:.4f})'
                    details['passes_filter'] = True
                    self.logger(
                        f"Signal {signal_type} for {symbol} PASSED hourly regime: {details['reason']}",
                        "SUCCESS"
                    )
                else:
                    details['reason'] = f'UPTREND: EMA20 ({ema20:.4f}) >= EMA50 ({ema50:.4f})'
                    self.logger(
                        f"Signal {signal_type} for {symbol} REJECTED: {details['reason']}",
                        "WARNING"
                    )
            else:
                details['reason'] = f'Unknown signal type: {signal_type}'
                self.logger(details['reason'], "ERROR")
                return False, details
            
            return regime_passes, details
            
        except Exception as e:
            details['reason'] = f'Error checking regime: {e}'
            self.logger(details['reason'], "ERROR")
            return False, details
    
    def evaluate_signal(
        self,
        symbol: str,
        current_datetime: datetime,
        signal_type: str,
        additional_checks: Dict[str, bool] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate a complete signal with all checks including hourly regime.
        
        Args:
            symbol: Trading symbol
            current_datetime: Current datetime
            signal_type: 'LONG' or 'SHORT'
            additional_checks: Dictionary of additional check results
            
        Returns:
            Tuple of (signal_passes: bool, details: dict)
        """
        evaluation = {
            'symbol': symbol,
            'signal_type': signal_type,
            'current_time': current_datetime.isoformat(),
            'checks': {},
            'passes_all_checks': True
        }
        
        # Check hourly regime (main filter)
        passes_regime, regime_details = self.check_hourly_regime(
            symbol=symbol,
            current_datetime=current_datetime,
            signal_type=signal_type
        )
        
        evaluation['checks']['hourly_regime'] = regime_details
        
        if not passes_regime:
            evaluation['passes_all_checks'] = False
            self.logger(
                f"Signal {signal_type} {symbol} failed hourly regime check",
                "WARNING"
            )
            return False, evaluation
        
        # Check additional conditions if provided
        if additional_checks:
            for check_name, check_result in additional_checks.items():
                evaluation['checks'][check_name] = check_result
                if not check_result:
                    evaluation['passes_all_checks'] = False
                    self.logger(
                        f"Signal {signal_type} {symbol} failed {check_name} check",
                        "WARNING"
                    )
                    return False, evaluation
        
        # All checks passed
        self.logger(
            f"Signal {signal_type} {symbol} APPROVED (all checks passed)",
            "SUCCESS"
        )
        return True, evaluation
