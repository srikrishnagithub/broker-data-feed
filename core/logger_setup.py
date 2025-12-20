"""
Logging setup with daily rotation.
Creates a new log file each day automatically.
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from pathlib import Path


def setup_logger(name: str = "broker_data_feed", log_dir: str = "logs") -> logging.Logger:
    """
    Set up logger with both console and file output.
    
    Creates a new log file each day automatically.
    
    Args:
        name: Logger name
        log_dir: Directory to store log files (will be created if it doesn't exist)
        
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Format for log messages
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler (INFO and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler with daily rotation
    # When='midnight' rotates at midnight
    # backupCount=30 keeps 30 days of logs
    # Include date in the filename from the start
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(log_dir, f"{name}_{date_str}.log")
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Custom suffix for rotated files (keeps the date format consistent)
    file_handler.suffix = "%Y-%m-%d"
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "broker_data_feed") -> logging.Logger:
    """
    Get logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
