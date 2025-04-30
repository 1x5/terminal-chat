"""
Тесты для менеджера узлов
"""
import pytest
import asyncio
import time
from src.node_manager import NodeManager, NodeInfo
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest.fixture
async def node_manager(config, crypto):
    manager = NodeManager(config, crypto)
    await manager.start()
    yield manager
    await manager.stop()

@pytest.mark.asyncio
async def test_add_remove_node(node_manager):
    """Тест добавления и удаления узла"""
    node_id = "test_node"
    public_key = "test_key"
    address = "127.0.0.1:8000"
    
    # Добавляем узел
    assert await node_manager.add_node(node_id, public_key, address)
    assert node_id in node_manager.nodes
    assert node_id in node_manager.active_nodes
    
    # Проверяем информацию об узле
    node = node_manager.nodes[node_id]
    assert node.node_id == node_id
    assert node.public_key == public_key
    assert node.address == address
    assert node.is_active
    
    # Удаляем узел
    assert await node_manager.remove_node(node_id)
    assert node_id not in node_manager.nodes
    assert node_id not in node_manager.active_nodes

@pytest.mark.asyncio
async def test_update_routes(node_manager):
    """Тест обновления маршрутов"""
    node_id = "test_node"
    public_key = "test_key"
    address = "127.0.0.1:8000"
    
    # Добавляем узел
    await node_manager.add_node(node_id, public_key, address)
    
    # Обновляем маршруты
    routes = {
        "target1": ["hop1", "hop2"],
        "target2": ["hop3"]
    }
    assert await node_manager.update_routes(node_id, routes)
    
    # Проверяем маршруты
    node = node_manager.nodes[node_id]
    assert node.routes == routes

@pytest.mark.asyncio
async def test_get_route(node_manager):
    """Тест получения маршрута"""
    # Добавляем несколько узлов
    nodes = [
        ("node1", "key1", "127.0.0.1:8001"),
        ("node2", "key2", "127.0.0.1:8002"),
        ("node3", "key3", "127.0.0.1:8003")
    ]
    
    for node_id, public_key, address in nodes:
        await node_manager.add_node(node_id, public_key, address)
    
    # Получаем маршрут
    route = await node_manager.get_route("node3")
    assert route is not None
    assert len(route) > 0
    assert "node3" in route

@pytest.mark.asyncio
async def test_node_monitoring(node_manager):
    """Тест мониторинга узлов"""
    node_id = "test_node"
    public_key = "test_key"
    address = "127.0.0.1:8000"
    
    # Добавляем узел
    await node_manager.add_node(node_id, public_key, address)
    
    # Ждем обновления маршрутов
    await asyncio.sleep(2)
    
    # Проверяем что узел все еще активен
    assert node_id in node_manager.active_nodes
    assert node_manager.nodes[node_id].is_active
    
    # Симулируем неактивность узла
    node_manager.nodes[node_id].last_seen = time.time() - 3601  # Больше часа
    
    # Ждем следующей проверки
    await asyncio.sleep(2)
    
    # Проверяем что узел удален
    assert node_id not in node_manager.nodes
    assert node_id not in node_manager.active_nodes

@pytest.mark.asyncio
async def test_node_registration(node_manager):
    """Тест регистрации узла"""
    # Регистрируем узел
    success = await node_manager.register_node(
        node_id="test_node",
        public_key="test_key",
        address="ws://localhost:8000"
    )
    assert success == True
    
    # Проверяем, что узел добавлен
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 1
    assert active_nodes[0].node_id == "test_node"
    assert active_nodes[0].public_key == "test_key"
    assert active_nodes[0].address == "ws://localhost:8000"
    assert active_nodes[0].is_active == True

@pytest.mark.asyncio
async def test_node_unregistration(node_manager):
    """Тест удаления узла"""
    # Регистрируем узел
    await node_manager.register_node(
        node_id="test_node",
        public_key="test_key",
        address="ws://localhost:8000"
    )
    
    # Удаляем узел
    success = await node_manager.unregister_node("test_node")
    assert success == True
    
    # Проверяем, что узел удален
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 0

@pytest.mark.asyncio
async def test_node_timeout(node_manager):
    """Тест таймаута узла"""
    # Регистрируем узел
    await node_manager.register_node(
        node_id="test_node",
        public_key="test_key",
        address="ws://localhost:8000"
    )
    
    # Устанавливаем старое время последнего обновления
    node_manager.nodes["test_node"].last_seen = time.time() - 400
    
    # Обновляем статус узлов
    await node_manager.update_node_status()
    
    # Проверяем, что узел помечен как неактивный
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 0

@pytest.mark.asyncio
async def test_route_management(node_manager):
    """Тест управления маршрутами"""
    # Регистрируем узлы
    await node_manager.register_node(
        node_id="node1",
        public_key="key1",
        address="ws://localhost:8001"
    )
    await node_manager.register_node(
        node_id="node2",
        public_key="key2",
        address="ws://localhost:8002"
    )
    
    # Обновляем маршруты
    routes = {
        "node2": ["node1", "node2"]
    }
    success = await node_manager.update_routes("node1", routes)
    assert success == True
    
    # Проверяем маршрут
    route = await node_manager.get_route("node2")
    assert route == ["node2"]  # Пока возвращаем прямой маршрут

@pytest.mark.asyncio
async def test_multiple_nodes(node_manager):
    """Тест работы с несколькими узлами"""
    # Регистрируем несколько узлов
    nodes = [
        ("node1", "key1", "ws://localhost:8001"),
        ("node2", "key2", "ws://localhost:8002"),
        ("node3", "key3", "ws://localhost:8003")
    ]
    
    for node_id, public_key, address in nodes:
        await node_manager.register_node(node_id, public_key, address)
    
    # Проверяем количество активных узлов
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 3
    
    # Деактивируем один узел
    node_manager.nodes["node2"].last_seen = time.time() - 400
    await node_manager.update_node_status()
    
    # Проверяем, что осталось 2 активных узла
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 2
    assert all(node.node_id != "node2" for node in active_nodes) 
 
 
Тесты для менеджера узлов
"""
import pytest
import asyncio
import time
from src.node_manager import NodeManager, NodeInfo
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest.fixture
async def node_manager(config, crypto):
    manager = NodeManager(config, crypto)
    await manager.start()
    yield manager
    await manager.stop()

@pytest.mark.asyncio
async def test_add_remove_node(node_manager):
    """Тест добавления и удаления узла"""
    node_id = "test_node"
    public_key = "test_key"
    address = "127.0.0.1:8000"
    
    # Добавляем узел
    assert await node_manager.add_node(node_id, public_key, address)
    assert node_id in node_manager.nodes
    assert node_id in node_manager.active_nodes
    
    # Проверяем информацию об узле
    node = node_manager.nodes[node_id]
    assert node.node_id == node_id
    assert node.public_key == public_key
    assert node.address == address
    assert node.is_active
    
    # Удаляем узел
    assert await node_manager.remove_node(node_id)
    assert node_id not in node_manager.nodes
    assert node_id not in node_manager.active_nodes

@pytest.mark.asyncio
async def test_update_routes(node_manager):
    """Тест обновления маршрутов"""
    node_id = "test_node"
    public_key = "test_key"
    address = "127.0.0.1:8000"
    
    # Добавляем узел
    await node_manager.add_node(node_id, public_key, address)
    
    # Обновляем маршруты
    routes = {
        "target1": ["hop1", "hop2"],
        "target2": ["hop3"]
    }
    assert await node_manager.update_routes(node_id, routes)
    
    # Проверяем маршруты
    node = node_manager.nodes[node_id]
    assert node.routes == routes

@pytest.mark.asyncio
async def test_get_route(node_manager):
    """Тест получения маршрута"""
    # Добавляем несколько узлов
    nodes = [
        ("node1", "key1", "127.0.0.1:8001"),
        ("node2", "key2", "127.0.0.1:8002"),
        ("node3", "key3", "127.0.0.1:8003")
    ]
    
    for node_id, public_key, address in nodes:
        await node_manager.add_node(node_id, public_key, address)
    
    # Получаем маршрут
    route = await node_manager.get_route("node3")
    assert route is not None
    assert len(route) > 0
    assert "node3" in route

@pytest.mark.asyncio
async def test_node_monitoring(node_manager):
    """Тест мониторинга узлов"""
    node_id = "test_node"
    public_key = "test_key"
    address = "127.0.0.1:8000"
    
    # Добавляем узел
    await node_manager.add_node(node_id, public_key, address)
    
    # Ждем обновления маршрутов
    await asyncio.sleep(2)
    
    # Проверяем что узел все еще активен
    assert node_id in node_manager.active_nodes
    assert node_manager.nodes[node_id].is_active
    
    # Симулируем неактивность узла
    node_manager.nodes[node_id].last_seen = time.time() - 3601  # Больше часа
    
    # Ждем следующей проверки
    await asyncio.sleep(2)
    
    # Проверяем что узел удален
    assert node_id not in node_manager.nodes
    assert node_id not in node_manager.active_nodes

@pytest.mark.asyncio
async def test_node_registration(node_manager):
    """Тест регистрации узла"""
    # Регистрируем узел
    success = await node_manager.register_node(
        node_id="test_node",
        public_key="test_key",
        address="ws://localhost:8000"
    )
    assert success == True
    
    # Проверяем, что узел добавлен
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 1
    assert active_nodes[0].node_id == "test_node"
    assert active_nodes[0].public_key == "test_key"
    assert active_nodes[0].address == "ws://localhost:8000"
    assert active_nodes[0].is_active == True

@pytest.mark.asyncio
async def test_node_unregistration(node_manager):
    """Тест удаления узла"""
    # Регистрируем узел
    await node_manager.register_node(
        node_id="test_node",
        public_key="test_key",
        address="ws://localhost:8000"
    )
    
    # Удаляем узел
    success = await node_manager.unregister_node("test_node")
    assert success == True
    
    # Проверяем, что узел удален
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 0

@pytest.mark.asyncio
async def test_node_timeout(node_manager):
    """Тест таймаута узла"""
    # Регистрируем узел
    await node_manager.register_node(
        node_id="test_node",
        public_key="test_key",
        address="ws://localhost:8000"
    )
    
    # Устанавливаем старое время последнего обновления
    node_manager.nodes["test_node"].last_seen = time.time() - 400
    
    # Обновляем статус узлов
    await node_manager.update_node_status()
    
    # Проверяем, что узел помечен как неактивный
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 0

@pytest.mark.asyncio
async def test_route_management(node_manager):
    """Тест управления маршрутами"""
    # Регистрируем узлы
    await node_manager.register_node(
        node_id="node1",
        public_key="key1",
        address="ws://localhost:8001"
    )
    await node_manager.register_node(
        node_id="node2",
        public_key="key2",
        address="ws://localhost:8002"
    )
    
    # Обновляем маршруты
    routes = {
        "node2": ["node1", "node2"]
    }
    success = await node_manager.update_routes("node1", routes)
    assert success == True
    
    # Проверяем маршрут
    route = await node_manager.get_route("node2")
    assert route == ["node2"]  # Пока возвращаем прямой маршрут

@pytest.mark.asyncio
async def test_multiple_nodes(node_manager):
    """Тест работы с несколькими узлами"""
    # Регистрируем несколько узлов
    nodes = [
        ("node1", "key1", "ws://localhost:8001"),
        ("node2", "key2", "ws://localhost:8002"),
        ("node3", "key3", "ws://localhost:8003")
    ]
    
    for node_id, public_key, address in nodes:
        await node_manager.register_node(node_id, public_key, address)
    
    # Проверяем количество активных узлов
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 3
    
    # Деактивируем один узел
    node_manager.nodes["node2"].last_seen = time.time() - 400
    await node_manager.update_node_status()
    
    # Проверяем, что осталось 2 активных узла
    active_nodes = await node_manager.get_active_nodes()
    assert len(active_nodes) == 2
    assert all(node.node_id != "node2" for node in active_nodes) 
 
 