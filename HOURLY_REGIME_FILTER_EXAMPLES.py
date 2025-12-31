"""
Example: Using the Hourly Regime Filter in Your Signal Generator

This file demonstrates how to integrate the forming hourly candle logic
into your existing signal generation system.
"""

# ============================================================================
# EXAMPLE 1: Basic Signal Evaluation with Hourly Regime Check
# ============================================================================

def example_basic_signal_evaluation():
    """
    Simplest way to check if a signal passes the hourly regime filter.
    """
    from core.database_handler import DatabaseHandler
    from core.signal_generator import SignalGenerator
    from datetime import datetime
    
    # Initialize
    db = DatabaseHandler()  # Uses PG_CONN_STR from environment
    signal_gen = SignalGenerator(db)
    
    # Signal parameters
    symbol = 'RELIANCE'
    signal_time = datetime.now()  # e.g., 13:30:57
    signal_type = 'LONG'  # or 'SHORT'
    
    # Check if signal passes hourly regime filter
    passes_regime, details = signal_gen.check_hourly_regime(
        symbol=symbol,
        current_datetime=signal_time,
        signal_type=signal_type
    )
    
    if passes_regime:
        print(f"✅ Signal {signal_type} {symbol} APPROVED")
        print(f"   EMA20: {details['ema20']:.4f}")
        print(f"   EMA50: {details['ema50']:.4f}")
        print(f"   Regime: {details['regime']}")
        # Place your order here
        return True
    else:
        print(f"❌ Signal {signal_type} {symbol} REJECTED")
        print(f"   Reason: {details['reason']}")
        return False


# ============================================================================
# EXAMPLE 2: Complete Signal Evaluation with Additional Checks
# ============================================================================

def example_complete_signal_evaluation():
    """
    Full signal evaluation including hourly regime plus additional checks.
    """
    from core.database_handler import DatabaseHandler
    from core.signal_generator import SignalGenerator
    from datetime import datetime
    
    def check_price_action(symbol, current_price):
        """Your custom price action check."""
        # Your logic here
        return True  # Returns True if check passes
    
    def check_volume(symbol, volume):
        """Your custom volume check."""
        # Your logic here
        return True  # Returns True if check passes
    
    # Initialize
    db = DatabaseHandler()
    signal_gen = SignalGenerator(db)
    
    # Signal parameters
    symbol = 'INFY'
    current_price = 1650.50
    volume = 45000
    signal_time = datetime.now()
    signal_type = 'LONG'
    
    # Run your custom checks
    price_action_ok = check_price_action(symbol, current_price)
    volume_ok = check_volume(symbol, volume)
    
    # Evaluate complete signal with all checks
    passes, evaluation = signal_gen.evaluate_signal(
        symbol=symbol,
        current_datetime=signal_time,
        signal_type=signal_type,
        additional_checks={
            'price_action': price_action_ok,
            'volume_confirmation': volume_ok,
        }
    )
    
    if passes:
        print(f"✅ ALL CHECKS PASSED for {signal_type} {symbol}")
        
        # Show each check result
        for check_name, check_details in evaluation['checks'].items():
            if isinstance(check_details, dict) and 'passes_filter' in check_details:
                status = "✓" if check_details['passes_filter'] else "✗"
                print(f"   {status} {check_name}: {check_details.get('reason', 'passed')}")
            else:
                status = "✓" if check_details else "✗"
                print(f"   {status} {check_name}: {'passed' if check_details else 'failed'}")
        
        return True
    else:
        print(f"❌ SIGNAL REJECTED for {signal_type} {symbol}")
        
        # Show which check failed
        for check_name, check_details in evaluation['checks'].items():
            if isinstance(check_details, dict) and 'passes_filter' in check_details:
                if not check_details['passes_filter']:
                    print(f"   Failed on: {check_name}")
                    print(f"   Reason: {check_details.get('reason', 'unknown')}")
                    break
            elif not check_details:
                print(f"   Failed on: {check_name}")
                break
        
        return False


# ============================================================================
# EXAMPLE 3: Direct Forming Candle Building (Advanced)
# ============================================================================

def example_direct_forming_candle():
    """
    Directly build a forming hourly candle without signal evaluation.
    Useful if you want to use the forming candle independently.
    """
    from core.hourly_candle_builder import build_forming_hourly_candle
    from core.database_handler import DatabaseHandler
    import pandas as pd
    from datetime import datetime
    
    # Initialize
    db = DatabaseHandler()
    
    # Get 15-minute candles from database
    from sqlalchemy import text
    
    symbol = 'TCS'
    current_time = datetime.now()
    
    # Fetch 15-min candles
    query = text("""
        SELECT datetime, open, high, low, close, volume
        FROM live_candles_15min
        WHERE tradingsymbol = :symbol
        ORDER BY datetime DESC
        LIMIT 20
    """)
    
    with db.engine.connect() as conn:
        result = conn.execute(query, {"symbol": symbol})
        rows = result.fetchall()
    
    if not rows:
        print(f"No 15-minute candles found for {symbol}")
        return None
    
    # Convert to DataFrame
    min15_df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
    
    # Build forming hourly candle
    forming_candle = build_forming_hourly_candle(
        symbol=symbol,
        current_datetime=current_time,
        candles_15min=min15_df
    )
    
    if forming_candle:
        print(f"✅ Forming Candle Built for {symbol}")
        print(f"   Time: {forming_candle['datetime']}")
        print(f"   Open: {forming_candle['open']:.2f}")
        print(f"   High: {forming_candle['high']:.2f}")
        print(f"   Low: {forming_candle['low']:.2f}")
        print(f"   Close: {forming_candle['close']:.2f}")
        print(f"   Volume: {forming_candle['volume']}")
        print(f"   15-min candles aggregated: {forming_candle['tick_count']}")
        return forming_candle
    else:
        print(f"Could not build forming candle for {symbol}")
        return None


# ============================================================================
# EXAMPLE 4: Batch Evaluation Across Multiple Symbols
# ============================================================================

def example_batch_signal_evaluation(symbols, signal_type='LONG'):
    """
    Evaluate signals for multiple symbols in one go.
    """
    from core.database_handler import DatabaseHandler
    from core.signal_generator import SignalGenerator
    from datetime import datetime
    
    # Initialize
    db = DatabaseHandler()
    signal_gen = SignalGenerator(db)
    
    # Current time (same for all signals)
    current_time = datetime.now()
    
    # Evaluate each symbol
    results = {}
    approved_signals = []
    rejected_signals = []
    
    for symbol in symbols:
        passes, details = signal_gen.check_hourly_regime(
            symbol=symbol,
            current_datetime=current_time,
            signal_type=signal_type
        )
        
        results[symbol] = {
            'passes': passes,
            'ema20': details.get('ema20'),
            'ema50': details.get('ema50'),
            'regime': details.get('regime'),
            'reason': details.get('reason')
        }
        
        if passes:
            approved_signals.append(symbol)
        else:
            rejected_signals.append(symbol)
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"BATCH SIGNAL EVALUATION - {signal_type} signals")
    print(f"Time: {current_time.isoformat()}")
    print(f"{'='*70}")
    
    print(f"\n✅ APPROVED SIGNALS ({len(approved_signals)}):")
    for symbol in approved_signals:
        r = results[symbol]
        print(f"   {symbol}: EMA20={r['ema20']:.4f} > EMA50={r['ema50']:.4f} ({r['regime']})")
    
    print(f"\n❌ REJECTED SIGNALS ({len(rejected_signals)}):")
    for symbol in rejected_signals:
        r = results[symbol]
        print(f"   {symbol}: {r['reason']}")
    
    print(f"\n{'='*70}\n")
    
    return approved_signals, rejected_signals


# ============================================================================
# EXAMPLE 5: Real-Time Signal Processing Loop
# ============================================================================

def example_real_time_signal_processing():
    """
    Example of a real-time signal processing loop.
    This shows how to integrate hourly regime check into your signal handler.
    """
    from core.database_handler import DatabaseHandler
    from core.signal_generator import SignalGenerator
    from datetime import datetime
    import time
    
    # Initialize
    db = DatabaseHandler()
    signal_gen = SignalGenerator(db)
    
    # Your signal queue (from your signal detection system)
    signal_queue = []  # [(symbol, signal_type, timestamp), ...]
    
    # Processing loop
    print("Starting real-time signal processing...")
    print("(This is a conceptual example - adapt to your actual signal source)")
    
    while True:
        # Get signals (this would come from your scanner/detector)
        # signals = get_signals_from_your_system()
        
        # For this example, we'll skip actual signal fetching
        # signals = signal_queue if signal_queue else []
        signals = []  # Empty for this demo
        
        if not signals:
            print(f"[{datetime.now().isoformat()}] No signals... waiting")
            time.sleep(5)
            continue
        
        # Process each signal
        for symbol, signal_type, signal_time in signals:
            print(f"\nProcessing signal: {signal_type} {symbol} @ {signal_time}")
            
            # Check hourly regime
            passes, details = signal_gen.check_hourly_regime(
                symbol=symbol,
                current_datetime=signal_time,
                signal_type=signal_type
            )
            
            if passes:
                print(f"✅ APPROVED: Place {signal_type} order for {symbol}")
                print(f"   EMA20={details['ema20']:.4f} > EMA50={details['ema50']:.4f}")
                # HERE: Place your actual order
                # place_order(symbol, signal_type, ...)
            else:
                print(f"❌ REJECTED: {details['reason']}")
            
            # Remove processed signal
            signal_queue.remove((symbol, signal_type, signal_time))


# ============================================================================
# EXAMPLE 6: Logging and Debugging
# ============================================================================

def example_with_custom_logging():
    """
    Example showing how to use custom logging with the signal generator.
    """
    from core.database_handler import DatabaseHandler
    from core.signal_generator import SignalGenerator
    from datetime import datetime
    
    def custom_logger(message: str, level: str = "INFO"):
        """Your custom logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Send to your logging system (file, cloud, etc.)
        print(f"[{timestamp}] [{level}] {message}")
        # You could also:
        # logger.log(level, message)
        # sentry.capture_message(message, level)
        # cloudwatch.put_metric_data(...)
    
    # Initialize with custom logger
    db = DatabaseHandler(logger=custom_logger)
    signal_gen = SignalGenerator(db, logger=custom_logger)
    
    # Now all logging will use your custom logger
    symbol = 'HDFCBANK'
    passes, details = signal_gen.check_hourly_regime(
        symbol=symbol,
        current_datetime=datetime.now(),
        signal_type='LONG'
    )
    
    # You'll see detailed logging output with your custom logger
    print(f"\nResult: {'APPROVED' if passes else 'REJECTED'}")


# ============================================================================
# EXAMPLE 7: Error Handling and Recovery
# ============================================================================

def example_error_handling():
    """
    Example showing proper error handling when using the signal generator.
    """
    from core.database_handler import DatabaseHandler
    from core.signal_generator import SignalGenerator
    from datetime import datetime
    
    symbol = 'MARUTI'
    
    try:
        # Initialize
        db = DatabaseHandler()
        signal_gen = SignalGenerator(db)
        
        # Check hourly regime with error handling
        passes, details = signal_gen.check_hourly_regime(
            symbol=symbol,
            current_datetime=datetime.now(),
            signal_type='LONG'
        )
        
        if passes:
            print(f"✅ Signal approved for {symbol}")
        else:
            print(f"⚠️ Signal rejected: {details['reason']}")
    
    except ValueError as e:
        # Database connection string issues
        print(f"❌ Configuration error: {e}")
        print("   Check that PG_CONN_STR environment variable is set correctly")
    
    except ConnectionError as e:
        # Database connection failed
        print(f"❌ Database connection error: {e}")
        print("   Check that database server is running and accessible")
    
    except Exception as e:
        # Catch-all for unexpected errors
        print(f"❌ Unexpected error: {e}")
        print("   Consider failing safely (rejecting the signal) rather than crashing")


# ============================================================================
# MAIN: Run Examples
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*70)
    print("HOURLY REGIME FILTER - USAGE EXAMPLES")
    print("="*70)
    
    print("\n--- Example 1: Basic Signal Evaluation ---")
    print("See: example_basic_signal_evaluation()")
    
    print("\n--- Example 2: Complete Signal Evaluation ---")
    print("See: example_complete_signal_evaluation()")
    
    print("\n--- Example 3: Direct Forming Candle Building ---")
    print("See: example_direct_forming_candle()")
    
    print("\n--- Example 4: Batch Evaluation ---")
    print("See: example_batch_signal_evaluation(['RELIANCE', 'INFY', 'TCS'])")
    
    print("\n--- Example 5: Real-Time Processing ---")
    print("See: example_real_time_signal_processing()")
    
    print("\n--- Example 6: Custom Logging ---")
    print("See: example_with_custom_logging()")
    
    print("\n--- Example 7: Error Handling ---")
    print("See: example_error_handling()")
    
    print("\n" + "="*70)
    print("To run an example, uncomment the function call below:")
    print("="*70 + "\n")
    
    # Uncomment to run examples:
    # example_basic_signal_evaluation()
    # example_complete_signal_evaluation()
    # example_direct_forming_candle()
    # example_batch_signal_evaluation(['RELIANCE', 'INFY', 'TCS', 'HDFCBANK'])
    # example_with_custom_logging()
    # example_error_handling()
