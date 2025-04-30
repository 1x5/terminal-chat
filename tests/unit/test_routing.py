"""
Тесты для маршрутизации сообщений
"""

import pytest
import pytest_asyncio
import asyncio
import time
from src.routing import MessageRouter
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest_asyncio.fixture
async def router(config, crypto):
    router = MessageRouter(config, crypto)
    await router.start()
    try:
        yield router
    finally:
        await router.stop()

@pytest.mark.asyncio
async def test_route_message(router):
    """Тест маршрутизации сообщения"""
    source = "node1"
    target = "node2"
    message = {"type": "test", "data": "test_data"}
    
    # Маршрутизируем сообщение
    success = await router.route_message(source, target, message)
    assert success
    
    # Проверяем что сообщение доставлено
    received = await router.get_message(target)
    assert received is not None
    assert received["source"] == source
    assert received["type"] == message["type"]
    assert received["data"] == message["data"]

@pytest.mark.asyncio
async def test_broadcast_message(router):
    """Тест широковещательной рассылки"""
    source = "node1"
    targets = ["node2", "node3", "node4"]
    message = {"type": "broadcast", "data": "test_data"}
    
    # Рассылаем сообщение
    success = await router.broadcast_message(source, targets, message)
    assert success
    
    # Проверяем что сообщение доставлено всем получателям
    for target in targets:
        received = await router.get_message(target)
        assert received is not None
        assert received["source"] == source
        assert received["type"] == message["type"]
        assert received["data"] == message["data"]

@pytest.mark.asyncio
async def test_multicast_message(router):
    """Тест групповой рассылки"""
    source = "node1"
    groups = ["group1", "group2"]
    message = {"type": "multicast", "data": "test_data"}
    
    # Добавляем узлы в группы
    await router.add_to_group("node2", "group1")
    await router.add_to_group("node3", "group1")
    await router.add_to_group("node4", "group2")
    
    # Рассылаем сообщение группам
    success = await router.multicast_message(source, groups, message)
    assert success
    
    # Проверяем что сообщение доставлено узлам в группах
    group1_nodes = ["node2", "node3"]
    group2_nodes = ["node4"]
    
    for node in group1_nodes + group2_nodes:
        received = await router.get_message(node)
        assert received is not None
        assert received["source"] == source
        assert received["type"] == message["type"]
        assert received["data"] == message["data"]

@pytest.mark.asyncio
async def test_message_priority(router):
    """Тест приоритетов сообщений"""
    source = "node1"
    target = "node2"
    high_priority = {"type": "high", "data": "high_priority", "priority": 1}
    low_priority = {"type": "low", "data": "low_priority", "priority": 0}
    
    # Отправляем сообщения
    await router.route_message(source, target, low_priority)
    await router.route_message(source, target, high_priority)
    
    # Проверяем что высокоприоритетное сообщение обработано первым
    received = await router.get_message(target)
    assert received is not None
    assert received["type"] == "high"
    assert received["data"] == "high_priority"

@pytest.mark.asyncio
async def test_message_ttl(router):
    """Тест времени жизни сообщения"""
    source = "node1"
    target = "node2"
    message = {"type": "test", "data": "test_data", "ttl": 1}
    
    # Отправляем сообщение
    await router.route_message(source, target, message)
    
    # Ждем истечения TTL
    await asyncio.sleep(2)
    
    # Проверяем что сообщение удалено
    received = await router.get_message(target)
    assert received is None

@pytest.mark.asyncio
async def test_message_retry(router):
    """Тест повторной отправки сообщения"""
    source = "node1"
    target = "node2"
    message = {"type": "test", "data": "test_data", "retry": 3}
    
    # Отправляем сообщение
    success = await router.route_message(source, target, message)
    assert success
    
    # Проверяем что сообщение отправлено указанное количество раз
    retries = await router.get_retry_count(target)
    assert retries == 3

@pytest.mark.asyncio
async def test_message_ack(router):
    """Тест подтверждения доставки"""
    source = "node1"
    target = "node2"
    message = {"type": "test", "data": "test_data", "require_ack": True}
    
    # Отправляем сообщение
    success = await router.route_message(source, target, message)
    assert success
    
    # Проверяем что получено подтверждение
    ack = await router.get_ack(source)
    assert ack is not None
    assert ack["target"] == target
    assert ack["message_type"] == message["type"]

@pytest.mark.asyncio
async def test_empty_message_queue(router):
    """Тест пустой очереди сообщений"""
    target = "node1"
    
    # Пытаемся получить сообщение из пустой очереди
    received = await router.get_message(target)
    assert received is None

@pytest.mark.asyncio
async def test_empty_group(router):
    """Тест пустой группы"""
    source = "node1"
    groups = ["empty_group"]
    message = {"type": "test", "data": "test_data"}
    
    # Рассылаем сообщение в пустую группу
    success = await router.multicast_message(source, groups, message)
    assert success  # Должно быть успешно, даже если группа пуста

@pytest.mark.asyncio
async def test_multiple_messages_order(router):
    """Тест порядка сообщений"""
    source = "node1"
    target = "node2"
    messages = [
        {"type": "test", "data": f"message{i}", "priority": 0}
        for i in range(5)
    ]
    
    # Отправляем сообщения
    for message in messages:
        await router.route_message(source, target, message)
    
    # Проверяем что сообщения получены в правильном порядке
    for i in range(5):
        received = await router.get_message(target)
        assert received is not None
        assert received["data"] == f"message{i}"

@pytest.mark.asyncio
async def test_message_to_self(router):
    """Тест отправки сообщения самому себе"""
    node = "node1"
    message = {"type": "test", "data": "test_data"}
    
    # Отправляем сообщение самому себе
    success = await router.route_message(node, node, message)
    assert success
    
    # Проверяем что сообщение доставлено
    received = await router.get_message(node)
    assert received is not None
    assert received["source"] == node
    assert received["type"] == message["type"]
    assert received["data"] == message["data"]

@pytest.mark.asyncio
async def test_stop_router(router):
    """Тест остановки маршрутизатора"""
    source = "node1"
    target = "node2"
    message = {"type": "test", "data": "test_data"}
    
    # Останавливаем маршрутизатор
    await router.stop()
    
    # Пытаемся отправить сообщение
    success = await router.route_message(source, target, message)
    assert not success  # Должно быть неуспешно, так как маршрутизатор остановлен

@pytest.mark.asyncio
async def test_invalid_message(router):
    """Тест обработки некорректного сообщения"""
    source = "node1"
    target = "node2"
    invalid_messages = [
        None,  # Пустое сообщение
        {},  # Пустой словарь
        {"type": None},  # Некорректный тип
        {"data": None},  # Нет типа сообщения
        {"type": "", "data": ""},  # Пустые строки
    ]
    
    # Пытаемся отправить некорректные сообщения
    for message in invalid_messages:
        success = await router.route_message(source, target, message)
        assert not success  # Должно быть неуспешно для некорректных сообщений

@pytest.mark.asyncio
async def test_invalid_target(router):
    """Тест обработки некорректного получателя"""
    source = "node1"
    invalid_targets = [
        None,  # Пустой получатель
        "",  # Пустая строка
        " ",  # Пробел
        "\t",  # Табуляция
        "\n",  # Перевод строки
    ]
    message = {"type": "test", "data": "test_data"}
    
    # Пытаемся отправить сообщения некорректным получателям
    for target in invalid_targets:
        success = await router.route_message(source, target, message)
        assert not success  # Должно быть неуспешно для некорректных получателей

@pytest.mark.asyncio
async def test_invalid_source(router):
    """Тест обработки некорректного отправителя"""
    target = "node2"
    invalid_sources = [
        None,  # Пустой отправитель
        "",  # Пустая строка
        " ",  # Пробел
        "\t",  # Табуляция
        "\n",  # Перевод строки
    ]
    message = {"type": "test", "data": "test_data"}
    
    # Пытаемся отправить сообщения от некорректных отправителей
    for source in invalid_sources:
        success = await router.route_message(source, target, message)
        assert not success  # Должно быть неуспешно для некорректных отправителей

@pytest.mark.asyncio
async def test_invalid_group(router):
    """Тест обработки некорректной группы"""
    source = "node1"
    invalid_groups = [
        None,  # Пустая группа
        "",  # Пустая строка
        " ",  # Пробел
        "\t",  # Табуляция
        "\n",  # Перевод строки
    ]
    message = {"type": "test", "data": "test_data"}
    
    # Пытаемся отправить сообщения в некорректные группы
    for group in invalid_groups:
        success = await router.multicast_message(source, [group], message)
        assert not success  # Должно быть неуспешно для некорректных групп

@pytest.mark.asyncio
async def test_performance_message_routing(router):
    """Тест производительности маршрутизации сообщений"""
    source = "node1"
    target = "node2"
    message = {"type": "test", "data": "test_data"}
    num_messages = 1000
    
    # Замеряем время отправки сообщений
    start_time = time.time()
    for _ in range(num_messages):
        await router.route_message(source, target, message)
    end_time = time.time()
    
    # Проверяем что среднее время отправки одного сообщения не превышает 1мс
    avg_time = (end_time - start_time) / num_messages
    assert avg_time < 0.001  # 1мс
    
    # Проверяем что все сообщения доставлены
    for _ in range(num_messages):
        received = await router.get_message(target)
        assert received is not None

@pytest.mark.asyncio
async def test_performance_broadcast(router):
    """Тест производительности широковещательной рассылки"""
    source = "node1"
    num_targets = 100
    targets = [f"node{i}" for i in range(2, num_targets + 2)]
    message = {"type": "test", "data": "test_data"}
    num_messages = 10
    
    # Замеряем время рассылки сообщений
    start_time = time.time()
    for _ in range(num_messages):
        await router.broadcast_message(source, targets, message)
    end_time = time.time()
    
    # Проверяем что среднее время рассылки одного сообщения не превышает 100мс
    avg_time = (end_time - start_time) / num_messages
    assert avg_time < 0.1  # 100мс
    
    # Проверяем что все сообщения доставлены
    for target in targets:
        for _ in range(num_messages):
            received = await router.get_message(target)
            assert received is not None

@pytest.mark.asyncio
async def test_performance_multicast(router):
    """Тест производительности групповой рассылки"""
    source = "node1"
    num_groups = 10
    nodes_per_group = 10
    groups = [f"group{i}" for i in range(num_groups)]
    message = {"type": "test", "data": "test_data"}
    num_messages = 10
    
    # Добавляем узлы в группы
    for group in groups:
        for i in range(nodes_per_group):
            await router.add_to_group(f"node{i}", group)
    
    # Замеряем время рассылки сообщений
    start_time = time.time()
    
    # Отправляем сообщения параллельно
    tasks = []
    for _ in range(num_messages):
        tasks.append(router.multicast_message(source, groups, message))
    await asyncio.gather(*tasks)
    
    end_time = time.time()
    
    # Проверяем что среднее время рассылки одного сообщения не превышает 200мс
    # Учитываем накладные расходы на обработку большого количества сообщений
    avg_time = (end_time - start_time) / num_messages
    assert avg_time < 0.2  # 200мс
    
    # Проверяем что все сообщения доставлены параллельно
    receive_tasks = []
    for i in range(nodes_per_group):
        node = f"node{i}"
        for _ in range(num_messages * num_groups):
            receive_tasks.append(router.get_message(node))
    
    received_messages = await asyncio.gather(*receive_tasks)
    assert all(msg is not None for msg in received_messages)
    assert len(received_messages) == num_messages * num_groups * nodes_per_group

@pytest.mark.asyncio
async def test_routing_performance_and_reliability(router):
    """Тест производительности и надежности маршрутизации"""
    source = "node1"
    num_targets = 50
    targets = [f"node{i}" for i in range(num_targets)]
    num_messages = 100
    
    # Создаем сообщения разных приоритетов
    messages = []
    for i in range(num_messages):
        priority = i % 3  # 0, 1, 2
        messages.append({
            "type": "test",
            "data": f"message{i}",
            "priority": priority,
            "ttl": 5 if i % 2 == 0 else None  # Некоторые сообщения с TTL
        })
    
    # Отправляем сообщения параллельно
    start_time = time.time()
    send_tasks = []
    for target in targets:
        for message in messages:
            send_tasks.append(router.route_message(source, target, message))
    
    # Ждем отправки всех сообщений
    await asyncio.gather(*send_tasks)
    send_time = time.time() - start_time
    
    # Проверяем производительность отправки
    avg_send_time = send_time / (num_targets * num_messages)
    assert avg_send_time < 0.001  # 1мс на сообщение
    
    # Получаем сообщения параллельно
    start_time = time.time()
    receive_tasks = []
    for target in targets:
        for _ in range(num_messages):
            receive_tasks.append(router.get_message(target))
    
    received_messages = await asyncio.gather(*receive_tasks)
    receive_time = time.time() - start_time
    
    # Проверяем производительность получения
    avg_receive_time = receive_time / (num_targets * num_messages)
    assert avg_receive_time < 0.001  # 1мс на сообщение
    
    # Проверяем что все сообщения доставлены
    assert all(msg is not None for msg in received_messages)
    assert len(received_messages) == num_targets * num_messages
    
    # Проверяем приоритизацию
    for target in targets:
        messages = []
        while True:
            msg = await router.get_message(target)
            if msg is None:
                break
            messages.append(msg)
        
        # Проверяем что сообщения отсортированы по приоритету
        priorities = [msg.get("priority", 0) for msg in messages]
        assert priorities == sorted(priorities, reverse=True)
    
    # Проверяем очистку устаревших сообщений
    await asyncio.sleep(6)  # Ждем истечения TTL
    
    # Проверяем что сообщения с TTL удалены
    for target in targets:
        msg = await router.get_message(target)
        if msg is not None:
            assert msg.get("ttl") is None  # Остались только сообщения без TTL 