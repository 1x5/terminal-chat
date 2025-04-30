import pytest
from datetime import datetime, timedelta
from src.reputation import ReputationManager, ReputationEvent, PeerStats

@pytest.fixture
def reputation_manager(tmp_path):
    """Фикстура для менеджера репутации"""
    config_path = tmp_path / "reputation.json"
    return ReputationManager(str(config_path))

def test_initial_reputation(reputation_manager):
    """Тест начальной репутации"""
    assert reputation_manager.get_reputation("test_peer") == 0.0
    assert not reputation_manager.is_trusted("test_peer")

def test_reputation_update(reputation_manager):
    """Тест обновления репутации"""
    peer_id = "test_peer"
    
    # Получение сообщения
    reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_RECEIVED)
    assert reputation_manager.get_reputation(peer_id) == 1.0
    
    # Отправка сообщения
    reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_SENT)
    assert reputation_manager.get_reputation(peer_id) == 3.0
    
    # Неверная подпись
    reputation_manager.update_reputation(peer_id, ReputationEvent.INVALID_SIGNATURE)
    assert reputation_manager.get_reputation(peer_id) == -2.0

def test_reputation_limits(reputation_manager):
    """Тест ограничений репутации"""
    peer_id = "test_peer"
    
    # Проверяем минимальную репутацию
    for _ in range(20):
        reputation_manager.update_reputation(peer_id, ReputationEvent.SYBIL_ATTACK)
    assert reputation_manager.get_reputation(peer_id) == -50.0
    
    # Проверяем максимальную репутацию
    for _ in range(100):
        reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_SENT)
    assert reputation_manager.get_reputation(peer_id) == 100.0

def test_reputation_decay(reputation_manager):
    """Тест уменьшения репутации со временем"""
    peer_id = "test_peer"
    
    # Устанавливаем высокую репутацию
    reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_SENT)
    reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_SENT)
    initial_reputation = reputation_manager.get_reputation(peer_id)
    
    # Симулируем прошедшие сутки
    stats = reputation_manager.get_peer_stats(peer_id)
    stats.last_seen = datetime.utcnow() - timedelta(hours=25)
    
    # Проверяем уменьшение репутации
    reputation_manager.decay_reputation()
    assert reputation_manager.get_reputation(peer_id) < initial_reputation

def test_peer_stats(reputation_manager):
    """Тест статистики пира"""
    peer_id = "test_peer"
    
    # Добавляем события
    reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_RECEIVED)
    reputation_manager.update_reputation(peer_id, ReputationEvent.MESSAGE_SENT)
    
    # Проверяем статистику
    stats = reputation_manager.get_peer_stats(peer_id)
    assert stats.messages_received == 1
    assert stats.messages_sent == 1
    assert len(stats.events) == 2

def test_top_peers(reputation_manager):
    """Тест получения топ пиров"""
    # Добавляем несколько пиров с разной репутацией
    reputation_manager.update_reputation("peer1", ReputationEvent.MESSAGE_SENT)
    reputation_manager.update_reputation("peer2", ReputationEvent.MESSAGE_SENT)
    reputation_manager.update_reputation("peer2", ReputationEvent.MESSAGE_SENT)
    reputation_manager.update_reputation("peer3", ReputationEvent.INVALID_SIGNATURE)
    
    # Получаем топ-2 пира
    top_peers = reputation_manager.get_top_peers(limit=2)
    assert len(top_peers) == 2
    assert top_peers[0][0] == "peer2"  # peer2 имеет наивысшую репутацию 