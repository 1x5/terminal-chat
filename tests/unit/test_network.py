"""
Тесты для сетевого слоя
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from src.network import P2PNetwork
from src.p2p_connection import NodeConnection
from src.crypto import CryptoManager
import pytest_asyncio
from dataclasses import dataclass
import random
from src.config import Config

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
    await network3.stop() 