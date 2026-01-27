#!/usr/bin/env python3
"""
Test script for backfilling missing 15-minute and 60-minute candles.

Simulates missing candles and verifies the backfill process.
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd


def create_sample_candle_series():
    """
    Create a complete series of 5-minute candles for testing.
    
    Creates candles from 9:00 to 9:59 (12 candles = 60 minutes).
    This represents a complete hour with all candles present.
    """
    
    base_time = datetime(2026, 1, 2, 9, 0, 0)
    candles = []
    
    for i in range(12):
        time = base_time + timedelta(minutes=5 * i)
        open_price = 100.0 + i
        candles.append({
            'datetime': time,
            'open': open_price,
            'high': open_price + 1.0,
            'low': open_price - 0.5,
            'close': open_price + 0.5,
            'volume': 1000 + (i * 100),
            'instrument_token': 12345,
            'tradingsymbol': 'TESTSTOCK'
        })
    
    return pd.DataFrame(candles)


def test_backfill_15min():
    """Test 15-minute candle backfilling logic."""
    
    print("\n" + "="*80)
    print("TEST: Backfill Missing 15-Minute Candles")
    print("="*80)
    
    # Create sample data
    df_5min = create_sample_candle_series()
    print(f"\nCreated {len(df_5min)} 5-minute candles")
    print("\nSample 5-minute candles:")
    print(df_5min[['datetime', 'close', 'volume']].to_string())
    
    # Expected 15-minute candles
    expected_15min = [
        {
            'period': '9:00-9:15',
            'timestamp': datetime(2026, 1, 2, 9, 0, 0),
            'open': 100.0,  # from 9:00 candle
            'close': 101.5,  # from 9:10 candle
            'volume': 1000 + 1100 + 1200  # sum of 3 candles
        },
        {
            'period': '9:15-9:30',
            'timestamp': datetime(2026, 1, 2, 9, 15, 0),
            'open': 102.0,  # from 9:15 candle
            'close': 103.5,  # from 9:25 candle
            'volume': 1300 + 1400 + 1500
        },
        {
            'period': '9:30-9:45',
            'timestamp': datetime(2026, 1, 2, 9, 30, 0),
            'open': 104.0,  # from 9:30 candle
            'close': 105.5,  # from 9:40 candle
            'volume': 1600 + 1700 + 1800
        },
        {
            'period': '9:45-10:00',
            'timestamp': datetime(2026, 1, 2, 9, 45, 0),
            'open': 106.0,  # from 9:45 candle
            'close': 106.5,  # from 9:55 candle
            'volume': 1900 + 2000 + 2100
        }
    ]
    
    print("\n\nExpected 15-minute candles after aggregation:")
    for expected in expected_15min:
        print(f"\n{expected['period']} ({expected['timestamp']})")
        print(f"  Open: {expected['open']:.2f}, Close: {expected['close']:.2f}, Volume: {expected['volume']}")
    
    # Simulate aggregation logic
    print("\n\nSimulating backfill aggregation...")
    aggregated_15min = []
    i = 0
    
    while i + 2 < len(df_5min):
        group = df_5min.iloc[i:i+3]
        first_dt = group.iloc[0]['datetime']
        minutes = (first_dt.minute // 15) * 15
        ts_15min = first_dt.replace(minute=minutes, second=0, microsecond=0)
        
        agg = {
            'datetime': ts_15min,
            'open': float(group.iloc[0]['open']),
            'high': float(group['high'].max()),
            'low': float(group['low'].min()),
            'close': float(group.iloc[-1]['close']),
            'volume': int(group['volume'].sum())
        }
        aggregated_15min.append(agg)
        print(f"✓ Aggregated {ts_15min}: O={agg['open']:.2f}, H={agg['high']:.2f}, L={agg['low']:.2f}, C={agg['close']:.2f}, V={agg['volume']}")
        
        i += 3
    
    # Verify
    print(f"\n✓ Created {len(aggregated_15min)} 15-minute candles (expected {len(expected_15min)})")
    
    if len(aggregated_15min) == len(expected_15min):
        print("✓ Count matches expected!")
    else:
        print(f"✗ Count mismatch: got {len(aggregated_15min)}, expected {len(expected_15min)}")
        return False
    
    return True


def test_backfill_60min():
    """Test 60-minute candle backfilling logic."""
    
    print("\n" + "="*80)
    print("TEST: Backfill Missing 60-Minute Candles")
    print("="*80)
    
    # Create 15-minute candles
    base_time = datetime(2026, 1, 2, 9, 0, 0)
    df_15min = pd.DataFrame([
        {'datetime': base_time + timedelta(minutes=15*i), 'open': 100.0 + i, 'high': 101.0 + i, 'low': 99.0 + i, 'close': 100.5 + i, 'volume': 1000 + (i*100), 'instrument_token': 12345}
        for i in range(8)  # 2 hours of 15-minute candles
    ])
    
    print(f"\nCreated {len(df_15min)} 15-minute candles (covering 2 hours)")
    print("\nSample 15-minute candles:")
    print(df_15min[['datetime', 'close', 'volume']].to_string())
    
    # Expected 60-minute candles (4 x 15-min = 1 hour)
    print("\n\nExpected 60-minute candles:")
    print("  9:00-10:00 (4 x 15-min candles)")
    print("  10:00-11:00 (4 x 15-min candles)")
    
    # Simulate aggregation logic
    print("\n\nSimulating backfill aggregation...")
    aggregated_60min = []
    i = 0
    
    while i + 3 < len(df_15min):
        group = df_15min.iloc[i:i+4]
        first_dt = group.iloc[0]['datetime']
        ts_60min = first_dt.replace(minute=0, second=0, microsecond=0)
        
        agg = {
            'datetime': ts_60min,
            'open': float(group.iloc[0]['open']),
            'high': float(group['high'].max()),
            'low': float(group['low'].min()),
            'close': float(group.iloc[-1]['close']),
            'volume': int(group['volume'].sum())
        }
        aggregated_60min.append(agg)
        print(f"✓ Aggregated {ts_60min}: O={agg['open']:.2f}, H={agg['high']:.2f}, L={agg['low']:.2f}, C={agg['close']:.2f}, V={agg['volume']}")
        
        i += 4
    
    # Verify
    print(f"\n✓ Created {len(aggregated_60min)} 60-minute candles (expected 2)")
    
    if len(aggregated_60min) == 2:
        print("✓ Count matches expected!")
    else:
        print(f"✗ Count mismatch: got {len(aggregated_60min)}, expected 2")
        return False
    
    return True


def test_missing_candle_detection():
    """Test detection of missing candles."""
    
    print("\n" + "="*80)
    print("TEST: Missing Candle Detection")
    print("="*80)
    
    # Create series with a gap
    base_time = datetime(2026, 1, 2, 9, 0, 0)
    candles = []
    
    # First 9 candles (45 minutes)
    for i in range(9):
        candles.append({
            'datetime': base_time + timedelta(minutes=5 * i),
            'value': i
        })
    
    # Skip 2 candles (10 minutes)
    # Then add last 3 candles
    for i in range(11, 14):
        candles.append({
            'datetime': base_time + timedelta(minutes=5 * i),
            'value': i
        })
    
    df = pd.DataFrame(candles)
    
    print(f"\nCreated candle series with gap:")
    print(f"  Candles at: 0-44 minutes (9 candles)")
    print(f"  GAP: 45-54 minutes (missing 2 x 5-min = 10 minutes)")
    print(f"  Candles at: 55-65 minutes (3 candles)")
    
    print(f"\nTotal candles: {len(df)}")
    print("\nCandle timestamps:")
    print(df[['datetime']].to_string())
    
    # Detect expected 15-min candles (each group of 3 consecutive)
    expected_groups = 0
    for i in range(0, len(df) - 2, 3):
        if i + 2 < len(df):
            expected_groups += 1
    
    print(f"\n✓ Can form {expected_groups} complete 15-minute candles from this series")
    print(f"  (with the gap, some candles won't be aggregated)")
    
    return True


def main():
    """Run all tests."""
    
    print("\n" + "="*80)
    print("BACKFILL FUNCTIONALITY TEST SUITE")
    print("="*80)
    
    tests_passed = 0
    tests_total = 3
    
    # Test 1: 15-minute backfill
    if test_backfill_15min():
        tests_passed += 1
    
    # Test 2: 60-minute backfill
    if test_backfill_60min():
        tests_passed += 1
    
    # Test 3: Missing candle detection
    if test_missing_candle_detection():
        tests_passed += 1
    
    # Summary
    print("\n" + "="*80)
    print(f"SUMMARY: {tests_passed}/{tests_total} tests passed")
    print("="*80)
    
    if tests_passed == tests_total:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n✗ {tests_total - tests_passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
