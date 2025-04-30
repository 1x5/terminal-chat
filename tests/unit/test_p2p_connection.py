"""
Тесты для модуля P2P соединений
"""

import pytest
import asyncio
from src.network import P2PConnection

@pytest.fixture
async def connection_pair():
    """Создает пару соединенных P2P соединений"""
    # Создаем первое соединение
    conn1 = P2PConnection("127.0.0.1", 8001)
    await conn1.start()
    
    # Создаем второе соединение
    conn2 = P2PConnection("127.0.0.1", 8002)
    await conn2.start()
    
    # Соединяем их
    await conn1.connect("127.0.0.1", 8002)
    
    yield conn1, conn2
    
    # Очистка
    await conn1.stop()
    await conn2.stop()

@pytest.mark.asyncio
async def test_connection_establishment(connection_pair):
    """Проверяет установление соединения"""
    conn1, conn2 = connection_pair
    
    assert conn1.is_connected()
    assert conn2.is_connected()
    assert conn1.remote_address == ("127.0.0.1", 8002)
    assert conn2.remote_address == ("127.0.0.1", 8001)

@pytest.mark.asyncio
async def test_message_exchange(connection_pair):
    """Проверяет обмен сообщениями"""
    conn1, conn2 = connection_pair
    
    # Отправляем сообщение
    message = "Тестовое сообщение"
    await conn1.send_message(message)
    
    # Получаем сообщение
    received = await conn2.receive_message()
    assert received == message

@pytest.mark.asyncio
async def test_connection_closure(connection_pair):
    """Проверяет закрытие соединения"""
    conn1, conn2 = connection_pair
    
    # Закрываем соединение
    await conn1.stop()
    
    assert not conn1.is_connected()
    assert not conn2.is_connected()

@pytest.mark.asyncio
async def test_reconnection():
    """Проверяет переподключение"""
    # Создаем соединение
    conn = P2PConnection("127.0.0.1", 8003)
    await conn.start()
    
    # Пытаемся подключиться к несуществующему узлу
    with pytest.raises(Exception):
        await conn.connect("127.0.0.1", 9999)
    
    # Проверяем, что соединение все еще активно
    assert conn.is_connected()
    
    await conn.stop()

@pytest.mark.asyncio
async def test_message_queue():
    """Проверяет очередь сообщений"""
    conn = P2PConnection("127.0.0.1", 8004)
    await conn.start()
    
    # Добавляем сообщения в очередь
    message1 = "Сообщение 1"
    message2 = "Сообщение 2"
    
    await conn.send_message(message1)
    await conn.send_message(message2)
    
    # Проверяем, что сообщения в очереди
    assert len(conn.message_queue) == 2
    
    await conn.stop() 