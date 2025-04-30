"""
Тесты для сетевого слоя
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.network import P2PNetwork, P2PConnection
from src.p2p_connection import NodeConnection
from src.crypto import CryptoManager
import pytest_asyncio
from dataclasses import dataclass
import random
from src.config import Config
from websockets.client import WebSocketClientProtocol
from websockets.server import WebSocketServerProtocol
from src.security import SecurityManager
import json

class MockConfig:
    def __init__(self):
        self.node_id = "test_node"
        
    def get_listen_address(self):
        return "127.0.0.1", 0
        
    def get_node_id(self):
        return self.node_id

class MockPeerDiscovery:
    def __init__(self):
        self.nodes = []
        
    async def start(self):
        pass
        
    async def stop(self):
        pass
        
    async def get_nodes(self):
        return self.nodes

@pytest_asyncio.fixture
async def network_pair():
    """Create two connected network nodes."""
    config1 = Config()
    config1.port = 8001
    config1.peer_discovery_port = 7001
    
    config2 = Config()
    config2.port = 8002
    config2.peer_discovery_port = 7002
    
    crypto1 = CryptoManager()
    crypto2 = CryptoManager()
    
    network1 = P2PNetwork(config1, crypto1)
    network2 = P2PNetwork(config2, crypto2)
    
    await network1.start()
    await network2.start()
    
    # Connect networks
    await network1.connect(f"ws://localhost:{config2.port}")
    
    yield network1, network2
    
    # Cleanup
    await network1.stop()
    await network2.stop()

@pytest_asyncio.fixture
async def crypto_manager():
    """Создает тестовый менеджер криптографии"""
    return CryptoManager()

@pytest_asyncio.fixture
async def security_manager(crypto_manager):
    """Создает тестовый менеджер безопасности"""
    return SecurityManager(crypto_manager)

@pytest_asyncio.fixture
async def connection(crypto_manager, security_manager):
    """Создает тестовое соединение"""
    conn = P2PConnection(
        host="localhost",
        port=8000,
        node_id="test_node",
        public_key="test_key",
        crypto_manager=crypto_manager,
        security_manager=security_manager
    )
    yield conn
    await conn.stop()

@pytest.mark.asyncio
async def test_connection_establishment(network_pair):
    """Test that two networks can establish a connection."""
    network1, network2 = network_pair
    
    # Wait for connection to be established
    await asyncio.sleep(0.1)
    
    assert len(network1.connections) == 1
    assert len(network2.connections) == 1
    assert network1.connections[0].remote_address.startswith("ws://localhost:")
    assert network2.connections[0].remote_address.startswith("ws://localhost:")

@pytest.mark.asyncio
async def test_message_exchange(network_pair):
    """Test that networks can exchange messages."""
    network1, network2 = network_pair
    messages = []
    
    def on_message(conn, msg):
        messages.append(msg)
    
    network2.on_message = on_message
    
    # Wait for connection to be established
    await asyncio.sleep(0.1)
    
    # Send message
    await network1.send_message(network1.connections[0].remote_address, "test message")
    
    # Wait for message to be received
    await asyncio.sleep(0.1)
    
    assert len(messages) == 1
    assert messages[0] == "test message"

@pytest.mark.asyncio
async def test_connection_loss(network_pair):
    """Test handling of connection loss."""
    network1, network2 = network_pair
    
    # Wait for connection to be established
    await asyncio.sleep(0.1)
    
    # Stop one network
    await network2.stop()
    
    # Wait for connection loss to be detected
    await asyncio.sleep(0.1)
    
    assert len(network1.connections) == 0

@pytest.mark.asyncio
async def test_reconnection(network_pair):
    """Test automatic reconnection after connection loss."""
    network1, network2 = network_pair
    
    # Wait for connection to be established
    await asyncio.sleep(0.1)
    
    # Stop and restart one network
    await network2.stop()
    await asyncio.sleep(0.1)
    await network2.start()
    
    # Reconnect
    await network1.connect(f"ws://localhost:{network2.config.port}")
    
    # Wait for reconnection
    await asyncio.sleep(0.1)
    
    assert len(network1.connections) == 1
    assert len(network2.connections) == 1

@pytest.mark.asyncio
async def test_invalid_connection(network_pair):
    """Test handling of invalid connection attempts."""
    network1, _ = network_pair
    
    # Try to connect to non-existent peer
    with pytest.raises(Exception):
        await network1.connect("ws://localhost:9999")

@pytest.mark.asyncio
async def test_message_encryption(network_pair):
    """Test that messages are properly encrypted."""
    network1, network2 = network_pair
    messages = []
    
    def on_message(conn, msg):
        messages.append(msg)
    
    network2.on_message = on_message
    
    # Wait for connection to be established
    await asyncio.sleep(0.1)
    
    # Send message
    await network1.send_message(network1.connections[0].remote_address, "encrypted message")
    
    # Wait for message to be received
    await asyncio.sleep(0.1)
    
    assert len(messages) == 1
    assert messages[0] == "encrypted message"

@pytest.mark.asyncio
async def test_multiple_connections(network_pair):
    """Test handling of multiple connections."""
    network1, network2 = network_pair
    
    # Create third network
    config3 = Config()
    config3.port = 8003
    config3.peer_discovery_port = 7003
    
    crypto3 = CryptoManager()
    network3 = P2PNetwork(config3, crypto3)
    
    await network3.start()
    
    # Connect to both networks
    await network3.connect(f"ws://localhost:{network1.config.port}")
    await network3.connect(f"ws://localhost:{network2.config.port}")
    
    # Wait for connections to be established
    await asyncio.sleep(0.1)
    
    assert len(network3.connections) == 2
    
    # Cleanup

@pytest.mark.asyncio
async def test_connection_error_handling(connection):
    """Тест обработки ошибок соединения"""
    with patch('websockets.connect', side_effect=ConnectionError("Test error")):
        await connection.connect()
        assert connection.connection_state == "disconnected"
        assert connection.error_count == 1

@pytest.mark.asyncio
async def test_connection_recovery(connection):
    """Тест восстановления соединения"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "handshake", "data": {}}))
    
    with patch('websockets.connect', side_effect=[ConnectionError("Test error"), mock_ws]):
        await connection.connect()
        assert connection.connection_state == "connected"
        assert connection.error_count == 0

@pytest.mark.asyncio
async def test_max_reconnect_attempts(connection):
    """Тест максимального количества попыток переподключения"""
    connection.max_reconnect_attempts = 2
    
    with patch('websockets.connect', side_effect=ConnectionError("Test error")):
        await connection.connect()
        await connection.connect()
        assert connection.reconnect_attempts == 2
        assert connection.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_message_error_handling(connection):
    """Тест обработки ошибок сообщений"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock(side_effect=Exception("Test error"))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        with pytest.raises(Exception):
            await connection.send_message("test", {"data": "test"})

@pytest.mark.asyncio
async def test_connection_state_transitions(connection):
    """Тест переходов состояний соединения"""
    assert connection.connection_state == "disconnected"
    
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "handshake", "data": {}}))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        assert connection.connection_state == "connected"
        
        await connection.stop()
        assert connection.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_connection_monitoring(connection):
    """Тест мониторинга соединения"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "handshake", "data": {}}))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        await connection.ping()
        assert connection.last_ping_time is not None

@pytest.mark.asyncio
async def test_ping_pong_error_handling(connection):
    """Тест обработки ошибок пинг-понг"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock(side_effect=Exception("Test error"))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        await connection.ping()
        assert connection.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_connection_cleanup(connection):
    """Тест очистки соединения"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.close = AsyncMock()
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        await connection.stop()
        mock_ws.close.assert_called_once()
    assert messages[0] == "encrypted message"

@pytest.mark.asyncio
async def test_multiple_connections(network_pair):
    """Test handling of multiple connections."""
    network1, network2 = network_pair
    
    # Create third network
    config3 = Config()
    config3.port = 8003
    config3.peer_discovery_port = 7003
    
    crypto3 = CryptoManager()
    network3 = P2PNetwork(config3, crypto3)
    
    await network3.start()
    
    # Connect to both networks
    await network3.connect(f"ws://localhost:{network1.config.port}")
    await network3.connect(f"ws://localhost:{network2.config.port}")
    
    # Wait for connections to be established
    await asyncio.sleep(0.1)
    
    assert len(network3.connections) == 2
    
    # Cleanup

@pytest.mark.asyncio
async def test_connection_error_handling(connection):
    """Тест обработки ошибок соединения"""
    with patch('websockets.connect', side_effect=ConnectionError("Test error")):
        await connection.connect()
        assert connection.connection_state == "disconnected"
        assert connection.error_count == 1

@pytest.mark.asyncio
async def test_connection_recovery(connection):
    """Тест восстановления соединения"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "handshake", "data": {}}))
    
    with patch('websockets.connect', side_effect=[ConnectionError("Test error"), mock_ws]):
        await connection.connect()
        assert connection.connection_state == "connected"
        assert connection.error_count == 0

@pytest.mark.asyncio
async def test_max_reconnect_attempts(connection):
    """Тест максимального количества попыток переподключения"""
    connection.max_reconnect_attempts = 2
    
    with patch('websockets.connect', side_effect=ConnectionError("Test error")):
        await connection.connect()
        await connection.connect()
        assert connection.reconnect_attempts == 2
        assert connection.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_message_error_handling(connection):
    """Тест обработки ошибок сообщений"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock(side_effect=Exception("Test error"))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        with pytest.raises(Exception):
            await connection.send_message("test", {"data": "test"})

@pytest.mark.asyncio
async def test_connection_state_transitions(connection):
    """Тест переходов состояний соединения"""
    assert connection.connection_state == "disconnected"
    
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "handshake", "data": {}}))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        assert connection.connection_state == "connected"
        
        await connection.stop()
        assert connection.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_connection_monitoring(connection):
    """Тест мониторинга соединения"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "handshake", "data": {}}))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        await connection.ping()
        assert connection.last_ping_time is not None

@pytest.mark.asyncio
async def test_ping_pong_error_handling(connection):
    """Тест обработки ошибок пинг-понг"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.send = AsyncMock(side_effect=Exception("Test error"))
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        await connection.ping()
        assert connection.connection_state == "disconnected"

@pytest.mark.asyncio
async def test_connection_cleanup(connection):
    """Тест очистки соединения"""
    mock_ws = AsyncMock(spec=WebSocketClientProtocol)
    mock_ws.close = AsyncMock()
    
    with patch('websockets.connect', return_value=mock_ws):
        await connection.connect()
        await connection.stop()
        mock_ws.close.assert_called_once()
    await network3.stop() 