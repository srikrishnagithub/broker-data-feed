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

from broker_data_feed.config.config import Config
from broker_data_feed.core.database_handler import DatabaseHandler
from broker_data_feed.core.data_feed_service import DataFeedService
from broker_data_feed.brokers.kite_broker import KiteBroker


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
        # Import MQTT publisher from Trading-V2
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
        from trading.services.mqtt_publisher import HiveMQCloudPublisher
        
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


def load_instruments_from_database(db_handler: DatabaseHandler) -> list:
    """
    Load instruments from database.
    
    Args:
        db_handler: Database handler instance
        
    Returns:
        List of symbols
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT DISTINCT tradingsymbol 
            FROM merged_candles_5min 
            WHERE datetime >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY tradingsymbol
        """)
        
        with db_handler.engine.connect() as conn:
            result = conn.execute(query)
            symbols = [row[0] for row in result]
        
        log_message(f"Loaded {len(symbols)} symbols from database", "INFO")
        return symbols
        
    except Exception as e:
        log_message(f"Error loading instruments from database: {e}", "ERROR")
        return []


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
        
        # Test database if requested
        if args.test_database:
            log_message("Testing database connection...", "INFO")
            if db_handler.test_connection():
                log_message("Database connection test successful", "SUCCESS")
                
                # Check table existence
                if db_handler.check_table_exists('merged_candles_5min'):
                    log_message("Table 'merged_candles_5min' exists", "SUCCESS")
                else:
                    log_message("Table 'merged_candles_5min' not found", "WARNING")
                
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
        
        # Load symbols
        symbols = []
        if args.symbols:
            symbols = args.symbols
            log_message(f"Using command-line symbols: {len(symbols)} symbols", "INFO")
        elif args.symbols_file:
            symbols = load_instruments_from_file(args.symbols_file)
        elif args.symbols_from_db:
            symbols = load_instruments_from_database(db_handler)
        else:
            log_message("No symbols specified. Use --symbols, --symbols-file, or --symbols-from-db", "ERROR")
            return 1
        
        if not symbols:
            log_message("No symbols to subscribe", "ERROR")
            return 1
        
        # Load instrument tokens
        log_message("Loading instrument tokens...", "INFO")
        symbol_to_token = broker.load_instruments(symbols)
        
        if not symbol_to_token:
            log_message("Failed to load instrument tokens", "ERROR")
            return 1
        
        instruments = list(symbol_to_token.values())
        log_message(f"Loaded {len(instruments)} instrument tokens", "SUCCESS")
        
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
    except Exception as e:
        log_message(f"Fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
