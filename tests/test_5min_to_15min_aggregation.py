#!/usr/bin/env python3
"""
Test script to verify 5-minute to 15-minute candle aggregation.

Tests the candle aggregation logic with sample data and displays results.
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.hourly_candle_builder import aggregate_5min_to_15min
import pandas as pd


def create_sample_5min_candles():
    """Create sample 5-minute candles for testing."""
    
    base_time = datetime(2026, 1, 2, 9, 5, 0)
    
    data = [
        # First 15-minute period (9:00-9:15)
        {'datetime': base_time, 'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000},
        {'datetime': base_time + timedelta(minutes=5), 'open': 100.5, 'high': 102.0, 'low': 100.0, 'close': 101.5, 'volume': 1200},
        {'datetime': base_time + timedelta(minutes=10), 'open': 101.5, 'high': 103.0, 'low': 101.0, 'close': 102.5, 'volume': 1100},
        
        # Second 15-minute period (9:15-9:30)
        {'datetime': base_time + timedelta(minutes=15), 'open': 102.5, 'high': 104.0, 'low': 102.0, 'close': 103.5, 'volume': 1300},
        {'datetime': base_time + timedelta(minutes=20), 'open': 103.5, 'high': 105.0, 'low': 103.0, 'close': 104.5, 'volume': 1400},
        {'datetime': base_time + timedelta(minutes=25), 'open': 104.5, 'high': 106.0, 'low': 104.0, 'close': 105.5, 'volume': 1500},
    ]
    
    df = pd.DataFrame(data)
    return df


def test_aggregate_5min_to_15min():
    """Test the aggregation function."""
    
    print("\n" + "="*80)
    print("TEST: 5-Minute to 15-Minute Candle Aggregation")
    print("="*80)
    
    # Create sample data
    print("\n1. Creating sample 5-minute candles...")
    df = create_sample_5min_candles()
    
    print("\nSample 5-minute candles:")
    print(df.to_string())
    
    # Test aggregation for first group
    print("\n2. Aggregating first 3 candles (9:05-9:15) into 15-min candle...")
    result = aggregate_5min_to_15min('TESTSTOCK', df.iloc[:3])
    
    if result:
        print(f"\n✓ First 15-minute candle aggregated successfully:")
        print(f"  Timestamp: {result['datetime']}")
        print(f"  Symbol: {result['symbol']}")
        print(f"  OHLC: {result['open']:.2f} / {result['high']:.2f} / {result['low']:.2f} / {result['close']:.2f}")
        print(f"  Volume: {result['volume']}")
        print(f"  Source: {result['source']}")
        
        # Verify values
        assert result['datetime'] == datetime(2026, 1, 2, 9, 0, 0), "Incorrect timestamp"
        assert result['open'] == 100.0, "Incorrect open"
        assert result['high'] == 103.0, "Incorrect high"
        assert result['low'] == 99.0, "Incorrect low"
        assert result['close'] == 102.5, "Incorrect close"
        assert result['volume'] == 3300, "Incorrect volume"
        print("\n✓ All assertions passed for first 15-min candle!")
    else:
        print("\n✗ Failed to aggregate first group")
        return False
    
    # Test aggregation for second group
    print("\n3. Aggregating second 3 candles (9:15-9:30) into 15-min candle...")
    result2 = aggregate_5min_to_15min('TESTSTOCK', df.iloc[3:6])
    
    if result2:
        print(f"\n✓ Second 15-minute candle aggregated successfully:")
        print(f"  Timestamp: {result2['datetime']}")
        print(f"  Symbol: {result2['symbol']}")
        print(f"  OHLC: {result2['open']:.2f} / {result2['high']:.2f} / {result2['low']:.2f} / {result2['close']:.2f}")
        print(f"  Volume: {result2['volume']}")
        print(f"  Source: {result2['source']}")
        
        # Verify values
        assert result2['datetime'] == datetime(2026, 1, 2, 9, 15, 0), "Incorrect timestamp"
        assert result2['open'] == 102.5, "Incorrect open"
        assert result2['high'] == 106.0, "Incorrect high"
        assert result2['low'] == 102.0, "Incorrect low"
        assert result2['close'] == 105.5, "Incorrect close"
        assert result2['volume'] == 4200, "Incorrect volume"
        print("\n✓ All assertions passed for second 15-min candle!")
    else:
        print("\n✗ Failed to aggregate second group")
        return False
    
    # Test edge case: insufficient candles
    print("\n4. Testing edge case: insufficient candles (< 3)...")
    result_empty = aggregate_5min_to_15min('TESTSTOCK', df.iloc[:2])
    if result_empty is None:
        print("✓ Correctly returned None for insufficient data")
    else:
        print("✗ Should have returned None for insufficient data")
        return False
    
    print("\n" + "="*80)
    print("✓ ALL TESTS PASSED!")
    print("="*80)
    return True


if __name__ == '__main__':
    success = test_aggregate_5min_to_15min()
    sys.exit(0 if success else 1)
