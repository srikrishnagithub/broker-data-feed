"""
MQTT Publisher Service for Trading-V2
Provides reusable MQTT connectivity to HiveMQ Cloud broker.
Can be used by any service that needs to publish data to MQTT topics.
"""
import json
import ssl
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Callable

import paho.mqtt.client as mqtt


class MQTTPublisher:
	"""
	Reusable MQTT publisher for HiveMQ Cloud.
	Handles connection, reconnection, and publishing with automatic retry.
	"""
    
	def __init__(
		self,
		broker: str,
		port: int,
		username: str,
		password: str,
		client_id_prefix: str = "trading_v2",
		keepalive: int = 60,
		use_tls: bool = True,
		logger: Optional[Callable] = None
	):
		"""
		Initialize MQTT Publisher.
        
		Args:
			broker: MQTT broker hostname
			port: MQTT broker port (8883 for TLS, 1883 for non-TLS)
			username: MQTT username
			password: MQTT password
			client_id_prefix: Prefix for client ID (timestamp will be appended)
			keepalive: Keep-alive interval in seconds
			use_tls: Whether to use TLS/SSL encryption
			logger: Optional logging function (default: print)
		"""
		self.broker = broker
		self.port = port
		self.username = username
		self.password = password
		self.client_id = f"{client_id_prefix}_{int(time.time())}"
		self.keepalive = keepalive
		self.use_tls = use_tls
		self.logger = logger or self._default_logger
        
		# Connection state
		self._client: Optional[mqtt.Client] = None
		self._connected = False
		self._lock = threading.Lock()
		self._connection_event = threading.Event()
        
	def _default_logger(self, message: str, level: str = "INFO"):
		"""Default logger that prints to console."""
		timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		print(f"[{timestamp}] [{level}] {message}")
    
	def _on_connect(self, client, userdata, flags, rc):
		"""Callback when connection is established."""
		with self._lock:
			if rc == 0:
				self._connected = True
				self._connection_event.set()
				self.logger("✅ Successfully connected to MQTT broker", "SUCCESS")
			else:
				self._connected = False
				error_messages = {
					1: "Connection refused - incorrect protocol version",
					2: "Connection refused - invalid client identifier",
					3: "Connection refused - server unavailable",
					4: "Connection refused - bad username or password",
					5: "Connection refused - not authorized"
				}
				error_msg = error_messages.get(rc, f"Unknown error (code: {rc})")
				self.logger(f"Failed to connect to MQTT broker: {error_msg}", "ERROR")
    
	def _on_disconnect(self, client, userdata, rc):
		"""Callback when connection is lost."""
		with self._lock:
			self._connected = False
			self._connection_event.clear()
            
		if rc != 0:
			self.logger(f"⚠️ Unexpected MQTT disconnection (code: {rc})", "WARNING")
		else:
			self.logger("MQTT client disconnected", "INFO")
    
	def _on_publish(self, client, userdata, mid):
		"""Callback when message is published."""
		self.logger(f"MQTT message published successfully (mid: {mid})", "DEBUG")
    
	def connect(self, timeout: float = 5.0) -> bool:
		"""
		Connect to MQTT broker.
        
		Args:
			timeout: Connection timeout in seconds
            
		Returns:
			True if connection successful, False otherwise
		"""
		try:
			self.logger(f"Initializing MQTT client (ID: {self.client_id})...", "INFO")
            
			# Create MQTT client
			self._client = mqtt.Client(client_id=self.client_id)
            
			# Set username and password
			self._client.username_pw_set(self.username, self.password)
            
			# Configure TLS/SSL if enabled
			if self.use_tls:
				self._client.tls_set(
					cert_reqs=ssl.CERT_REQUIRED,
					tls_version=ssl.PROTOCOL_TLS
				)
            
			# Set callbacks
			self._client.on_connect = self._on_connect
			self._client.on_disconnect = self._on_disconnect
			self._client.on_publish = self._on_publish
            
			# Connect to broker
			self.logger(f"Connecting to MQTT broker: {self.broker}:{self.port}", "INFO")
			self._client.connect(self.broker, self.port, self.keepalive)
            
			# Start network loop in background thread
			self._client.loop_start()
            
			# Wait for connection with timeout
			if self._connection_event.wait(timeout=timeout):
				self.logger("MQTT client ready", "SUCCESS")
				return True
			else:
				self.logger(f"MQTT connection timeout after {timeout}s", "WARNING")
				return False
                
		except Exception as e:
			self.logger(f"Failed to connect to MQTT broker: {e}", "ERROR")
			return False
    
	def disconnect(self):
		"""Disconnect from MQTT broker."""
		if self._client:
			try:
				self.logger("Disconnecting MQTT client...", "INFO")
				self._client.loop_stop()
				self._client.disconnect()
				with self._lock:
					self._connected = False
				self.logger("MQTT client disconnected", "INFO")
			except Exception as e:
				self.logger(f"Error during MQTT disconnection: {e}", "WARNING")
    
	def is_connected(self) -> bool:
		"""Check if connected to MQTT broker."""
		with self._lock:
			return self._connected
    
	def publish(
		self,
		topic: str,
		payload: Any,
		qos: int = 1,
		retain: bool = False,
		as_json: bool = True
	) -> bool:
		"""
		Publish message to MQTT topic.
        
		Args:
			topic: MQTT topic to publish to
			payload: Message payload (will be JSON-encoded if as_json=True)
			qos: Quality of Service level (0, 1, or 2)
			retain: Whether broker should retain message
			as_json: Whether to JSON-encode the payload
            
		Returns:
			True if publish successful, False otherwise
		"""
		if not self.is_connected():
			self.logger("Cannot publish: MQTT not connected", "WARNING")
			return False
        
		try:
			# Convert payload to string
			if as_json:
				if isinstance(payload, (dict, list)):
					message = json.dumps(payload, default=str)
				else:
					message = json.dumps({"data": payload}, default=str)
			else:
				message = str(payload)
            
			# Publish to MQTT topic
			result = self._client.publish(topic, message, qos=qos, retain=retain)
            
			if result.rc == mqtt.MQTT_ERR_SUCCESS:
				self.logger(f"📡 Published to {topic}: {len(message)} bytes", "DEBUG")
				return True
			else:
				self.logger(f"MQTT publish failed with code: {result.rc}", "WARNING")
				return False
                
		except Exception as e:
			self.logger(f"Error publishing to MQTT: {e}", "ERROR")
			return False
    
	def publish_heartbeat(
		self,
		topic: str,
		service_name: str,
		additional_data: Optional[Dict[str, Any]] = None
	) -> bool:
		"""
		Publish standardized heartbeat message.
        
		Args:
			topic: MQTT topic to publish to
			service_name: Name of the service sending heartbeat
			additional_data: Additional data to include in heartbeat
            
		Returns:
			True if publish successful, False otherwise
		"""
		heartbeat = {
			"timestamp": datetime.now().isoformat(),
			"service": service_name,
			"status": "alive"
		}
        
		if additional_data:
			heartbeat.update(additional_data)
        
		return self.publish(topic, heartbeat, qos=1)
    
	def __enter__(self):
		"""Context manager entry."""
		self.connect()
		return self
    
	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit."""
		self.disconnect()


class HiveMQCloudPublisher(MQTTPublisher):
	"""
	Pre-configured MQTT publisher for HiveMQ Cloud.
	Uses credentials from Trading-V2 configuration.
	"""
    
	# HiveMQ Cloud Configuration
	DEFAULT_BROKER = "51fb84d3a946481dbf0a1351b502c29d.s1.eu.hivemq.cloud"
	DEFAULT_PORT = 8883
	DEFAULT_USERNAME = "hivemq.webclient.1765708687167"
	DEFAULT_PASSWORD = "z72*;D1jIs:Z%Xx0ArCe"
    
	def __init__(
		self,
		client_id_prefix: str = "trading_v2",
		logger: Optional[Callable] = None
	):
		"""
		Initialize HiveMQ Cloud publisher with default credentials.
        
		Args:
			client_id_prefix: Prefix for client ID
			logger: Optional logging function
		"""
		super().__init__(
			broker=self.DEFAULT_BROKER,
			port=self.DEFAULT_PORT,
			username=self.DEFAULT_USERNAME,
			password=self.DEFAULT_PASSWORD,
			client_id_prefix=client_id_prefix,
			keepalive=60,
			use_tls=True,
			logger=logger
		)


# Example usage and testing
if __name__ == "__main__":
	"""Test the MQTT publisher."""
    
	def test_logger(message: str, level: str = "INFO"):
		"""Custom logger for testing."""
		timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		print(f"[{timestamp}] [{level}] {message}")
    
	# Test HiveMQ Cloud publisher
	print("Testing HiveMQ Cloud MQTT Publisher...")
	print("-" * 50)
    
	publisher = HiveMQCloudPublisher(
		client_id_prefix="test_mqtt",
		logger=test_logger
	)
    
	# Connect
	if publisher.connect(timeout=10):
		print("\n✅ Connection successful!\n")
        
		# Test publish
		test_data = {
			"test_timestamp": datetime.now().isoformat(),
			"test_value": 123.45,
			"test_message": "Hello from Trading-V2 MQTT Publisher!"
		}
        
		success = publisher.publish("test_topic", test_data)
		print(f"\nPublish result: {'✅ Success' if success else '❌ Failed'}\n")
        
		# Test heartbeat
		success = publisher.publish_heartbeat(
			topic="heartbeat_test",
			service_name="mqtt_publisher_test",
			additional_data={"test_run": True}
		)
		print(f"Heartbeat result: {'✅ Success' if success else '❌ Failed'}\n")
        
		# Wait a bit
		time.sleep(2)
        
		# Disconnect
		publisher.disconnect()
		print("\n✅ Disconnected successfully!")
	else:
		print("\n❌ Connection failed!")
    
	print("-" * 50)
	print("Test complete!")