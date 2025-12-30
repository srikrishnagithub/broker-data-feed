"""
Configuration management for broker data feed service.
"""
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Configuration management."""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_file: Optional path to .env file
        """
        if config_file:
            load_dotenv(config_file)
        else:
            load_dotenv()
    
    @staticmethod
    def get_database_config() -> Dict[str, Any]:
        """Get database configuration."""
        return {
            'connection_string': os.getenv('PG_CONN_STR'),
            'table_name': os.getenv('CANDLE_TABLE_NAME', 'merged_candles_5min')
        }
    
    @staticmethod
    def get_broker_config(broker_name: str = 'kite') -> Dict[str, Any]:
        """
        Get broker configuration.
        
        Args:
            broker_name: Name of broker (default: 'kite')
            
        Returns:
            Broker configuration dictionary
        """
        if broker_name.lower() == 'kite':
            return {
                'api_key': os.getenv('KITE_API_KEY'),
                'access_token': os.getenv('KITE_ACCESS_TOKEN'),
                'api_secret': os.getenv('KITE_API_SECRET')
            }
        elif broker_name.lower() == 'kotak' or broker_name.lower() == 'kotak_neo':
            return {
                'access_token': os.getenv('KOTAK_ACCESS_TOKEN'),
                'mobile_number': os.getenv('KOTAK_MOBILE_NUMBER'),
                'ucc': os.getenv('KOTAK_UCC'),
                'totp_secret': os.getenv('KOTAK_TOTP_SECRET'),
                'mpin': os.getenv('KOTAK_MPIN')
            }
        else:
            raise ValueError(f"Unsupported broker: {broker_name}")
    
    @staticmethod
    def get_mqtt_config() -> Optional[Dict[str, Any]]:
        """Get MQTT configuration if available."""
        broker = os.getenv('MQTT_BROKER')
        
        if not broker:
            return None
        
        return {
            'broker': broker,
            'port': int(os.getenv('MQTT_PORT', '8883')),
            'username': os.getenv('MQTT_USERNAME'),
            'password': os.getenv('MQTT_PASSWORD'),
            'use_tls': os.getenv('MQTT_USE_TLS', 'true').lower() == 'true',
            'keepalive': int(os.getenv('MQTT_KEEPALIVE', '60'))
        }
    
    @staticmethod
    def get_service_config() -> Dict[str, Any]:
        """Get service configuration."""
        return {
            'candle_intervals': [
                int(x.strip()) 
                for x in os.getenv('CANDLE_INTERVALS', '5').split(',')
            ],
            'heartbeat_interval': int(os.getenv('HEARTBEAT_INTERVAL', '30')),
            'log_level': os.getenv('LOG_LEVEL', 'INFO')
        }
    
    @staticmethod
    def get_instruments_file() -> Optional[str]:
        """Get path to instruments file."""
        return os.getenv('INSTRUMENTS_FILE')
    
    @staticmethod
    def validate(broker_name: str = 'kite') -> List[str]:
        """
        Validate configuration.
        
        Args:
            broker_name: Name of broker to validate (default: 'kite')
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check database connection
        if not os.getenv('PG_CONN_STR'):
            errors.append("PG_CONN_STR not set in environment")
        
        # Check broker-specific credentials
        if broker_name.lower() == 'kite':
            if not os.getenv('KITE_API_KEY'):
                errors.append("KITE_API_KEY not set in environment")
            
            if not os.getenv('KITE_ACCESS_TOKEN'):
                errors.append("KITE_ACCESS_TOKEN not set in environment")
        
        elif broker_name.lower() == 'kotak' or broker_name.lower() == 'kotak_neo':
            if not os.getenv('KOTAK_ACCESS_TOKEN'):
                errors.append("KOTAK_ACCESS_TOKEN not set in environment")
            
            if not os.getenv('KOTAK_MOBILE_NUMBER'):
                errors.append("KOTAK_MOBILE_NUMBER not set in environment")
            
            if not os.getenv('KOTAK_UCC'):
                errors.append("KOTAK_UCC not set in environment")
            
            if not os.getenv('KOTAK_TOTP_SECRET'):
                errors.append("KOTAK_TOTP_SECRET not set in environment")
            
            if not os.getenv('KOTAK_MPIN'):
                errors.append("KOTAK_MPIN not set in environment")
        
        return errors
