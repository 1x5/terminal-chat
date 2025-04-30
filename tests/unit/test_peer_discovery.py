"""
Тесты для модуля обнаружения пиров
"""

import pytest
import asyncio
from src.peer_discovery import PeerDiscovery

@pytest.fixture
async def discovery_network():
    """Создает сеть для тестирования обнаружения пиров"""
    # Создаем три узла обнаружения
    d1 = PeerDiscovery("127.0.0.1", 7001)
    d2 = PeerDiscovery("127.0.0.1", 7002)
    d3 = PeerDiscovery("127.0.0.1", 7003)
    
    # Запускаем узлы
    await d1.start()
    await d2.start()
    await d3.start()
    
    yield d1, d2, d3
    
    # Очистка
    await d1.stop()
    await d2.stop()
    await d3.stop()

@pytest.mark.asyncio
async def test_peer_announcement(discovery_network):
    """Проверяет анонс пиров"""
    d1, d2, _ = discovery_network
    
    # Анонсируем пир
    await d1.announce_peer("127.0.0.1", 7001)
    
    # Проверяем, что пир обнаружен
    peers = await d2.get_peers()
    assert ("127.0.0.1", 7001) in peers

@pytest.mark.asyncio
async def test_peer_discovery(discovery_network):
    """Проверяет обнаружение пиров"""
    d1, d2, d3 = discovery_network
    
    # Анонсируем пиры
    await d1.announce_peer("127.0.0.1", 7001)
    await d2.announce_peer("127.0.0.1", 7002)
    await d3.announce_peer("127.0.0.1", 7003)
    
    # Проверяем, что все пиры обнаружены
    peers = await d1.get_peers()
    assert len(peers) == 2
    assert ("127.0.0.1", 7002) in peers
    assert ("127.0.0.1", 7003) in peers

@pytest.mark.asyncio
async def test_peer_removal(discovery_network):
    """Проверяет удаление пиров"""
    d1, d2, _ = discovery_network
    
    # Анонсируем пир
    await d1.announce_peer("127.0.0.1", 7001)
    
    # Удаляем пир
    await d1.remove_peer("127.0.0.1", 7001)
    
    # Проверяем, что пир удален
    peers = await d2.get_peers()
    assert ("127.0.0.1", 7001) not in peers

@pytest.mark.asyncio
async def test_discovery_error():
    """Проверяет обработку ошибок обнаружения"""
    d = PeerDiscovery("127.0.0.1", 7001)
    await d.start()
    
    # Пытаемся анонсировать неверный адрес
    with pytest.raises(Exception):
        await d.announce_peer("invalid", 7002)
    
    await d.stop()

@pytest.mark.asyncio
async def test_peer_refresh(discovery_network):
    """Проверяет обновление списка пиров"""
    d1, d2, d3 = discovery_network
    
    # Анонсируем пиры
    await d1.announce_peer("127.0.0.1", 7001)
    await d2.announce_peer("127.0.0.1", 7002)
    
    # Проверяем начальное состояние
    peers = await d3.get_peers()
    assert len(peers) == 2
    
    # Удаляем один пир
    await d1.remove_peer("127.0.0.1", 7001)
    
    # Обновляем список пиров
    await d3.refresh_peers()
    
    # Проверяем обновленное состояние
    peers = await d3.get_peers()
    assert len(peers) == 1
    assert ("127.0.0.1", 7002) in peers 