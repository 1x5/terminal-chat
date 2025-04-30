import pytest
import asyncio
from unittest.mock import Mock, patch
from src.nat_traversal import NATTraversal, NATType
from src.config import Config

@pytest.fixture
async def nat_traversal():
    config = Config()
    nat = NATTraversal(config)
    await nat.init()
    yield nat
    await nat.cleanup()

@pytest.mark.asyncio
async def test_nat_detection(nat_traversal):
    """Тест определения типа NAT"""
    nat_type = await nat_traversal.detect_nat_type()
    assert nat_type in [t for t in NATType]
    assert nat_traversal.nat_type == nat_type

@pytest.mark.asyncio
async def test_upnp_setup(nat_traversal):
    """Тест настройки UPnP"""
    with patch('miniupnpc.UPnP') as mock_upnp:
        mock_instance = Mock()
        mock_upnp.return_value = mock_instance
        
        await nat_traversal.setup_upnp()
        
        assert mock_instance.discover.called
        assert mock_instance.selectigd.called
        assert mock_instance.addportmapping.called

@pytest.mark.asyncio
async def test_ice_connection():
    """Тест ICE соединения между двумя пирами"""
    # Создаем два экземпляра NAT traversal
    config1 = Config()
    config2 = Config()
    
    nat1 = NATTraversal(config1)
    nat2 = NATTraversal(config2)
    
    try:
        # Инициализируем оба экземпляра
        await nat1.init()
        await nat2.init()
        
        # Получаем кандидатов от обоих пиров
        peer1_candidates = nat1.ice_agent["candidates"]
        peer2_candidates = nat2.ice_agent["candidates"]
        
        # Пробуем установить соединение
        success = await nat1.connect_to_peer("peer2", peer2_candidates)
        assert success, "Не удалось установить соединение"
        
    finally:
        await nat1.cleanup()
        await nat2.cleanup()

@pytest.mark.asyncio
async def test_connection_loss_handling(nat_traversal):
    """Тест обработки потери соединения"""
    # Создаем мок-соединение
    peer_id = "test_peer"
    nat_traversal.connections[peer_id] = {
        "socket": Mock(),
        "remote_ip": "127.0.0.1",
        "remote_port": 12345,
        "candidates": []
    }
    
    # Симулируем потерю соединения
    with patch.object(nat_traversal, '_check_connection', return_value=False):
        with patch.object(nat_traversal, 'connect_to_peer', return_value=True):
            # Запускаем обработку потери соединения
            result = await nat_traversal._handle_connection_loss(peer_id)
            assert result, "Переподключение не удалось"

@pytest.mark.asyncio
async def test_turn_candidates():
    """Тест получения TURN кандидатов"""
    config = Config()
    config.turn_servers = [{
        "url": "turn:test.com:3478",
        "username": "test",
        "password": "test123"
    }]
    
    nat = NATTraversal(config)
    
    with patch('aiohttp.ClientSession') as mock_session:
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = Mock(return_value={"ip": "1.2.3.4", "port": 3478})
        
        mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
        
        candidates = await nat._gather_turn_candidates()
        assert len(candidates) == 1
        assert candidates[0]["type"] == "relay"
        assert candidates[0]["ip"] == "1.2.3.4" 