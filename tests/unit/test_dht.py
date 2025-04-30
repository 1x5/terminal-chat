"""
Тесты для DHT
"""

import pytest
import asyncio
import time
from src.dht import DHT, NodeInfo
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest.fixture
async def dht(config, crypto):
    dht = DHT(config, crypto)
    await dht.start()
    yield dht
    await dht.stop()

@pytest.fixture
def sample_nodes():
    return [
        NodeInfo(
            node_id="1" * 40,
            address="127.0.0.1",
            port=8000,
            public_key="test_key_1",
            last_seen=0.0
        ),
        NodeInfo(
            node_id="2" * 40,
            address="127.0.0.1",
            port=8001,
            public_key="test_key_2",
            last_seen=0.0
        )
    ]

@pytest.mark.asyncio
async def test_add_node(dht, sample_nodes):
    # Test adding a node
    result = await dht.add_node(sample_nodes[0])
    assert result is True
    
    # Test adding same node again
    result = await dht.add_node(sample_nodes[0])
    assert result is True
    
    # Test bucket size limit
    for i in range(21):  # k + 1 nodes
        node = NodeInfo(
            node_id=f"{i}" * 40,
            address="127.0.0.1",
            port=8000 + i,
            public_key=f"test_key_{i}",
            last_seen=0.0
        )
        await dht.add_node(node)
    
    # Verify bucket size doesn't exceed k
    bucket_index = dht._get_bucket_index(sample_nodes[0].node_id)
    assert len(dht.buckets[bucket_index]) <= dht.k

@pytest.mark.asyncio
async def test_find_node(dht, sample_nodes):
    # Add some nodes
    for node in sample_nodes:
        await dht.add_node(node)
    
    # Test finding nodes
    found_nodes = await dht.find_node(sample_nodes[0].node_id)
    assert len(found_nodes) > 0
    assert any(node.node_id == sample_nodes[0].node_id for node in found_nodes)

@pytest.mark.asyncio
async def test_remove_node(dht, sample_nodes):
    # Add a node
    await dht.add_node(sample_nodes[0])
    
    # Test removing the node
    result = await dht.remove_node(sample_nodes[0].node_id)
    assert result is True
    
    # Verify node is removed
    bucket_index = dht._get_bucket_index(sample_nodes[0].node_id)
    assert not any(node.node_id == sample_nodes[0].node_id for node in dht.buckets[bucket_index])
    
    # Test removing non-existent node
    result = await dht.remove_node("non_existent")
    assert result is False

@pytest.mark.asyncio
async def test_cleanup(dht, sample_nodes, monkeypatch):
    # Mock current time to be far in the future
    future_time = time.time() + 7200  # 2 hours in the future
    monkeypatch.setattr(asyncio.get_event_loop(), 'time', lambda: future_time)
    
    # Add nodes with old timestamps
    for node in sample_nodes:
        node.last_seen = time.time()  # Current time (2 hours before cleanup)
        await dht.add_node(node)
    
    # Run cleanup
    await dht.cleanup()
    
    # Verify old nodes are removed
    for node in sample_nodes:
        bucket_index = dht._get_bucket_index(node.node_id)
        assert not any(n.node_id == node.node_id for n in dht.buckets[bucket_index])

@pytest.mark.asyncio
async def test_distance_calculation(dht):
    # Test distance between identical nodes
    assert dht._get_distance("0" * 40, "0" * 40) == 0
    
    # Test distance between different nodes
    assert dht._get_distance("0" * 40, "1" * 40) > 0
    
    # Test distance symmetry
    id1 = "1" * 40
    id2 = "2" * 40
    assert dht._get_distance(id1, id2) == dht._get_distance(id2, id1)

@pytest.mark.asyncio
async def test_store_and_get(dht, sample_nodes):
    # Add some nodes to the network
    for node in sample_nodes:
        await dht.add_node(node)
    
    # Test storing a value
    key = "test_key"
    value = {"data": "test_value"}
    result = await dht.store(key, value)
    assert result is True
    
    # Test retrieving the value
    retrieved = await dht.get(key)
    assert retrieved == value
    
    # Test retrieving non-existent key
    retrieved = await dht.get("non_existent")
    assert retrieved is None

@pytest.mark.asyncio
async def test_value_expiration(dht, sample_nodes, monkeypatch):
    # Add some nodes
    for node in sample_nodes:
        await dht.add_node(node)
    
    # Store a value with short TTL
    key = "test_key"
    value = "test_value"
    await dht.store(key, value, ttl=1)  # 1 second TTL
    
    # Verify value exists
    retrieved = await dht.get(key)
    assert retrieved == value
    
    # Mock time to be after TTL
    future_time = time.time() + 2  # 2 seconds in the future
    monkeypatch.setattr(asyncio.get_event_loop(), 'time', lambda: future_time)
    
    # Run cleanup
    await dht.cleanup()
    
    # Verify value is expired
    retrieved = await dht.get(key)
    assert retrieved is None

@pytest.mark.asyncio
async def test_value_replication(dht, sample_nodes):
    # Add enough nodes for replication
    for i in range(5):
        node = NodeInfo(
            node_id=f"{i}" * 40,
            address="127.0.0.1",
            port=8000 + i,
            public_key=f"test_key_{i}",
            last_seen=time.time()
        )
        await dht.add_node(node)
    
    # Store value with specific replication factor
    key = "test_key"
    value = "test_value"
    replicas = 3
    result = await dht.store(key, value, replicas=replicas)
    assert result is True  # Should succeed with enough nodes

@pytest.mark.asyncio
async def test_put_get(dht):
    """Тест добавления и получения значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    success = await dht.put(key, value)
    assert success
    
    # Получаем значение
    retrieved = await dht.get(key)
    assert retrieved == value

@pytest.mark.asyncio
async def test_remove(dht):
    """Тест удаления значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    await dht.put(key, value)
    
    # Удаляем значение
    success = await dht.remove(key)
    assert success
    
    # Проверяем что значение удалено
    retrieved = await dht.get(key)
    assert retrieved is None

@pytest.mark.asyncio
async def test_find_value(dht):
    """Тест поиска значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    await dht.put(key, value)
    
    # Ищем значение
    found = await dht.find_value(key)
    assert found is not None
    assert found == value

@pytest.mark.asyncio
async def test_store(dht):
    """Тест хранения данных"""
    key = "test_key"
    value = "test_value"
    
    # Сохраняем значение
    assert await dht.store(key, value)
    
    # Проверяем что значение сохранено
    result = await dht.get(key)
    assert result == value

@pytest.mark.asyncio
async def test_join_network(dht):
    """Тест присоединения к сети"""
    bootstrap_node = ("bootstrap", "bootstrap_key", "127.0.0.1:8000")
    
    # Присоединяемся к сети
    assert await dht.join_network(bootstrap_node)
    
    # Проверяем что узел добавлен
    node = await dht.find_node(bootstrap_node[0])
    assert node is not None
    assert node.node_id == bootstrap_node[0]
    assert node.public_key == bootstrap_node[1]
    assert node.address == bootstrap_node[2]

@pytest.mark.asyncio
async def test_leave_network(dht):
    """Тест выхода из сети"""
    # Присоединяемся к сети
    bootstrap_node = ("bootstrap", "bootstrap_key", "127.0.0.1:8000")
    await dht.join_network(bootstrap_node)
    
    # Выходим из сети
    assert await dht.leave_network()
    
    # Проверяем что узел удален
    node = await dht.find_node(bootstrap_node[0])
    assert node is None

@pytest.mark.asyncio
async def test_find_node(dht):
    """Тест поиска узла"""
    node_id = "test_node"
    
    # Добавляем узел
    await dht.put(node_id, {"ip": "1.2.3.4", "port": 8000})
    
    # Ищем узел
    node = await dht.find_node(node_id)
    assert node is not None
    assert node["ip"] == "1.2.3.4"
    assert node["port"] == 8000

@pytest.mark.asyncio
async def test_iterative_find_node(dht):
    """Тест итеративного поиска узла"""
    node_id = "test_node"
    
    # Добавляем узел
    await dht.put(node_id, {"ip": "1.2.3.4", "port": 8000})
    
    # Ищем узел итеративно
    nodes = await dht.iterative_find_node(node_id)
    assert len(nodes) > 0
    assert any(n["id"] == node_id for n in nodes)

@pytest.mark.asyncio
async def test_iterative_find_value(dht):
    """Тест итеративного поиска значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    await dht.put(key, value)
    
    # Ищем значение итеративно
    values = await dht.iterative_find_value(key)
    assert len(values) > 0
    assert value in values

@pytest.mark.asyncio
async def test_bootstrap(dht):
    """Тест начальной загрузки"""
    # Добавляем начальные узлы
    bootstrap_nodes = [
        {"id": "node1", "ip": "1.2.3.4", "port": 8000},
        {"id": "node2", "ip": "5.6.7.8", "port": 8001}
    ]
    
    for node in bootstrap_nodes:
        await dht.put(node["id"], {"ip": node["ip"], "port": node["port"]})
    
    # Выполняем начальную загрузку
    success = await dht.bootstrap()
    assert success
    
    # Проверяем что узлы добавлены в таблицу маршрутизации
    routing_table = await dht.get_routing_table()
    assert len(routing_table) >= len(bootstrap_nodes) 
Тесты для DHT
"""

import pytest
import asyncio
import time
from src.dht import DHT, NodeInfo
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest.fixture
async def dht(config, crypto):
    dht = DHT(config, crypto)
    await dht.start()
    yield dht
    await dht.stop()

@pytest.fixture
def sample_nodes():
    return [
        NodeInfo(
            node_id="1" * 40,
            address="127.0.0.1",
            port=8000,
            public_key="test_key_1",
            last_seen=0.0
        ),
        NodeInfo(
            node_id="2" * 40,
            address="127.0.0.1",
            port=8001,
            public_key="test_key_2",
            last_seen=0.0
        )
    ]

@pytest.mark.asyncio
async def test_add_node(dht, sample_nodes):
    # Test adding a node
    result = await dht.add_node(sample_nodes[0])
    assert result is True
    
    # Test adding same node again
    result = await dht.add_node(sample_nodes[0])
    assert result is True
    
    # Test bucket size limit
    for i in range(21):  # k + 1 nodes
        node = NodeInfo(
            node_id=f"{i}" * 40,
            address="127.0.0.1",
            port=8000 + i,
            public_key=f"test_key_{i}",
            last_seen=0.0
        )
        await dht.add_node(node)
    
    # Verify bucket size doesn't exceed k
    bucket_index = dht._get_bucket_index(sample_nodes[0].node_id)
    assert len(dht.buckets[bucket_index]) <= dht.k

@pytest.mark.asyncio
async def test_find_node(dht, sample_nodes):
    # Add some nodes
    for node in sample_nodes:
        await dht.add_node(node)
    
    # Test finding nodes
    found_nodes = await dht.find_node(sample_nodes[0].node_id)
    assert len(found_nodes) > 0
    assert any(node.node_id == sample_nodes[0].node_id for node in found_nodes)

@pytest.mark.asyncio
async def test_remove_node(dht, sample_nodes):
    # Add a node
    await dht.add_node(sample_nodes[0])
    
    # Test removing the node
    result = await dht.remove_node(sample_nodes[0].node_id)
    assert result is True
    
    # Verify node is removed
    bucket_index = dht._get_bucket_index(sample_nodes[0].node_id)
    assert not any(node.node_id == sample_nodes[0].node_id for node in dht.buckets[bucket_index])
    
    # Test removing non-existent node
    result = await dht.remove_node("non_existent")
    assert result is False

@pytest.mark.asyncio
async def test_cleanup(dht, sample_nodes, monkeypatch):
    # Mock current time to be far in the future
    future_time = time.time() + 7200  # 2 hours in the future
    monkeypatch.setattr(asyncio.get_event_loop(), 'time', lambda: future_time)
    
    # Add nodes with old timestamps
    for node in sample_nodes:
        node.last_seen = time.time()  # Current time (2 hours before cleanup)
        await dht.add_node(node)
    
    # Run cleanup
    await dht.cleanup()
    
    # Verify old nodes are removed
    for node in sample_nodes:
        bucket_index = dht._get_bucket_index(node.node_id)
        assert not any(n.node_id == node.node_id for n in dht.buckets[bucket_index])

@pytest.mark.asyncio
async def test_distance_calculation(dht):
    # Test distance between identical nodes
    assert dht._get_distance("0" * 40, "0" * 40) == 0
    
    # Test distance between different nodes
    assert dht._get_distance("0" * 40, "1" * 40) > 0
    
    # Test distance symmetry
    id1 = "1" * 40
    id2 = "2" * 40
    assert dht._get_distance(id1, id2) == dht._get_distance(id2, id1)

@pytest.mark.asyncio
async def test_store_and_get(dht, sample_nodes):
    # Add some nodes to the network
    for node in sample_nodes:
        await dht.add_node(node)
    
    # Test storing a value
    key = "test_key"
    value = {"data": "test_value"}
    result = await dht.store(key, value)
    assert result is True
    
    # Test retrieving the value
    retrieved = await dht.get(key)
    assert retrieved == value
    
    # Test retrieving non-existent key
    retrieved = await dht.get("non_existent")
    assert retrieved is None

@pytest.mark.asyncio
async def test_value_expiration(dht, sample_nodes, monkeypatch):
    # Add some nodes
    for node in sample_nodes:
        await dht.add_node(node)
    
    # Store a value with short TTL
    key = "test_key"
    value = "test_value"
    await dht.store(key, value, ttl=1)  # 1 second TTL
    
    # Verify value exists
    retrieved = await dht.get(key)
    assert retrieved == value
    
    # Mock time to be after TTL
    future_time = time.time() + 2  # 2 seconds in the future
    monkeypatch.setattr(asyncio.get_event_loop(), 'time', lambda: future_time)
    
    # Run cleanup
    await dht.cleanup()
    
    # Verify value is expired
    retrieved = await dht.get(key)
    assert retrieved is None

@pytest.mark.asyncio
async def test_value_replication(dht, sample_nodes):
    # Add enough nodes for replication
    for i in range(5):
        node = NodeInfo(
            node_id=f"{i}" * 40,
            address="127.0.0.1",
            port=8000 + i,
            public_key=f"test_key_{i}",
            last_seen=time.time()
        )
        await dht.add_node(node)
    
    # Store value with specific replication factor
    key = "test_key"
    value = "test_value"
    replicas = 3
    result = await dht.store(key, value, replicas=replicas)
    assert result is True  # Should succeed with enough nodes

@pytest.mark.asyncio
async def test_put_get(dht):
    """Тест добавления и получения значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    success = await dht.put(key, value)
    assert success
    
    # Получаем значение
    retrieved = await dht.get(key)
    assert retrieved == value

@pytest.mark.asyncio
async def test_remove(dht):
    """Тест удаления значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    await dht.put(key, value)
    
    # Удаляем значение
    success = await dht.remove(key)
    assert success
    
    # Проверяем что значение удалено
    retrieved = await dht.get(key)
    assert retrieved is None

@pytest.mark.asyncio
async def test_find_value(dht):
    """Тест поиска значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    await dht.put(key, value)
    
    # Ищем значение
    found = await dht.find_value(key)
    assert found is not None
    assert found == value

@pytest.mark.asyncio
async def test_store(dht):
    """Тест хранения данных"""
    key = "test_key"
    value = "test_value"
    
    # Сохраняем значение
    assert await dht.store(key, value)
    
    # Проверяем что значение сохранено
    result = await dht.get(key)
    assert result == value

@pytest.mark.asyncio
async def test_join_network(dht):
    """Тест присоединения к сети"""
    bootstrap_node = ("bootstrap", "bootstrap_key", "127.0.0.1:8000")
    
    # Присоединяемся к сети
    assert await dht.join_network(bootstrap_node)
    
    # Проверяем что узел добавлен
    node = await dht.find_node(bootstrap_node[0])
    assert node is not None
    assert node.node_id == bootstrap_node[0]
    assert node.public_key == bootstrap_node[1]
    assert node.address == bootstrap_node[2]

@pytest.mark.asyncio
async def test_leave_network(dht):
    """Тест выхода из сети"""
    # Присоединяемся к сети
    bootstrap_node = ("bootstrap", "bootstrap_key", "127.0.0.1:8000")
    await dht.join_network(bootstrap_node)
    
    # Выходим из сети
    assert await dht.leave_network()
    
    # Проверяем что узел удален
    node = await dht.find_node(bootstrap_node[0])
    assert node is None

@pytest.mark.asyncio
async def test_find_node(dht):
    """Тест поиска узла"""
    node_id = "test_node"
    
    # Добавляем узел
    await dht.put(node_id, {"ip": "1.2.3.4", "port": 8000})
    
    # Ищем узел
    node = await dht.find_node(node_id)
    assert node is not None
    assert node["ip"] == "1.2.3.4"
    assert node["port"] == 8000

@pytest.mark.asyncio
async def test_iterative_find_node(dht):
    """Тест итеративного поиска узла"""
    node_id = "test_node"
    
    # Добавляем узел
    await dht.put(node_id, {"ip": "1.2.3.4", "port": 8000})
    
    # Ищем узел итеративно
    nodes = await dht.iterative_find_node(node_id)
    assert len(nodes) > 0
    assert any(n["id"] == node_id for n in nodes)

@pytest.mark.asyncio
async def test_iterative_find_value(dht):
    """Тест итеративного поиска значения"""
    key = "test_key"
    value = "test_value"
    
    # Добавляем значение
    await dht.put(key, value)
    
    # Ищем значение итеративно
    values = await dht.iterative_find_value(key)
    assert len(values) > 0
    assert value in values

@pytest.mark.asyncio
async def test_bootstrap(dht):
    """Тест начальной загрузки"""
    # Добавляем начальные узлы
    bootstrap_nodes = [
        {"id": "node1", "ip": "1.2.3.4", "port": 8000},
        {"id": "node2", "ip": "5.6.7.8", "port": 8001}
    ]
    
    for node in bootstrap_nodes:
        await dht.put(node["id"], {"ip": node["ip"], "port": node["port"]})
    
    # Выполняем начальную загрузку
    success = await dht.bootstrap()
    assert success
    
    # Проверяем что узлы добавлены в таблицу маршрутизации
    routing_table = await dht.get_routing_table()
    assert len(routing_table) >= len(bootstrap_nodes) 
 