import pytest
import asyncio
import time
import socket
import struct
import json
from unittest.mock import Mock, patch
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
        public_key="2" * 64,
        last_seen=time.time(),
        services={"chat"},
        latency=0.1,
        success_rate=1.0,
        reputation=1.0
    )

@pytest.mark.asyncio
async def test_peer_discovery_start_stop(discovery):
    await discovery.start()
    assert discovery.running
    assert discovery.session is not None
    
    await discovery.stop()
    assert not discovery.running
    assert discovery.session is None

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
    
    # Test reputation filtering
    low_rep_peer = PeerInfo(
        node_id="3" * 40,
        address="127.0.0.1",
        port=8002,
        public_key="4" * 64,
        last_seen=time.time(),
        services={"chat"},
        reputation=0.3
    )
    discovery.add_peer(low_rep_peer)
    
    high_rep_peers = discovery.get_peers(min_reputation=0.5)
    assert len(high_rep_peers) == 1
    assert high_rep_peers[0].node_id == sample_peer.node_id

@pytest.mark.asyncio
async def test_network_health_check(discovery, sample_peer):
    await discovery.start()
    discovery.add_peer(sample_peer)
    
    # Test with low number of active peers
    discovery.active_peers.clear()
    await discovery._check_network_health()
    assert len(discovery.active_peers) > 0
    
    # Test error count reset
    discovery.error_counts["test_peer"] = 5
    discovery.last_discovery_time["test_peer"] = time.time() - 3601
    await discovery._check_network_health()
    assert discovery.error_counts["test_peer"] == 0
    
    await discovery.stop()

@pytest.mark.asyncio
async def test_peer_reconnection(discovery, sample_peer):
    await discovery.start()
    discovery.add_peer(sample_peer)
    sample_peer.reputation = 0.2
    
    with patch.object(discovery, '_bootstrap_node') as mock_bootstrap:
        await discovery._reconnect_peer(sample_peer)
        assert sample_peer.connection_attempts == 1
        mock_bootstrap.assert_called_once()
        
        # Test max attempts
        sample_peer.connection_attempts = 3
        await discovery._reconnect_peer(sample_peer)
        assert sample_peer.connection_attempts == 3
        assert mock_bootstrap.call_count == 1
    
    await discovery.stop()

@pytest.mark.asyncio
async def test_peer_discovery_with_http(discovery):
    await discovery.start()
    
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "peers": [{
            "node_id": "1" * 40,
            "address": "127.0.0.1",
            "port": 8001,
            "public_key": "2" * 64,
            "services": ["chat"],
            "latency": 0.1,
            "success_rate": 1.0,
            "reputation": 1.0
        }]
    }
    
    with patch.object(discovery.session, 'get', return_value=mock_response):
        peer = PeerInfo(
            node_id="3" * 40,
            address="127.0.0.1",
            port=8002,
            public_key="4" * 64,
            last_seen=time.time(),
            services={"chat"}
        )
        await discovery._discover_from_peer(peer)
        
        assert len(discovery.known_peers) == 1
        assert peer.success_rate > 0.9
        assert peer.reputation > 0.9
    
    await discovery.stop()

@pytest.mark.asyncio
async def test_peer_validation(discovery):
    # Test valid peer
    valid_peer = PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert discovery._validate_peer(valid_peer)
    
    # Test invalid node_id
    invalid_peer = PeerInfo(
        node_id="1" * 39,  # Too short
        address="127.0.0.1",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert not discovery._validate_peer(invalid_peer)
    
    # Test invalid address
    invalid_peer = PeerInfo(
        node_id="1" * 40,
        address="invalid",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert not discovery._validate_peer(invalid_peer)
    
    # Test invalid port
    invalid_peer = PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=70000,  # Too high
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert not discovery._validate_peer(invalid_peer)

@pytest.mark.asyncio
async def test_network_stats(discovery):
    # Add peers with different reputations
    high_rep_peer = PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time(),
        reputation=0.9
    )
    medium_rep_peer = PeerInfo(
        node_id="3" * 40,
        address="127.0.0.1",
        port=8002,
        public_key="4" * 64,
        last_seen=time.time(),
        reputation=0.6
    )
    low_rep_peer = PeerInfo(
        node_id="5" * 40,
        address="127.0.0.1",
        port=8003,
        public_key="6" * 64,
        last_seen=time.time(),
        reputation=0.3
    )
    
    discovery.add_peer(high_rep_peer)
    discovery.add_peer(medium_rep_peer)
    discovery.add_peer(low_rep_peer)
    
    stats = discovery.get_network_stats()
    assert stats["total_peers"] == 3
    assert stats["reputation_stats"]["high"] == 1
    assert stats["reputation_stats"]["medium"] == 1
    assert stats["reputation_stats"]["low"] == 1 
import asyncio
import time
import socket
import struct
import json
from unittest.mock import Mock, patch
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
        public_key="2" * 64,
        last_seen=time.time(),
        services={"chat"},
        latency=0.1,
        success_rate=1.0,
        reputation=1.0
    )

@pytest.mark.asyncio
async def test_peer_discovery_start_stop(discovery):
    await discovery.start()
    assert discovery.running
    assert discovery.session is not None
    
    await discovery.stop()
    assert not discovery.running
    assert discovery.session is None

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
    
    # Test reputation filtering
    low_rep_peer = PeerInfo(
        node_id="3" * 40,
        address="127.0.0.1",
        port=8002,
        public_key="4" * 64,
        last_seen=time.time(),
        services={"chat"},
        reputation=0.3
    )
    discovery.add_peer(low_rep_peer)
    
    high_rep_peers = discovery.get_peers(min_reputation=0.5)
    assert len(high_rep_peers) == 1
    assert high_rep_peers[0].node_id == sample_peer.node_id

@pytest.mark.asyncio
async def test_network_health_check(discovery, sample_peer):
    await discovery.start()
    discovery.add_peer(sample_peer)
    
    # Test with low number of active peers
    discovery.active_peers.clear()
    await discovery._check_network_health()
    assert len(discovery.active_peers) > 0
    
    # Test error count reset
    discovery.error_counts["test_peer"] = 5
    discovery.last_discovery_time["test_peer"] = time.time() - 3601
    await discovery._check_network_health()
    assert discovery.error_counts["test_peer"] == 0
    
    await discovery.stop()

@pytest.mark.asyncio
async def test_peer_reconnection(discovery, sample_peer):
    await discovery.start()
    discovery.add_peer(sample_peer)
    sample_peer.reputation = 0.2
    
    with patch.object(discovery, '_bootstrap_node') as mock_bootstrap:
        await discovery._reconnect_peer(sample_peer)
        assert sample_peer.connection_attempts == 1
        mock_bootstrap.assert_called_once()
        
        # Test max attempts
        sample_peer.connection_attempts = 3
        await discovery._reconnect_peer(sample_peer)
        assert sample_peer.connection_attempts == 3
        assert mock_bootstrap.call_count == 1
    
    await discovery.stop()

@pytest.mark.asyncio
async def test_peer_discovery_with_http(discovery):
    await discovery.start()
    
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "peers": [{
            "node_id": "1" * 40,
            "address": "127.0.0.1",
            "port": 8001,
            "public_key": "2" * 64,
            "services": ["chat"],
            "latency": 0.1,
            "success_rate": 1.0,
            "reputation": 1.0
        }]
    }
    
    with patch.object(discovery.session, 'get', return_value=mock_response):
        peer = PeerInfo(
            node_id="3" * 40,
            address="127.0.0.1",
            port=8002,
            public_key="4" * 64,
            last_seen=time.time(),
            services={"chat"}
        )
        await discovery._discover_from_peer(peer)
        
        assert len(discovery.known_peers) == 1
        assert peer.success_rate > 0.9
        assert peer.reputation > 0.9
    
    await discovery.stop()

@pytest.mark.asyncio
async def test_peer_validation(discovery):
    # Test valid peer
    valid_peer = PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert discovery._validate_peer(valid_peer)
    
    # Test invalid node_id
    invalid_peer = PeerInfo(
        node_id="1" * 39,  # Too short
        address="127.0.0.1",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert not discovery._validate_peer(invalid_peer)
    
    # Test invalid address
    invalid_peer = PeerInfo(
        node_id="1" * 40,
        address="invalid",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert not discovery._validate_peer(invalid_peer)
    
    # Test invalid port
    invalid_peer = PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=70000,  # Too high
        public_key="2" * 64,
        last_seen=time.time()
    )
    assert not discovery._validate_peer(invalid_peer)

@pytest.mark.asyncio
async def test_network_stats(discovery):
    # Add peers with different reputations
    high_rep_peer = PeerInfo(
        node_id="1" * 40,
        address="127.0.0.1",
        port=8001,
        public_key="2" * 64,
        last_seen=time.time(),
        reputation=0.9
    )
    medium_rep_peer = PeerInfo(
        node_id="3" * 40,
        address="127.0.0.1",
        port=8002,
        public_key="4" * 64,
        last_seen=time.time(),
        reputation=0.6
    )
    low_rep_peer = PeerInfo(
        node_id="5" * 40,
        address="127.0.0.1",
        port=8003,
        public_key="6" * 64,
        last_seen=time.time(),
        reputation=0.3
    )
    
    discovery.add_peer(high_rep_peer)
    discovery.add_peer(medium_rep_peer)
    discovery.add_peer(low_rep_peer)
    
    stats = discovery.get_network_stats()
    assert stats["total_peers"] == 3
    assert stats["reputation_stats"]["high"] == 1
    assert stats["reputation_stats"]["medium"] == 1
    assert stats["reputation_stats"]["low"] == 1 