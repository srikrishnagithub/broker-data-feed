#!/usr/bin/env python3
"""
Startup initialization script for broker data feed.

Performs backfill of missing 15-minute and 60-minute candles on startup.
This ensures data integrity by filling gaps from available lower-timeframe candles.

Usage:
    python scripts/startup_initialization.py
"""

import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database_handler import DatabaseHandler
from core.logger_setup import setup_logger


def main():
    """Run startup initialization."""
    
    # Setup logger
    logger_obj = setup_logger('startup_initialization')
    
    def log_message(message: str, level: str = "INFO"):
        """Wrapper function for logging."""
        level_upper = level.upper()
        if level_upper == "INFO":
            logger_obj.info(message)
        elif level_upper == "SUCCESS":
            logger_obj.info(message)
        elif level_upper == "WARNING":
            logger_obj.warning(message)
        elif level_upper == "ERROR":
            logger_obj.error(message)
        else:
            logger_obj.info(message)
    
    log_message("="*80, "INFO")
    log_message("BROKER DATA FEED STARTUP INITIALIZATION", "INFO")
    log_message("="*80, "INFO")
    log_message(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
    
    # Connect to database
    try:
        db = DatabaseHandler(logger=log_message)
        if not db.test_connection():
            log_message("Database connection failed!", "ERROR")
            sys.exit(1)
    except Exception as e:
        log_message(f"Failed to initialize database: {e}", "ERROR")
        sys.exit(1)
    
    try:
        # Run startup backfill
        log_message("\nStep 1: Running backfill for all symbols...", "INFO")
        results = db.startup_backfill_all_symbols()
        
        if results:
            log_message("\n✓ Backfill completed successfully", "SUCCESS")
        else:
            log_message("\nℹ No symbols to backfill or no missing candles", "INFO")
        
        # Check database health
        log_message("\nStep 2: Checking database health...", "INFO")
        
        tables_to_check = [
            ('live_candles_5min', '5-minute candles'),
            ('live_candles_15min', '15-minute candles'),
            ('live_candles_60min', '60-minute candles')
        ]
        
        for table_name, description in tables_to_check:
            if db.check_table_exists(table_name):
                health = db.check_data_health(table_name, max_age_minutes=60)
                if health['healthy']:
                    log_message(f"✓ {description}: {health['message']}", "SUCCESS")
                else:
                    log_message(f"⚠ {description}: {health['message']}", "WARNING")
            else:
                log_message(f"✗ {description} table not found", "ERROR")
        
        # Print final status
        log_message("\n" + "="*80, "INFO")
        log_message("STARTUP INITIALIZATION COMPLETE", "SUCCESS")
        log_message("="*80, "INFO")
        log_message(f"Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
        
        db.close()
        return 0
        
    except KeyboardInterrupt:
        log_message("\nStartup initialization interrupted by user", "WARNING")
        db.close()
        return 1
    except Exception as e:
        log_message(f"Error during startup initialization: {e}", "ERROR")
        import traceback
        log_message(f"Traceback: {traceback.format_exc()}", "ERROR")
        db.close()
        return 1


if __name__ == '__main__':
    sys.exit(main())
