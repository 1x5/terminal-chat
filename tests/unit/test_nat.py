"""
Тесты для NAT traversal
"""

import pytest
import asyncio
from src.nat import NATTraversal
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest.fixture
async def nat(config, crypto):
    nat = NATTraversal(config, crypto)
    await nat.start()
    yield nat
    await nat.stop()

@pytest.mark.asyncio
async def test_detect_nat_type(nat):
    """Тест определения типа NAT"""
    nat_type = await nat.detect_nat_type()
    assert nat_type in ["open", "full_cone", "restricted_cone", "port_restricted_cone", "symmetric"]

@pytest.mark.asyncio
async def test_get_public_ip(nat):
    """Тест получения публичного IP"""
    public_ip = await nat.get_public_ip()
    assert public_ip is not None
    assert isinstance(public_ip, str)

@pytest.mark.asyncio
async def test_get_public_port(nat):
    """Тест получения публичного порта"""
    local_port = 8000
    public_port = await nat.get_public_port(local_port)
    assert public_port is not None
    assert isinstance(public_port, int)

@pytest.mark.asyncio
async def test_create_hole(nat):
    """Тест создания дырки в NAT"""
    target_ip = "1.2.3.4"
    target_port = 8000
    
    # Создаем дырку
    success = await nat.create_hole(target_ip, target_port)
    assert success
    
    # Проверяем что дырка создана
    holes = await nat.get_holes()
    assert any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in holes)

@pytest.mark.asyncio
async def test_close_hole(nat):
    """Тест закрытия дырки в NAT"""
    target_ip = "1.2.3.4"
    target_port = 8000
    
    # Создаем дырку
    await nat.create_hole(target_ip, target_port)
    
    # Закрываем дырку
    success = await nat.close_hole(target_ip, target_port)
    assert success
    
    # Проверяем что дырка закрыта
    holes = await nat.get_holes()
    assert not any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in holes)

@pytest.mark.asyncio
async def test_get_holes(nat):
    """Тест получения списка дырок"""
    holes = [
        ("1.2.3.4", 8000),
        ("5.6.7.8", 8001),
        ("9.10.11.12", 8002)
    ]
    
    # Создаем дырки
    for target_ip, target_port in holes:
        await nat.create_hole(target_ip, target_port)
    
    # Получаем список дырок
    all_holes = await nat.get_holes()
    assert len(all_holes) == len(holes)
    
    # Проверяем что все дырки созданы
    for target_ip, target_port in holes:
        assert any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in all_holes)

@pytest.mark.asyncio
async def test_keep_alive(nat):
    """Тест поддержания дырки активной"""
    target_ip = "1.2.3.4"
    target_port = 8000
    
    # Создаем дырку
    await nat.create_hole(target_ip, target_port)
    
    # Поддерживаем дырку активной
    success = await nat.keep_alive(target_ip, target_port)
    assert success
    
    # Проверяем что дырка все еще активна
    holes = await nat.get_holes()
    assert any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in holes) 
Тесты для NAT traversal
"""

import pytest
import asyncio
from src.nat import NATTraversal
from src.crypto import CryptoManager
from src.config import Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def crypto():
    return CryptoManager()

@pytest.fixture
async def nat(config, crypto):
    nat = NATTraversal(config, crypto)
    await nat.start()
    yield nat
    await nat.stop()

@pytest.mark.asyncio
async def test_detect_nat_type(nat):
    """Тест определения типа NAT"""
    nat_type = await nat.detect_nat_type()
    assert nat_type in ["open", "full_cone", "restricted_cone", "port_restricted_cone", "symmetric"]

@pytest.mark.asyncio
async def test_get_public_ip(nat):
    """Тест получения публичного IP"""
    public_ip = await nat.get_public_ip()
    assert public_ip is not None
    assert isinstance(public_ip, str)

@pytest.mark.asyncio
async def test_get_public_port(nat):
    """Тест получения публичного порта"""
    local_port = 8000
    public_port = await nat.get_public_port(local_port)
    assert public_port is not None
    assert isinstance(public_port, int)

@pytest.mark.asyncio
async def test_create_hole(nat):
    """Тест создания дырки в NAT"""
    target_ip = "1.2.3.4"
    target_port = 8000
    
    # Создаем дырку
    success = await nat.create_hole(target_ip, target_port)
    assert success
    
    # Проверяем что дырка создана
    holes = await nat.get_holes()
    assert any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in holes)

@pytest.mark.asyncio
async def test_close_hole(nat):
    """Тест закрытия дырки в NAT"""
    target_ip = "1.2.3.4"
    target_port = 8000
    
    # Создаем дырку
    await nat.create_hole(target_ip, target_port)
    
    # Закрываем дырку
    success = await nat.close_hole(target_ip, target_port)
    assert success
    
    # Проверяем что дырка закрыта
    holes = await nat.get_holes()
    assert not any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in holes)

@pytest.mark.asyncio
async def test_get_holes(nat):
    """Тест получения списка дырок"""
    holes = [
        ("1.2.3.4", 8000),
        ("5.6.7.8", 8001),
        ("9.10.11.12", 8002)
    ]
    
    # Создаем дырки
    for target_ip, target_port in holes:
        await nat.create_hole(target_ip, target_port)
    
    # Получаем список дырок
    all_holes = await nat.get_holes()
    assert len(all_holes) == len(holes)
    
    # Проверяем что все дырки созданы
    for target_ip, target_port in holes:
        assert any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in all_holes)

@pytest.mark.asyncio
async def test_keep_alive(nat):
    """Тест поддержания дырки активной"""
    target_ip = "1.2.3.4"
    target_port = 8000
    
    # Создаем дырку
    await nat.create_hole(target_ip, target_port)
    
    # Поддерживаем дырку активной
    success = await nat.keep_alive(target_ip, target_port)
    assert success
    
    # Проверяем что дырка все еще активна
    holes = await nat.get_holes()
    assert any(h["target_ip"] == target_ip and h["target_port"] == target_port for h in holes) 