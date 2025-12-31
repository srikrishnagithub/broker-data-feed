"""
Hourly Regime Filter with Forming Hourly Candles - Implementation Guide

This document describes the implementation of a real-time hourly regime filter
that uses "forming" hourly candles to eliminate false signal rejections due to
stale hourly data.
"""

# PROBLEM STATEMENT
# ================================================================================
# The original issue was that the hourly regime filter (EMA20 > EMA50 for LONG)
# was rejecting valid signals at non-hour boundaries.
#
# EXAMPLE:
# At 13:30:57, a LONG signal occurs.
# The 13:00-14:00 hourly candle hasn't been completed yet.
# The hourly data only contains up to 12:00-13:00.
# Therefore, hourly EMAs are stale and don't reflect the current 13:00 candle.
# This causes valid LONG signals to be rejected during the 13:00-14:00 hour.
#
# SOLUTION:
# Build a "forming" hourly candle from available 15-minute data in the current hour.
# Use this forming candle along with completed hourly candles when calculating EMAs.
# This ensures EMAs always reflect the most current data.


# ARCHITECTURE OVERVIEW
# ================================================================================
# The solution consists of three main components:
#
# 1. core/hourly_candle_builder.py
#    - build_forming_hourly_candle(symbol, current_datetime, candles_15min)
#    - append_forming_hourly_candle(hourly_df, forming_candle)
#    - Helper functions and logging
#
# 2. core/signal_generator.py
#    - SignalGenerator class with:
#      - get_hourly_candles() - fetch completed hourly candles
#      - get_15min_candles() - fetch 15-minute candles
#      - calculate_ema() - compute EMA values
#      - get_hourly_ema_with_forming() - main logic combining forming + completed
#      - check_hourly_regime() - evaluate if signal passes filter
#      - evaluate_signal() - complete signal evaluation
#
# 3. tests/test_hourly_signals.py
#    - Comprehensive test suite
#    - Tests for edge cases


# IMPLEMENTATION DETAILS
# ================================================================================

# STEP 1: BUILD FORMING HOURLY CANDLE
# ------------------------------------
# Function: build_forming_hourly_candle()
# Location: core/hourly_candle_builder.py
#
# Logic:
#   1. Determine current hour boundaries (e.g., 13:00:00 - 13:59:59)
#   2. Filter 15-minute candles for current hour
#   3. If no candles in current hour, return None
#   4. Aggregate 15-min candles:
#      - open = first 15-min candle's open
#      - high = maximum high across all candles
#      - low = minimum low across all candles
#      - close = last 15-min candle's close
#      - volume = sum of all volumes
#   5. Return dict with OHLCV + metadata
#
# Example Input (at 13:30:57):
#   Time: 13:00 -> O=278.10 H=278.20 L=278.00 C=278.15 V=5000
#   Time: 13:15 -> O=278.15 H=278.30 L=278.10 C=278.25 V=5100
#
# Example Output:
#   {
#       'datetime': 2025-12-22 13:00:00,
#       'symbol': 'RELIANCE',
#       'open': 278.10,   # First 15-min candle
#       'high': 278.30,   # Max across all
#       'low': 278.00,    # Min across all
#       'close': 278.25,  # Last 15-min candle
#       'volume': 10100,  # Sum of volumes
#       'source': 'forming',
#       'tick_count': 2   # Number of 15-min candles
#   }


# STEP 2: APPEND FORMING CANDLE TO HOURLY DATA
# -----------------------------------------------
# Function: append_forming_hourly_candle()
# Location: core/hourly_candle_builder.py
#
# Logic:
#   1. Take DataFrame of completed hourly candles
#   2. Convert forming candle dict to DataFrame
#   3. Concatenate (append at end)
#   4. Return combined DataFrame
#
# Effect:
#   Before: [12:00 candle, 12:00-13:00 candle]
#   After:  [12:00 candle, 12:00-13:00 candle, 13:00-14:00 FORMING candle]


# STEP 3: CALCULATE HOURLY EMAs WITH FORMING DATA
# -----------------------------------------------
# Function: get_hourly_ema_with_forming()
# Location: core/signal_generator.py
#
# This is the main integration point.
#
# Algorithm:
#   1. Fetch completed hourly candles from database
#   2. Check if current time is in incomplete hour (minute != 0)
#   3. If incomplete hour:
#      a. Fetch 15-minute candles
#      b. Build forming hourly candle
#      c. Append to hourly DataFrame
#   4. Calculate EMAs on combined dataset (completed + forming)
#   5. Return EMA values
#
# Example Timeline at 13:30:57:
#   ├─ Hour 12:00-13:00 [COMPLETED - in database]
#   ├─ Hour 13:00-14:00 [INCOMPLETE - FORMING from 13:00 and 13:15 candles]
#   └─ Now: 13:30:57
#
#   EMA20 and EMA50 are calculated using:
#   [... earlier hours ..., 12:00-13:00 completed, 13:00-14:00 forming]
#
# Result: EMAs reflect current hour's price action


# STEP 4: CHECK HOURLY REGIME
# ----------------------------
# Function: check_hourly_regime()
# Location: core/signal_generator.py
#
# Logic:
#   1. Call get_hourly_ema_with_forming() to get EMA20 and EMA50
#   2. For LONG signals: Check if EMA20 > EMA50 (uptrend)
#   3. For SHORT signals: Check if EMA20 < EMA50 (downtrend)
#   4. Return (passes_filter, details_dict)
#
# Returns:
#   {
#       'symbol': 'RELIANCE',
#       'signal_type': 'LONG',
#       'current_time': '2025-12-22T13:30:57',
#       'ema20': 278.16,
#       'ema50': 278.12,
#       'regime': 'UPTREND',
#       'passes_filter': True,
#       'reason': 'UPTREND: EMA20 (278.16) > EMA50 (278.12)'
#   }


# USAGE EXAMPLES
# ================================================================================

# EXAMPLE 1: Basic Signal Evaluation
# -----------------------------------
# from core.database_handler import DatabaseHandler
# from core.signal_generator import SignalGenerator
# from datetime import datetime
#
# # Initialize
# db = DatabaseHandler()
# signal_gen = SignalGenerator(db)
#
# # Evaluate a signal
# current_time = datetime.now()  # e.g., 13:30:57
# symbol = 'RELIANCE'
# signal_type = 'LONG'
#
# passes, details = signal_gen.check_hourly_regime(
#     symbol=symbol,
#     current_datetime=current_time,
#     signal_type=signal_type
# )
#
# if passes:
#     print(f"Signal {signal_type} {symbol} APPROVED")
#     print(f"  EMA20: {details['ema20']:.4f}")
#     print(f"  EMA50: {details['ema50']:.4f}")
#     print(f"  Regime: {details['regime']}")
# else:
#     print(f"Signal REJECTED: {details['reason']}")


# EXAMPLE 2: Direct Forming Candle Building
# -------------------------------------------
# from core.hourly_candle_builder import build_forming_hourly_candle
# import pandas as pd
#
# # Assume you have 15-min candles
# min15_df = pd.DataFrame({
#     'datetime': [datetime(2025, 12, 22, 13, 0), datetime(2025, 12, 22, 13, 15)],
#     'open': [278.10, 278.15],
#     'high': [278.20, 278.30],
#     'low': [278.00, 278.10],
#     'close': [278.15, 278.25],
#     'volume': [5000, 5100]
# })
#
# current_time = datetime(2025, 12, 22, 13, 30, 57)
#
# forming_candle = build_forming_hourly_candle(
#     symbol='RELIANCE',
#     current_datetime=current_time,
#     candles_15min=min15_df
# )
#
# print(f"Forming Candle: O={forming_candle['open']} H={forming_candle['high']} "
#       f"L={forming_candle['low']} C={forming_candle['close']} V={forming_candle['volume']}")


# EXAMPLE 3: Complete Signal Evaluation with Additional Checks
# -----------------------------------------------
# additional_checks = {
#     'price_action': True,  # Some custom check result
#     'volume_confirmation': True
# }
#
# passes, evaluation = signal_gen.evaluate_signal(
#     symbol='RELIANCE',
#     current_datetime=datetime.now(),
#     signal_type='LONG',
#     additional_checks=additional_checks
# )
#
# print(f"Signal passes all checks: {evaluation['passes_all_checks']}")
# print(f"Checks results: {evaluation['checks']}")


# DATABASE SCHEMA REQUIREMENTS
# ================================================================================
# The implementation requires two tables:
#
# 1. live_candles_60min (or custom hourly table)
#    Columns: datetime, tradingsymbol, open, high, low, close, volume
#    Purpose: Completed hourly candles from database
#
# 2. live_candles_15min (or custom 15-min table)
#    Columns: datetime, tradingsymbol, open, high, low, close, volume
#    Purpose: 15-minute candles for forming current hour
#
# Both tables should have:
#    - PRIMARY KEY (instrument_token, datetime)
#    - INDEX on tradingsymbol
#    - INDEX on datetime


# LOGGING
# ================================================================================
# The implementation logs key events:
#
# INFO Level:
#   - "Built forming hourly candle for {symbol}..."
#   - "Using forming hourly candle for {symbol}..."
#   - "Signal LONG {symbol} APPROVED (all checks passed)"
#
# WARNING Level:
#   - "No hourly candles found for {symbol}"
#   - "Could not build forming hourly candle for {symbol}"
#   - "Signal REJECTED: {reason}"
#
# DEBUG Level:
#   - "Current time is in incomplete hour (minute=30)"
#   - "Fetched X hourly candles..."
#   - "Forming candle OHLC: O=... H=... L=... C=..."


# ERROR HANDLING
# ================================================================================
#
# Edge Cases Handled:
#
# 1. NO 15-MINUTE DATA AVAILABLE
#    ├─ Scenario: Current hour started but no 15-min candles yet
#    ├─ Handling: Return None, continue with completed hourly candles only
#    └─ Impact: EMAs based on older data (same as original behavior)
#
# 2. SINGLE 15-MINUTE CANDLE IN CURRENT HOUR
#    ├─ Scenario: Only first 15-min candle exists
#    ├─ Handling: Build valid forming candle with tick_count=1
#    └─ Impact: Forming candle valid for EMA calculation
#
# 3. EMPTY DATAFRAME
#    ├─ Scenario: No data at all
#    ├─ Handling: Return None, exit gracefully
#    └─ Impact: Signal evaluation fails with clear error
#
# 4. DATABASE CONNECTION FAILURE
#    ├─ Scenario: Cannot fetch candles from database
#    ├─ Handling: Log error, return empty dict for EMAs
#    └─ Impact: Signal fails as safeguard (reject unknown signal)
#
# 5. HOUR BOUNDARY (MINUTE = 0)
#    ├─ Scenario: Signal at exactly 13:00:00
#    ├─ Handling: Don't build forming candle, use completed data only
#    └─ Impact: Correct behavior - hour is complete


# TESTING
# ================================================================================
#
# Run tests:
#   python tests/test_hourly_signals.py
#
# Tests cover:
#   ✓ Forming candle building from 15-min data
#   ✓ Correct OHLCV aggregation
#   ✓ Incomplete hour detection
#   ✓ Hour boundary calculations
#   ✓ EMA calculation accuracy
#   ✓ Forming candle appending
#   ✓ Edge cases (no data, single candle, etc.)
#
# Expected Output:
#   ✅ Passed: 7
#   ❌ Failed: 0
#   📊 Total:  7


# PERFORMANCE CONSIDERATIONS
# ================================================================================
#
# Time Complexity:
#   - build_forming_hourly_candle(): O(n) where n = candles in current hour (~4)
#   - calculate_ema(): O(m) where m = lookback periods (~50)
#   - check_hourly_regime(): O(n + m) - dominated by database queries
#
# Database Queries:
#   - Per signal evaluation: 2 queries
#     1. Fetch hourly candles (100 rows)
#     2. Fetch 15-min candles (20 rows)
#   - Query time: <100ms typically
#
# Memory Usage:
#   - In-memory DataFrames: ~50 hourly + ~20 15-min = ~70 rows max
#   - Memory impact: Negligible


# INTEGRATION POINTS
# ================================================================================
#
# Where to use this in your trading system:
#
# 1. Signal Scanner/Generator
#    └─ When evaluating if a signal should be placed
#       └─ Call check_hourly_regime() before placing order
#
# 2. Risk Management
#    └─ When checking current market regime
#       └─ Call get_hourly_ema_with_forming() for regime confirmation
#
# 3. Position Management
#    └─ When deciding if to continue/close position
#       └─ Call check_hourly_regime() for regime alignment
#
# 4. Portfolio Monitoring
#    └─ When aggregating market conditions
#       └─ Call get_hourly_ema_with_forming() across symbols


# CONFIGURATION OPTIONS
# ================================================================================
#
# In your signal generator, you can customize:
#
# 1. EMA Periods
#    - Default: [20, 50]
#    - Can change to [10, 30] or any other combination
#    - Called in: get_hourly_ema_with_forming(ema_periods=[...])
#
# 2. Lookback Periods
#    - Default: 100 hourly candles (~4 days)
#    - Can increase for longer-term EMA calculation
#    - Called in: get_hourly_candles(lookback_periods=...)
#
# 3. Table Names
#    - Default hourly: 'live_candles_60min'
#    - Default 15-min: 'live_candles_15min'
#    - Can customize for different tables
#    - Called in: get_hourly_ema_with_forming(hourly_table='...', min15_table='...')
#
# 4. Signal Types
#    - Supports: 'LONG' and 'SHORT'
#    - Can extend for other regime types
#    - Called in: check_hourly_regime(signal_type='...')


# MIGRATION FROM OLD SYSTEM
# ================================================================================
#
# If you had an old hourly regime check:
#
# OLD CODE:
#   hourly_df = fetch_hourly_candles(symbol)  # Only completed candles
#   ema20 = calculate_ema(hourly_df['close'], 20)
#   ema50 = calculate_ema(hourly_df['close'], 50)
#   passes = ema20 > ema50  # Simple check
#
# NEW CODE:
#   signal_gen = SignalGenerator(db)
#   passes, details = signal_gen.check_hourly_regime(
#       symbol=symbol,
#       current_datetime=datetime.now(),
#       signal_type='LONG'
#   )
#   # And you get:
#   # - forming candle logic automatically
#   # - detailed logging
#   # - error handling
#   # - complete signal evaluation


# TROUBLESHOOTING
# ================================================================================
#
# Issue: Signal rejected despite strong uptrend
# Cause: At 13:30, hourly data only shows 12:00-13:00 hour
# Solution: This is what forming candle fixes! Should now pass.
#
# Issue: No forming candle built
# Cause: No 15-min candles in current hour yet
# Solution: Normal at start of hour. Will build forming as candles arrive.
#
# Issue: EMA values seem wrong
# Cause: Check database for data quality
# Solution: Verify OHLCV values in database, check for missing candles
#
# Issue: Slow signal evaluation
# Cause: Large lookback_periods (e.g., 500)
# Solution: Reduce to 100-150, still sufficient for EMA calculation
#
# Issue: Cannot connect to database
# Cause: Connection string or database server issue
# Solution: Test with db.test_connection() first


# FUTURE ENHANCEMENTS
# ================================================================================
#
# Potential improvements:
#
# 1. Caching
#    - Cache hourly candles in memory
#    - Reduce database queries
#    - Invalidate cache on new hour
#
# 2. Multiple Timeframes
#    - Extend to form 5-min from ticks
#    - Form 4-hour from hourly
#    - Multi-timeframe regime confirmation
#
# 3. Volume Analysis
#    - Incorporate volume in regime check
#    - Volume-weighted EMAs
#    - Volume confirmation signals
#
# 4. Divergence Detection
#    - Detect price/EMA divergences
#    - Warn of reversal probability
#    - Risk management signals
#
# 5. Multiple Regimes
#    - Support more than 2-EMA regime
#    - Add RSI, MACD, ADX checks
#    - Composite regime scores


# CONTACT & SUPPORT
# ================================================================================
#
# For questions about this implementation:
# 1. Review test cases: tests/test_hourly_signals.py
# 2. Check examples: See "USAGE EXAMPLES" section above
# 3. Review logging output: Enable DEBUG level logging
# 4. Verify database: Check candle data exists and is current
"""

# Export to file as markdown-style documentation
DOCUMENTATION = __doc__
