#!/usr/bin/env python3
"""
Test KOTAK NEO REST API quotes fetching.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_kotak_quotes():
    """Test fetching quotes from KOTAK NEO REST API."""
    print("=" * 60)
    print("KOTAK NEO REST API Quotes Test")
    print("=" * 60)
    print()
    
    try:
        from brokers.kotak_neo_broker import KotakNeoBroker
        from config.config import Config
        import os
        
        # Get config
        config_obj = Config()
        broker_config = config_obj.get_broker_config('kotak')
        
        # Initialize broker
        print("1. Initializing KOTAK NEO broker...")
        broker = KotakNeoBroker(broker_config, logger=lambda msg, level: print(f"[{level}] {msg}"))
        
        # Authenticate
        print("\n2. Authenticating...")
        if not broker.connect():
            print("❌ Authentication failed")
            return False
        
        print("✅ Authentication successful!")
        
        # Test with a few symbols
        test_symbols = ['RELIANCE', 'INFY', 'TCS']
        
        print(f"\n3. Loading instruments for {test_symbols}...")
        symbol_tokens = broker.load_instruments(test_symbols)
        print(f"✅ Loaded {len(symbol_tokens)} instruments")
        
        # Subscribe
        print(f"\n4. Subscribing to instruments...")
        tokens = list(symbol_tokens.values())
        if broker.subscribe(tokens):
            print(f"✅ Subscribed to {len(tokens)} instruments")
        else:
            print("❌ Subscription failed")
            return False
        
        # Fetch quotes
        print(f"\n5. Fetching quotes for {test_symbols}...")
        quotes = broker.fetch_quotes(test_symbols)
        
        if not quotes:
            print("❌ No quotes received")
            return False
        
        print(f"✅ Received {len(quotes)} quotes")
        
        # Display quotes
        print("\n" + "=" * 60)
        print("Quote Data:")
        print("=" * 60)
        for quote in quotes:
            symbol = quote.get('display_symbol', 'N/A')
            ltp = quote.get('ltp', 'N/A')
            change = quote.get('change', 'N/A')
            per_change = quote.get('per_change', 'N/A')
            volume = quote.get('last_volume', 'N/A')
            
            print(f"\n📊 {symbol}")
            print(f"   LTP: {ltp}")
            print(f"   Change: {change} ({per_change}%)")
            print(f"   Volume: {volume}")
            
            # OHLC
            ohlc = quote.get('ohlc', {})
            if ohlc:
                print(f"   Open: {ohlc.get('open', 'N/A')}")
                print(f"   High: {ohlc.get('high', 'N/A')}")
                print(f"   Low: {ohlc.get('low', 'N/A')}")
                print(f"   Close: {ohlc.get('close', 'N/A')}")
        
        print("\n" + "=" * 60)
        print("✅ REST API quotes test successful!")
        print("=" * 60)
        
        # Disconnect
        broker.disconnect()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_kotak_quotes()
    sys.exit(0 if success else 1)
