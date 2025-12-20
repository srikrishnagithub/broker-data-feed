"""
Main entry point for broker data feed service.
Independent live OHLC data feeding service.
"""
import os
import sys
import signal
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from core.database_handler import DatabaseHandler
from core.data_feed_service import DataFeedService
from brokers.kite_broker import KiteBroker


def log_message(message: str, level: str = "INFO"):
    """Logging function."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def setup_mqtt_publisher(config):
    """
    Setup MQTT publisher if configured.
    
    Args:
        config: Configuration object
        
    Returns:
        MQTT publisher instance or None
    """
    mqtt_config = config.get_mqtt_config()
    
    if not mqtt_config:
        log_message("MQTT not configured - skipping", "INFO")
        return None
    
    try:
        # Import MQTT publisher from brokers.mqtt_publisher
        from brokers.mqtt_publisher import HiveMQCloudPublisher
        
        log_message("Initializing MQTT publisher...", "INFO")
        publisher = HiveMQCloudPublisher(
            client_id_prefix="broker_data_feed",
            logger=log_message
        )
        
        if publisher.connect(timeout=5.0):
            log_message("MQTT publisher connected", "SUCCESS")
            return publisher
        else:
            log_message("MQTT connection failed - continuing without MQTT", "WARNING")
            return None
            
    except Exception as e:
        log_message(f"Failed to setup MQTT: {e}", "WARNING")
        return None


def load_instruments_from_file(file_path: str) -> list:
    """
    Load instruments from file.
    
    Args:
        file_path: Path to instruments file (one symbol per line)
        
    Returns:
        List of symbols
    """
    try:
        with open(file_path, 'r') as f:
            symbols = [line.strip() for line in f if line.strip()]
        log_message(f"Loaded {len(symbols)} symbols from {file_path}", "INFO")
        return symbols
    except Exception as e:
        log_message(f"Error loading instruments file: {e}", "ERROR")
        return []


def check_required_tables(db_handler: DatabaseHandler) -> bool:
    """
    Check if all required tables exist and have data.
    
    Args:
        db_handler: Database handler instance
        
    Returns:
        True if all checks pass, False otherwise
    """
    required_tables = ['fundamental', 'instruments']
    optional_tables = ['merged_candles_5min']
    
    # Check required tables
    for table in required_tables:
        if not db_handler.check_table_exists(table):
            log_message(f"Required table '{table}' does not exist", "ERROR")
            return False
        else:
            log_message(f"Table '{table}' exists", "SUCCESS")
    
    # Check optional tables (warning only)
    for table in optional_tables:
        if not db_handler.check_table_exists(table):
            log_message(f"Optional table '{table}' does not exist (will be created/populated by service)", "WARNING")
        else:
            log_message(f"Table '{table}' exists", "SUCCESS")
    
    # Check if fundamental table has data
    try:
        from sqlalchemy import text
        with db_handler.engine.connect() as conn:
            result = conn.execute(text('SELECT COUNT(*) FROM fundamental WHERE "SYMBOL" IS NOT NULL'))
            count = result.fetchone()[0] # type: ignore
            if count == 0:
                log_message("Fundamental table exists but contains no symbols", "ERROR")
                return False
            else:
                log_message(f"Fundamental table contains {count} symbols", "SUCCESS")
            
            # Check if instruments table has data
            result = conn.execute(text('SELECT COUNT(*) FROM instruments'))
            count = result.fetchone()[0] # type: ignore
            if count == 0:
                log_message("Instruments table exists but contains no data", "ERROR")
                return False
            else:
                log_message(f"Instruments table contains {count} instruments", "SUCCESS")
                
    except Exception as e:
        log_message(f"Error checking table data: {e}", "ERROR")
        return False
    
    return True


def load_instruments_from_database(db_handler: DatabaseHandler) -> dict:
    """
    Load instruments from database - symbols from Fundamental table with tokens from instruments table.
    
    Args:
        db_handler: Database handler instance
        
    Returns:
        Dictionary mapping symbols to instrument tokens
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT DISTINCT 
                f."SYMBOL" as tradingsymbol,
                i.instrument_token
            FROM fundamental f
            JOIN instruments i ON f."SYMBOL" = i.tradingsymbol
            ORDER BY f."SYMBOL"
        """)
        
        with db_handler.engine.connect() as conn:
            result = conn.execute(query)
            symbol_to_token = {row[0]: row[1] for row in result}
        
        log_message(f"Loaded {len(symbol_to_token)} symbols with instrument tokens from database", "INFO")
        return symbol_to_token
        
    except Exception as e:
        log_message(f"Error loading instruments from database: {e}", "ERROR")
        return {}


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Broker Data Feed Service - Independent live OHLC data feeding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with symbols from file
  python main.py --symbols-file instruments.txt
  
  # Start with specific symbols
  python main.py --symbols RELIANCE INFY TCS
  
  # Start with database symbols
  python main.py --symbols-from-db
  
  # Test broker connection
  python main.py --test-broker

Environment variables required:
  PG_CONN_STR - PostgreSQL connection string
  KITE_API_KEY - Kite API key
  KITE_ACCESS_TOKEN - Kite access token
  
Optional environment variables:
  CANDLE_INTERVALS - Comma-separated intervals in minutes (default: 5)
  HEARTBEAT_INTERVAL - Heartbeat interval in seconds (default: 30)
  MQTT_BROKER - MQTT broker hostname (optional)
  MQTT_USERNAME - MQTT username (optional)
  MQTT_PASSWORD - MQTT password (optional)
        """
    )
    
    parser.add_argument('--symbols', nargs='+',
                       help='List of trading symbols to subscribe')
    parser.add_argument('--symbols-file',
                       help='File containing symbols (one per line)')
    parser.add_argument('--symbols-from-db', action='store_true',
                       help='Load symbols from database')
    parser.add_argument('--test-broker', action='store_true',
                       help='Test broker connection and exit')
    parser.add_argument('--test-database', action='store_true',
                       help='Test database connection and exit')
    parser.add_argument('--config-file',
                       help='Path to custom .env configuration file')
    
    return parser.parse_args()


def main():
    """Main entry point."""
    log_message("=== Broker Data Feed Service Starting ===", "INFO")
    
    try:
        # Parse arguments
        args = parse_arguments()
        
        # Load configuration
        config = Config(args.config_file)
        
        # Validate configuration
        errors = config.validate()
        if errors:
            log_message("Configuration validation failed:", "ERROR")
            for error in errors:
                log_message(f"  - {error}", "ERROR")
            return 1
        
        # Get configurations
        db_config = config.get_database_config()
        broker_config = config.get_broker_config('kite')
        service_config = config.get_service_config()
        
        # Initialize database handler
        log_message("Initializing database handler...", "INFO")
        db_handler = DatabaseHandler(
            connection_string=db_config['connection_string'],
            logger=log_message
        )
        
        # Check required tables
        log_message("Checking required database tables...", "INFO")
        if not check_required_tables(db_handler):
            log_message("Required database tables check failed", "ERROR")
            return 1
        
        # Test database if requested
        if args.test_database:
            log_message("Testing database connection...", "INFO")
            if db_handler.test_connection():
                log_message("Database connection test successful", "SUCCESS")
                
                # Check required tables
                if check_required_tables(db_handler):
                    log_message("All required tables are present and populated", "SUCCESS")
                else:
                    log_message("Required tables check failed", "ERROR")
                
                return 0
            else:
                log_message("Database connection test failed", "ERROR")
                return 1
        
        # Initialize broker
        log_message("Initializing Kite broker...", "INFO")
        broker = KiteBroker(broker_config, logger=log_message)
        
        # Test broker if requested
        if args.test_broker:
            log_message("Testing broker connection...", "INFO")
            result = broker.test_connection()
            
            if result['success']:
                log_message(f"Broker test successful: {result['message']}", "SUCCESS")
                return 0
            else:
                log_message(f"Broker test failed: {result['message']}", "ERROR")
                return 1
        
        # Load symbols and instrument tokens
        symbol_to_token = {}
        if args.symbols:
            symbols = args.symbols
            log_message(f"Using command-line symbols: {len(symbols)} symbols", "INFO")
            # Load instrument tokens from broker
            log_message("Loading instrument tokens from broker...", "INFO")
            symbol_to_token = broker.load_instruments(symbols)
        elif args.symbols_file:
            symbols = load_instruments_from_file(args.symbols_file)
            if symbols:
                log_message("Loading instrument tokens from broker...", "INFO")
                symbol_to_token = broker.load_instruments(symbols)
        elif args.symbols_from_db:
            log_message("Loading symbols and instrument tokens from database...", "INFO")
            symbol_to_token = load_instruments_from_database(db_handler)
            symbols = list(symbol_to_token.keys())
            
            # Populate broker's internal mapping
            if symbol_to_token:
                broker._token_to_symbol = {token: symbol for symbol, token in symbol_to_token.items()}
                log_message("Populated broker's token-to-symbol mapping", "INFO")
        else:
            log_message("No symbols specified. Use --symbols, --symbols-file, or --symbols-from-db", "ERROR")
            return 1
        
        if not symbol_to_token:
            log_message("No instrument tokens loaded", "ERROR")
            return 1
        
        instruments = list(symbol_to_token.values())
        log_message(f"Loaded {len(instruments)} instrument tokens for {len(symbols)} symbols", "SUCCESS")
        
        # Setup MQTT (optional)
        mqtt_publisher = setup_mqtt_publisher(config)
        
        # Initialize data feed service
        log_message("Initializing data feed service...", "INFO")
        service = DataFeedService(
            broker=broker,
            database=db_handler,
            candle_intervals=service_config['candle_intervals'],
            mqtt_publisher=mqtt_publisher,
            logger=log_message
        )
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            log_message("Shutdown signal received", "INFO")
            service.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start service
        log_message(f"Starting service with {len(instruments)} instruments...", "INFO")
        log_message(f"Candle intervals: {service_config['candle_intervals']} minutes", "INFO")
        log_message(f"Heartbeat interval: {service_config['heartbeat_interval']} seconds", "INFO")
        
        service.start(instruments, symbols)
        
        return 0
        
    except KeyboardInterrupt:
        log_message("Keyboard interrupt received", "INFO")
        return 0
    except RuntimeError as e:
        # Check for specific broker connection error
        error_str = str(e)
        if "Broker connection failed" in error_str:
            log_message("BROKER CONNECTION FAILED", "ERROR")
            log_message("", "ERROR")
            log_message("This usually means invalid or expired Kite API credentials.", "ERROR")
            log_message("Please check your .env file and ensure:", "ERROR")
            log_message("  - KITE_API_KEY is correct", "ERROR")
            log_message("  - KITE_ACCESS_TOKEN is valid (not expired)", "ERROR")
            log_message("  - You have a valid Kite subscription", "ERROR")
            log_message("", "ERROR")
            
            # Check what credentials are actually being used
            api_key = os.getenv('KITE_API_KEY', 'NOT_SET')
            access_token = os.getenv('KITE_ACCESS_TOKEN', 'NOT_SET')
            
            if len(api_key) > 10:
                masked_api = api_key[:6] + "..." + api_key[-4:]
                log_message(f"API Key being used: {masked_api}", "ERROR")
            else:
                log_message("API Key: NOT_SET", "ERROR")
                
            if len(access_token) > 10:
                masked_token = access_token[:6] + "..." + access_token[-4:]
                log_message(f"Access Token being used: {masked_token}", "ERROR")
            else:
                log_message("Access Token: NOT_SET", "ERROR")
            
            log_message("", "ERROR")
            log_message("IMPORTANT: Make sure the API key and access token are from the SAME Kite app!", "ERROR")
            log_message("If you just updated the .env file:", "ERROR")
            log_message("  - Try restarting your terminal/command prompt", "ERROR")
            log_message("  - Or run: python main.py --test-broker", "ERROR")
            log_message("", "ERROR")
            log_message("To get new credentials:", "ERROR")
            log_message("  1. Visit: https://developers.kite.trade/", "ERROR")
            log_message("  2. Login with your Kite credentials", "ERROR")
            log_message("  3. Generate a new access token", "ERROR")
            log_message("  4. Update your .env file", "ERROR")
            
            # Generate and display login URL following kite_token_manager.py pattern
            try:
                from kiteconnect import KiteConnect
                api_key = config.get_broker_config('kite').get('api_key') # type: ignore
                if api_key:
                    kite_temp = KiteConnect(api_key=api_key)
                    login_url = kite_temp.login_url()
                    log_message("", "ERROR")
                    log_message("Direct login URL:", "ERROR")
                    log_message(f"   {login_url}", "ERROR")
                    log_message("", "ERROR")
                    log_message("Copy this URL and paste it in your browser to get a new access token.", "ERROR")
                else:
                    log_message("Could not generate login URL - KITE_API_KEY not found", "ERROR")
            except Exception as url_error:
                log_message(f"Could not generate login URL: {url_error}", "ERROR")
            
            log_message("", "ERROR")
            log_message("To test credentials: python main.py --test-broker", "ERROR")
            return 1
        else:
            # Re-raise other RuntimeErrors
            log_message(f"A runtime error occurred: {e}", "ERROR")
            return 1
    except Exception as e:
        log_message(f"Fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
