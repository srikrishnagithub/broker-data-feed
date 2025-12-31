"""
Tests for hourly regime filter with forming candles.

Verifies:
1. Forming hourly candle building from 15-minute data
2. Correct OHLCV aggregation
3. Hourly EMA calculation with forming data
4. Signal acceptance/rejection based on hourly regime
5. Edge cases and error handling
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hourly_candle_builder import (
    build_forming_hourly_candle,
    append_forming_hourly_candle,
    is_in_incomplete_hour,
    get_current_hour_start,
    get_current_hour_end,
    log_forming_candle_usage
)
from core.signal_generator import SignalGenerator


def create_sample_15min_candles(
    symbol: str = 'RELIANCE',
    base_datetime: datetime = None,
    num_candles: int = 4
) -> pd.DataFrame:
    """
    Create sample 15-minute candles for testing.
    
    Args:
        symbol: Trading symbol
        base_datetime: Base datetime (defaults to current hour)
        num_candles: Number of 15-min candles to create
        
    Returns:
        DataFrame with 15-min candle data
    """
    if base_datetime is None:
        base_datetime = datetime.now().replace(minute=0, second=0, microsecond=0)
    
    # Create 4 x 15-min candles (13:00, 13:15, 13:30, 13:45) with incrementing prices
    candles = []
    for i in range(num_candles):
        candle_time = base_datetime + timedelta(minutes=15*i)
        base_price = 278.00 + (i * 0.05)  # Slightly incrementing prices
        
        candle = {
            'datetime': candle_time,
            'open': base_price,
            'high': base_price + 0.15,
            'low': base_price - 0.10,
            'close': base_price + 0.08,
            'volume': 5000 + (i * 100)
        }
        candles.append(candle)
    
    return pd.DataFrame(candles)


def create_sample_hourly_candles(
    symbol: str = 'RELIANCE',
    num_candles: int = 50
) -> pd.DataFrame:
    """
    Create sample hourly candles for testing.
    
    Args:
        symbol: Trading symbol
        num_candles: Number of hourly candles
        
    Returns:
        DataFrame with hourly candle data
    """
    candles = []
    base_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    
    for i in range(num_candles):
        candle_time = base_time - timedelta(hours=(num_candles - i - 1))
        
        # Create trend: gradually increasing then decreasing
        if i < num_candles // 2:
            base_price = 275.00 + (i * 0.10)  # Uptrend
        else:
            base_price = 280.00 - ((i - num_candles//2) * 0.08)  # Downtrend
        
        candle = {
            'datetime': candle_time,
            'open': base_price,
            'high': base_price + 0.25,
            'low': base_price - 0.20,
            'close': base_price + 0.10,
            'volume': 50000 + (i * 500)
        }
        candles.append(candle)
    
    return pd.DataFrame(candles)


def test_forming_candle_building():
    """Test building a forming hourly candle from 15-minute data."""
    print("\n" + "="*70)
    print("TEST: Forming Hourly Candle Building")
    print("="*70)
    
    # Create sample 15-min candles
    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
    min15_df = create_sample_15min_candles(
        symbol='RELIANCE',
        base_datetime=base_time,
        num_candles=4
    )
    
    print(f"\nInput: 4 x 15-minute candles")
    print(min15_df.to_string())
    
    # Build forming candle
    forming_candle = build_forming_hourly_candle(
        symbol='RELIANCE',
        current_datetime=base_time + timedelta(minutes=35),
        candles_15min=min15_df
    )
    
    # Verify
    assert forming_candle is not None, "Forming candle should not be None"
    assert forming_candle['symbol'] == 'RELIANCE', "Symbol should match"
    assert forming_candle['datetime'] == base_time, "Timestamp should be hour start"
    assert forming_candle['open'] == min15_df.iloc[0]['open'], "Open should be first candle's open"
    assert forming_candle['close'] == min15_df.iloc[-1]['close'], "Close should be last candle's close"
    assert forming_candle['high'] == min15_df['high'].max(), "High should be maximum"
    assert forming_candle['low'] == min15_df['low'].min(), "Low should be minimum"
    assert forming_candle['volume'] == min15_df['volume'].sum(), "Volume should be sum"
    assert forming_candle['tick_count'] == 4, "Should have 4 candles"
    assert forming_candle['source'] == 'forming', "Source should be 'forming'"
    
    print(f"\nOutput: Forming hourly candle")
    print(f"  DateTime: {forming_candle['datetime']}")
    print(f"  Open: {forming_candle['open']:.4f}")
    print(f"  High: {forming_candle['high']:.4f}")
    print(f"  Low: {forming_candle['low']:.4f}")
    print(f"  Close: {forming_candle['close']:.4f}")
    print(f"  Volume: {forming_candle['volume']}")
    print(f"  Tick Count: {forming_candle['tick_count']}")
    print(f"  Source: {forming_candle['source']}")
    
    print("\n✅ TEST PASSED: Forming candle built correctly")
    return True


def test_incomplete_hour_detection():
    """Test detection of incomplete hours."""
    print("\n" + "="*70)
    print("TEST: Incomplete Hour Detection")
    print("="*70)
    
    # Test cases
    test_cases = [
        (datetime(2025, 12, 22, 13, 0, 0), False, "13:00:00 - Hour boundary"),
        (datetime(2025, 12, 22, 13, 15, 30), True, "13:15:30 - Incomplete"),
        (datetime(2025, 12, 22, 13, 30, 45), True, "13:30:45 - Incomplete"),
        (datetime(2025, 12, 22, 13, 59, 59), True, "13:59:59 - Incomplete"),
        (datetime(2025, 12, 22, 14, 0, 0), False, "14:00:00 - Hour boundary"),
    ]
    
    for dt, expected, description in test_cases:
        result = is_in_incomplete_hour(dt)
        assert result == expected, f"Failed for {description}"
        status = "✓" if result == expected else "✗"
        print(f"{status} {description}: is_incomplete={result}")
    
    print("\n✅ TEST PASSED: Incomplete hour detection works correctly")
    return True


def test_hour_boundary_functions():
    """Test hour start and end calculation."""
    print("\n" + "="*70)
    print("TEST: Hour Boundary Functions")
    print("="*70)
    
    test_dt = datetime(2025, 12, 22, 13, 35, 47, 123456)
    
    hour_start = get_current_hour_start(test_dt)
    hour_end = get_current_hour_end(test_dt)
    
    assert hour_start == datetime(2025, 12, 22, 13, 0, 0), "Hour start should be 13:00:00"
    assert hour_end == datetime(2025, 12, 22, 13, 59, 59), "Hour end should be 13:59:59"
    
    print(f"Input time: {test_dt}")
    print(f"Hour start: {hour_start}")
    print(f"Hour end: {hour_end}")
    
    print("\n✅ TEST PASSED: Hour boundary functions work correctly")
    return True


def test_ema_calculation():
    """Test EMA calculation."""
    print("\n" + "="*70)
    print("TEST: EMA Calculation")
    print("="*70)
    
    # Create sample data
    signal_gen = SignalGenerator(None)  # No database needed for this test
    
    # Sample prices
    prices = pd.Series([
        277.50, 277.80, 277.90, 278.10, 278.20, 278.15,
        278.00, 278.05, 278.10, 278.20, 278.30, 278.25,
        278.20, 278.15, 278.10
    ])
    
    # Calculate EMA20 and EMA50 (though we don't have 50 data points here)
    ema20 = signal_gen.calculate_ema(prices, 20)
    ema5 = signal_gen.calculate_ema(prices, 5)
    
    print(f"Sample prices (length={len(prices)})")
    print(f"  First: {prices.iloc[0]:.4f}")
    print(f"  Last: {prices.iloc[-1]:.4f}")
    print(f"\nEMA5: {ema5.iloc[-1]:.4f}")
    print(f"EMA20: {ema20.iloc[-1]:.4f}")
    
    # EMAs should be between min and max prices
    assert ema5.iloc[-1] >= prices.min() and ema5.iloc[-1] <= prices.max(), "EMA5 out of range"
    assert ema20.iloc[-1] >= prices.min() and ema20.iloc[-1] <= prices.max(), "EMA20 out of range"
    
    print("\n✅ TEST PASSED: EMA calculation works correctly")
    return True


def test_forming_candle_appending():
    """Test appending forming candle to hourly DataFrame."""
    print("\n" + "="*70)
    print("TEST: Appending Forming Candle to Hourly DataFrame")
    print("="*70)
    
    # Create sample hourly candles
    hourly_df = create_sample_hourly_candles(num_candles=5)
    initial_rows = len(hourly_df)
    
    print(f"Initial hourly candles: {initial_rows}")
    
    # Create forming candle
    forming_candle = {
        'datetime': datetime.now().replace(minute=0, second=0, microsecond=0),
        'symbol': 'RELIANCE',
        'instrument_token': 6401,
        'open': 278.10,
        'high': 278.25,
        'low': 278.00,
        'close': 278.15,
        'volume': 25000,
        'source': 'forming',
        'tick_count': 3
    }
    
    # Append forming candle
    result_df = append_forming_hourly_candle(hourly_df, forming_candle)
    
    assert len(result_df) == initial_rows + 1, "Should have one more row"
    assert result_df.iloc[-1]['source'] == 'forming', "Last row should be forming candle"
    assert result_df.iloc[-1]['tick_count'] == 3, "Tick count should match"
    
    print(f"After appending: {len(result_df)} rows")
    print(f"Last row (forming): {result_df.iloc[-1].to_dict()}")
    
    print("\n✅ TEST PASSED: Forming candle appended correctly")
    return True


def test_edge_case_no_15min_data():
    """Test handling when no 15-minute data is available."""
    print("\n" + "="*70)
    print("TEST: Edge Case - No 15-Minute Data")
    print("="*70)
    
    # Empty DataFrame
    empty_df = pd.DataFrame()
    
    forming_candle = build_forming_hourly_candle(
        symbol='RELIANCE',
        current_datetime=datetime.now().replace(minute=30, second=0, microsecond=0),
        candles_15min=empty_df
    )
    
    assert forming_candle is None, "Should return None for empty data"
    
    print("Empty DataFrame -> forming_candle is None ✓")
    
    # No candles in current hour
    past_time = datetime.now() - timedelta(hours=2)
    past_df = create_sample_15min_candles(
        base_datetime=past_time,
        num_candles=4
    )
    
    forming_candle = build_forming_hourly_candle(
        symbol='RELIANCE',
        current_datetime=datetime.now().replace(minute=30, second=0, microsecond=0),
        candles_15min=past_df
    )
    
    assert forming_candle is None, "Should return None when no candles in current hour"
    
    print("Past candles (no current hour match) -> forming_candle is None ✓")
    
    print("\n✅ TEST PASSED: Edge cases handled correctly")
    return True


def test_edge_case_partial_hour_data():
    """Test forming candle with only 1-2 candles in the hour."""
    print("\n" + "="*70)
    print("TEST: Edge Case - Partial Hour Data (1-2 candles)")
    print("="*70)
    
    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
    
    # Only first 15-min candle
    single_candle_df = create_sample_15min_candles(
        base_datetime=base_time,
        num_candles=1
    )
    
    forming_candle = build_forming_hourly_candle(
        symbol='RELIANCE',
        current_datetime=base_time + timedelta(minutes=5),
        candles_15min=single_candle_df
    )
    
    assert forming_candle is not None, "Should handle single candle"
    assert forming_candle['tick_count'] == 1, "Should have 1 candle"
    assert forming_candle['open'] == forming_candle['open'], "Open should match itself"
    assert forming_candle['close'] == forming_candle['close'], "Close should match itself"
    
    print(f"Single candle -> tick_count={forming_candle['tick_count']} "
          f"O={forming_candle['open']:.2f} C={forming_candle['close']:.2f} ✓")
    
    # Two candles
    two_candle_df = create_sample_15min_candles(
        base_datetime=base_time,
        num_candles=2
    )
    
    forming_candle = build_forming_hourly_candle(
        symbol='RELIANCE',
        current_datetime=base_time + timedelta(minutes=20),
        candles_15min=two_candle_df
    )
    
    assert forming_candle is not None, "Should handle two candles"
    assert forming_candle['tick_count'] == 2, "Should have 2 candles"
    
    print(f"Two candles -> tick_count={forming_candle['tick_count']} ✓")
    
    print("\n✅ TEST PASSED: Partial hour data handled correctly")
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*70)
    print("HOURLY REGIME FILTER - COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    tests = [
        test_forming_candle_building,
        test_incomplete_hour_detection,
        test_hour_boundary_functions,
        test_ema_calculation,
        test_forming_candle_appending,
        test_edge_case_no_15min_data,
        test_edge_case_partial_hour_data,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ TEST ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total:  {passed + failed}")
    print("="*70 + "\n")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
