"""
Тесты для модуля P2P сети
"""

import pytest
import asyncio
from src.network import P2PNetwork

@pytest.fixture
async def p2p_network():
    """Создает сеть для тестирования P2P соединений"""
    # Создаем три узла P2P сети
    n1 = P2PNetwork("127.0.0.1", 9001)
    n2 = P2PNetwork("127.0.0.1", 9002)
    n3 = P2PNetwork("127.0.0.1", 9003)
    
    # Запускаем узлы
    await n1.start()
    await n2.start()
    await n3.start()
    
    yield n1, n2, n3
    
    # Очистка
    await n1.stop()
    await n2.stop()
    await n3.stop()

@pytest.mark.asyncio
async def test_peer_connection(p2p_network):
    """Проверяет установку соединения между пирами"""
    n1, n2, _ = p2p_network
    
    # Устанавливаем соединение
    await n1.connect_to_peer("127.0.0.1", 9002)
    
    # Проверяем, что соединение установлено
    assert n1.is_connected_to("127.0.0.1", 9002)
    assert n2.is_connected_to("127.0.0.1", 9001)

@pytest.mark.asyncio
async def test_message_exchange(p2p_network):
    """Проверяет обмен сообщениями между пирами"""
    n1, n2, _ = p2p_network
    
    # Устанавливаем соединение
    await n1.connect_to_peer("127.0.0.1", 9002)
    
    # Отправляем сообщение
    message = "Test message"
    await n1.send_message("127.0.0.1", 9002, message)
    
    # Проверяем получение сообщения
    received = await n2.receive_message()
    assert received == message

@pytest.mark.asyncio
async def test_peer_disconnection(p2p_network):
    """Проверяет разрыв соединения между пирами"""
    n1, n2, _ = p2p_network
    
    # Устанавливаем соединение
    await n1.connect_to_peer("127.0.0.1", 9002)
    
    # Разрываем соединение
    await n1.disconnect_from_peer("127.0.0.1", 9002)
    
    # Проверяем, что соединение разорвано
    assert not n1.is_connected_to("127.0.0.1", 9002)
    assert not n2.is_connected_to("127.0.0.1", 9001)

@pytest.mark.asyncio
async def test_connection_error():
    """Проверяет обработку ошибок соединения"""
    n = P2PNetwork("127.0.0.1", 9001)
    await n.start()
    
    # Пытаемся подключиться к несуществующему пиру
    with pytest.raises(Exception):
        await n.connect_to_peer("invalid", 9002)
    
    await n.stop()

@pytest.mark.asyncio
async def test_multiple_connections(p2p_network):
    """Проверяет работу с несколькими соединениями"""
    n1, n2, n3 = p2p_network
    
    # Устанавливаем соединения
    await n1.connect_to_peer("127.0.0.1", 9002)
    await n1.connect_to_peer("127.0.0.1", 9003)
    
    # Отправляем сообщения разным пирам
    await n1.send_message("127.0.0.1", 9002, "Message 1")
    await n1.send_message("127.0.0.1", 9003, "Message 2")
    
    # Проверяем получение сообщений
    received1 = await n2.receive_message()
    received2 = await n3.receive_message()
    
    assert received1 == "Message 1"
    assert received2 == "Message 2" 