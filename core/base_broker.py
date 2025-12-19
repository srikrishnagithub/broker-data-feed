"""
Base broker interface for data feed service.
Defines the contract that all broker implementations must follow.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime


class TickData:
    """Standardized tick data structure."""
    
    def __init__(
        self,
        instrument_token: int,
        symbol: str,
        last_price: float,
        timestamp: datetime,
        volume: int = 0,
        oi: int = 0,
        depth: Optional[Dict[str, Any]] = None
    ):
        self.instrument_token = instrument_token
        self.symbol = symbol
        self.last_price = last_price
        self.timestamp = timestamp
        self.volume = volume
        self.oi = oi
        self.depth = depth or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'instrument_token': self.instrument_token,
            'symbol': self.symbol,
            'last_price': self.last_price,
            'timestamp': self.timestamp.isoformat(),
            'volume': self.volume,
            'oi': self.oi,
            'depth': self.depth
        }


class BaseBroker(ABC):
    """
    Abstract base class for broker implementations.
    All broker connectors must inherit from this class.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[Callable] = None):
        """
        Initialize broker with configuration.
        
        Args:
            config: Broker-specific configuration
            logger: Optional logging function
        """
        self.config = config
        self.logger = logger or self._default_logger
        self._connected = False
        self._instruments = []
    
    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logger."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to broker.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from broker."""
        pass
    
    @abstractmethod
    def subscribe(self, instruments: List[int]) -> bool:
        """
        Subscribe to instrument ticks.
        
        Args:
            instruments: List of instrument tokens to subscribe
            
        Returns:
            True if subscription successful, False otherwise
        """
        pass
    
    @abstractmethod
    def unsubscribe(self, instruments: List[int]) -> bool:
        """
        Unsubscribe from instrument ticks.
        
        Args:
            instruments: List of instrument tokens to unsubscribe
            
        Returns:
            True if unsubscription successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to broker.
        
        Returns:
            True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    def set_tick_callback(self, callback: Callable[[List[TickData]], None]):
        """
        Set callback function for tick data.
        
        Args:
            callback: Function to call when ticks are received
        """
        pass
    
    @abstractmethod
    def get_broker_name(self) -> str:
        """
        Get broker name.
        
        Returns:
            Name of the broker
        """
        pass
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test broker connection and return status.
        
        Returns:
            Dictionary with connection test results
        """
        try:
            if self.connect():
                status = {
                    'success': True,
                    'broker': self.get_broker_name(),
                    'connected': self.is_connected(),
                    'message': 'Connection test successful'
                }
                self.disconnect()
                return status
            else:
                return {
                    'success': False,
                    'broker': self.get_broker_name(),
                    'connected': False,
                    'message': 'Connection test failed'
                }
        except Exception as e:
            return {
                'success': False,
                'broker': self.get_broker_name(),
                'connected': False,
                'message': f'Connection test error: {str(e)}'
            }
