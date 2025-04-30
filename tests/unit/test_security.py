"""
Тесты для модуля безопасности
"""
import pytest
import pytest_asyncio
import asyncio
import time
from src.security import SecurityManager, SecurityConfig
from src.crypto import CryptoManager
import hashlib
from src.config import Config

@pytest_asyncio.fixture
async def security_manager():
    """Создает тестовый менеджер безопасности"""
    crypto = CryptoManager()
    config = SecurityConfig(
        max_connections_per_ip=2,
        connection_timeout=1,
        max_message_size=1024,
        rate_limit_window=1,
        max_messages_per_window=3,
        challenge_timeout=1,
        min_reputation=0.5,
        reputation_decay=0.1,
        sybil_threshold=3
    )
    manager = SecurityManager(crypto, config)
    await manager.init()
    yield manager
    await manager.cleanup()

@pytest.fixture
def config():
    """Создает тестовую конфигурацию"""
    return SecurityConfig(
        max_connections_per_ip=2,
        connection_timeout=1,
        max_message_size=1024,
        rate_limit_window=1,
        max_messages_per_window=3,
        challenge_timeout=1,
        min_reputation=0.5,
        reputation_decay=0.1,
        sybil_threshold=3
    )

@pytest_asyncio.fixture
async def security(config):
    """Создает тестовый менеджер безопасности"""
    crypto = CryptoManager()
    manager = SecurityManager(crypto, config)
    await manager.init()
    yield manager
    await manager.cleanup()

@pytest.mark.asyncio
async def test_node_authentication(security_manager):
    """Тест аутентификации узла"""
    # Генерируем вызов
    challenge = await security_manager.generate_challenge("test_node")
    assert challenge is not None
    
    # Проверяем, что узел не аутентифицирован
    assert not await security_manager.is_node_authenticated("test_node")
    
    # Генерируем правильный ответ
    response = hashlib.sha256(challenge.encode()).hexdigest()
    
    # Проверяем ответ
    assert await security_manager.verify_challenge("test_node", response)
    
    # Проверяем, что узел аутентифицирован
    assert await security_manager.is_node_authenticated("test_node")
    
    # Проверяем таймаут аутентификации
    await asyncio.sleep(1.1)
    assert not await security_manager.is_node_authenticated("test_node")

@pytest.mark.asyncio
async def test_connection_limits(security_manager):
    """Тест ограничений подключений"""
    # Проверяем лимит подключений
    assert await security_manager.check_connection_limit("127.0.0.1")
    assert await security_manager.check_connection_limit("127.0.0.1")
    assert not await security_manager.check_connection_limit("127.0.0.1")  # Третье подключение должно быть отклонено
    
    # Ждем таймаут
    await asyncio.sleep(1.1)
    await security_manager.cleanup()  # Очищаем устаревшие подключения
    
    # Проверяем, что можно подключиться снова
    assert await security_manager.check_connection_limit("127.0.0.1")

@pytest.mark.asyncio
async def test_rate_limiting(security_manager):
    """Тест ограничения частоты сообщений"""
    # Проверяем лимит сообщений
    assert await security_manager.check_rate_limit("127.0.0.1")
    assert await security_manager.check_rate_limit("127.0.0.1")
    assert await security_manager.check_rate_limit("127.0.0.1")
    assert not await security_manager.check_rate_limit("127.0.0.1")
    
    # Ждем новый временной интервал
    await asyncio.sleep(1.1)
    assert await security_manager.check_rate_limit("127.0.0.1")

@pytest.mark.asyncio
async def test_message_validation(security_manager):
    """Тест валидации сообщений"""
    # Проверяем сообщение нормального размера
    assert await security_manager.validate_message(b"test" * 100)
    
    # Проверяем сообщение превышающее лимит
    assert not await security_manager.validate_message(b"test" * 1000)

@pytest.mark.asyncio
async def test_challenge_timeout(security_manager):
    """Тест таймаута вызова"""
    # Генерируем вызов
    challenge = await security_manager.generate_challenge("test_node")
    
    # Ждем таймаут
    await asyncio.sleep(1.1)
    
    # Проверяем, что вызов больше не действителен
    response = hashlib.sha256(challenge.encode()).hexdigest()
    assert not await security_manager.verify_challenge("test_node", response)

@pytest.mark.asyncio
async def test_cleanup(security_manager):
    """Тест очистки устаревших данных"""
    # Создаем тестовые данные
    await security_manager.generate_challenge("test_node1")
    await security_manager.generate_challenge("test_node2")
    await security_manager.check_connection_limit("127.0.0.1")
    await security_manager.check_rate_limit("127.0.0.1")
    
    # Ждем таймаут
    await asyncio.sleep(1.1)
    
    # Очищаем данные
    await security_manager.cleanup()
    
    # Проверяем, что данные очищены
    assert not await security_manager.is_node_authenticated("test_node1")
    assert not await security_manager.is_node_authenticated("test_node2")

@pytest.mark.asyncio
async def test_sybil_protection(security_manager):
    """Тест защиты от Sybil-атак"""
    # Симулируем несколько подключений с одного IP
    ip = "127.0.0.1"
    
    # Первые подключения должны пройти
    assert await security_manager.check_connection_limit(ip)
    assert await security_manager.check_connection_limit(ip)
    
    # Третье подключение должно быть отклонено
    assert not await security_manager.check_connection_limit(ip)
    
    # Проверяем, что узел помечен как потенциальный Sybil
    assert security_manager.is_sybil_node(ip)
    
    # Ждем таймаут
    await asyncio.sleep(1.1)
    
    # Проверяем, что узел больше не помечен как Sybil
    assert not security_manager.is_sybil_node(ip)

@pytest.mark.asyncio
async def test_node_reputation(security_manager):
    """Тест механизма репутации узлов"""
    node_id = "test_node"
    
    # Начальная репутация должна быть 1.0
    assert security_manager.get_node_reputation(node_id) == 1.0
    
    # Симулируем успешные действия
    await security_manager.update_reputation(node_id, True)
    assert security_manager.get_node_reputation(node_id) == 1.0  # Не должна превышать 1.0
    
    # Симулируем неудачные действия
    await security_manager.update_reputation(node_id, False)
    assert security_manager.get_node_reputation(node_id) < 1.0
    
    # Проверяем, что репутация не может упасть ниже минимума
    await security_manager.update_reputation(node_id, False)
    await security_manager.update_reputation(node_id, False)
    await security_manager.update_reputation(node_id, False)
    assert security_manager.get_node_reputation(node_id) >= security_manager.config.min_reputation

@pytest.mark.asyncio
async def test_reputation_decay(security_manager):
    """Тест затухания репутации со временем"""
    node_id = "test_node"
    
    # Устанавливаем высокую репутацию
    await security_manager.update_reputation(node_id, True)
    initial_reputation = security_manager.get_node_reputation(node_id)
    
    # Ждем и проверяем затухание
    await asyncio.sleep(1.1)
    await security_manager.cleanup()
    
    # Репутация должна уменьшиться
    assert security_manager.get_node_reputation(node_id) < initial_reputation

@pytest.mark.asyncio
async def test_blocked_nodes(security_manager):
    """Тест блокировки узлов"""
    node_id = "127.0.0.1"
    
    # Блокируем узел
    await security_manager.block_node(node_id)
    assert security_manager.is_node_blocked(node_id)
    
    # Проверяем, что заблокированный узел не может подключиться
    assert not await security_manager.check_connection_limit(node_id)
    
    # Разблокируем узел
    await security_manager.unblock_node(node_id)
    assert not security_manager.is_node_blocked(node_id)
    
    # Проверяем, что узел может подключиться
    assert await security_manager.check_connection_limit(node_id)

@pytest.mark.asyncio
async def test_sybil_detection(security):
    """Test detection of potential Sybil nodes"""
    node_id = "127.0.0.1"
    
    # Initial check should pass
    assert await security.check_sybil_attack(node_id)
    
    # Create multiple connections to trigger Sybil detection
    for _ in range(security.config.sybil_threshold + 1):
        await security.check_connection_limit(node_id)
    
    # Node should be marked as Sybil
    assert not await security.check_sybil_attack(node_id)
    
    # Wait for timeout
    await asyncio.sleep(1.1)
    
    # Node should be allowed again
    assert await security.check_sybil_attack(node_id)

@pytest.mark.asyncio
async def test_reputation_system(security):
    """Test reputation scoring system"""
    node_id = "127.0.0.1"
    
    # Initial reputation
    assert await security.check_sybil_attack(node_id)
    
    # Bad behavior reduces reputation
    for _ in range(5):
        await security.update_reputation(node_id, False)
    
    # Node should be blocked due to low reputation
    assert not await security.check_sybil_attack(node_id)
    
    # Good behavior increases reputation
    for _ in range(10):
        await security.update_reputation(node_id, True)
    
    # Node should be allowed again
    assert await security.check_sybil_attack(node_id)

@pytest.mark.asyncio
async def test_sybil_window(security):
    """Test Sybil detection window"""
    node_id = "127.0.0.1"
    
    # Initial check should pass
    assert await security.check_sybil_attack(node_id)
    
    # Create multiple connections
    for _ in range(security.config.sybil_threshold + 1):
        await security.check_connection_limit(node_id)
    
    # Node should be marked as Sybil
    assert not await security.check_sybil_attack(node_id)
    
    # Wait for timeout
    await asyncio.sleep(1.1)
    
    # Node should be allowed again
    assert await security.check_sybil_attack(node_id)

@pytest.mark.asyncio
async def test_connection_limit(security):
    """Test connection limit enforcement"""
    node_id = "127.0.0.1"
    
    # Try to connect up to the limit
    for _ in range(security.config.max_connections_per_ip):
        assert await security.check_connection_limit(node_id)
        
    # Next connection should be rejected
    assert not await security.check_connection_limit(node_id)
    
    # Wait for timeout
    await asyncio.sleep(1.1)
    
    # Should be able to connect again
    assert await security.check_connection_limit(node_id) 