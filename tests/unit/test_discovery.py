import pytest
import asyncio
import time
import socket
import struct
from src.discovery import PeerDiscovery, PeerInfo

@pytest.fixture
def discovery():
    return PeerDiscovery(
        node_id="0" * 40,
        port=8000,
        bootstrap_nodes=[("127.0.0.1", 8001)]
    )

@pytest.fixture
def sample_peer():
    return PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=8001,
        public_key="test_key",
        last_seen=time.time(),
        services={"chat", "storage"}
    )

@pytest.mark.asyncio
async def test_start_stop(discovery):
    # Test starting the service
    await discovery.start()
    assert discovery.running is True
    assert discovery.discovery_task is not None
    
    # Test stopping the service
    await discovery.stop()
    assert discovery.running is False
    assert discovery.discovery_task is None

@pytest.mark.asyncio
async def test_add_remove_peer(discovery, sample_peer):
    # Test adding a peer
    result = discovery.add_peer(sample_peer)
    assert result is True
    assert sample_peer.node_id in discovery.known_peers
    assert sample_peer.node_id in discovery.active_peers
    
    # Test removing a peer
    result = discovery.remove_peer(sample_peer.node_id)
    assert result is True
    assert sample_peer.node_id not in discovery.known_peers
    assert sample_peer.node_id not in discovery.active_peers
    
    # Test removing non-existent peer
    result = discovery.remove_peer("non_existent")
    assert result is False

@pytest.mark.asyncio
async def test_get_peers(discovery, sample_peer):
    # Add a peer
    discovery.add_peer(sample_peer)
    
    # Test getting all peers
    peers = discovery.get_peers()
    assert len(peers) == 1
    assert peers[0].node_id == sample_peer.node_id
    
    # Test getting peers by service
    chat_peers = discovery.get_peers(service="chat")
    assert len(chat_peers) == 1
    assert chat_peers[0].node_id == sample_peer.node_id
    
    # Test getting peers for non-existent service
    relay_peers = discovery.get_peers(service="relay")
    assert len(relay_peers) == 0

@pytest.mark.asyncio
async def test_cleanup_peers(discovery, sample_peer, monkeypatch):
    # Add a peer with old timestamp
    sample_peer.last_seen = time.time() - 7200  # 2 hours ago
    discovery.add_peer(sample_peer)
    
    # Run cleanup
    await discovery._cleanup_peers()
    
    # Verify peer is removed
    assert sample_peer.node_id not in discovery.known_peers
    assert sample_peer.node_id not in discovery.active_peers

@pytest.mark.asyncio
async def test_process_peer_response(discovery):
    # Create test response data
    node_id = "1" * 40
    public_key = "2" * 64
    services = 0x03  # chat + storage
    port = 8001
    
    # Pack data
    data = (
        bytes.fromhex(node_id) +
        bytes.fromhex(public_key) +
        struct.pack("!I", services) +
        struct.pack("!H", port)
    )
    
    # Process response
    discovery._process_peer_response(data, ("127.0.0.1", 8001))
    
    # Verify peer was added
    assert node_id in discovery.known_peers
    peer = discovery.known_peers[node_id]
    assert peer.address == "127.0.0.1"
    assert peer.port == port
    assert peer.public_key == public_key
    assert "chat" in peer.services
    assert "storage" in peer.services
    assert "relay" not in peer.services

@pytest.mark.asyncio
async def test_bootstrap(discovery, monkeypatch):
    # Mock socket operations
    class MockSocket:
        def __init__(self, *args, **kwargs):
            pass
            
        def settimeout(self, timeout):
            pass
            
        def sendto(self, data, addr):
            pass
            
        def recvfrom(self, size):
            # Return mock response
            node_id = "1" * 40
            public_key = "2" * 64
            services = 0x01  # chat only
            port = 8001
            
            data = (
                bytes.fromhex(node_id) +
                bytes.fromhex(public_key) +
                struct.pack("!I", services) +
                struct.pack("!H", port)
            )
            return data, ("127.0.0.1", 8001)
            
        def close(self):
            pass
            
    monkeypatch.setattr(socket, "socket", MockSocket)
    
    # Run bootstrap
    await discovery._bootstrap()
    
    # Verify peer was added
    assert len(discovery.known_peers) == 1
    peer = list(discovery.known_peers.values())[0]
    assert peer.node_id == "1" * 40
    assert "chat" in peer.services
    assert "storage" not in peer.services 