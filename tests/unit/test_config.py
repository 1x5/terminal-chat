"""
Тесты для модуля конфигурации
"""

import pytest
import os
import tempfile
import json
from src.config import Config

@pytest.fixture
def config_file():
    """Создает временный конфигурационный файл"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump({
            "listen_host": "127.0.0.1",
            "listen_port": 10001,
            "data_dir": "/tmp/securetermchat",
            "log_level": "INFO",
            "bootstrap_nodes": [
                "127.0.0.1:10002",
                "127.0.0.1:10003"
            ]
        }, f)
    yield f.name
    os.unlink(f.name)

@pytest.mark.asyncio
async def test_config_loading(config_file):
    """Проверяет загрузку конфигурации из файла"""
    config = Config(config_file)
    await config.load()
    
    assert config.config["listen_host"] == "127.0.0.1"
    assert config.config["listen_port"] == 10001
    assert config.data_dir == "/tmp/securetermchat"
    assert config.config["log_level"] == "INFO"
    assert len(config.config["bootstrap_nodes"]) == 2
    assert config.config["bootstrap_nodes"][0] == "127.0.0.1:10002"
    assert config.config["bootstrap_nodes"][1] == "127.0.0.1:10003"

@pytest.mark.asyncio
async def test_config_saving(config_file):
    """Проверяет сохранение конфигурации в файл"""
    config = Config(config_file)
    await config.load()
    
    # Изменяем конфигурацию
    config.config["listen_host"] = "localhost"
    config.config["listen_port"] = 10004
    config.config["bootstrap_nodes"].append("127.0.0.1:10005")
    
    # Сохраняем изменения
    await config.save()
    
    # Загружаем конфигурацию заново
    new_config = Config(config_file)
    await new_config.load()
    
    assert new_config.config["listen_host"] == "localhost"
    assert new_config.config["listen_port"] == 10004
    assert len(new_config.config["bootstrap_nodes"]) == 3
    assert new_config.config["bootstrap_nodes"][2] == "127.0.0.1:10005"

@pytest.mark.asyncio
async def test_config_validation():
    """Проверяет валидацию конфигурации"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump({
            "listen_host": "invalid_host",
            "listen_port": -1,
            "data_dir": "",
            "log_level": "INVALID",
            "bootstrap_nodes": [
                "invalid:port"
            ]
        }, f)
    
    config = Config(f.name)
    with pytest.raises(ValueError):
        await config.load()
    
    os.unlink(f.name)

@pytest.mark.asyncio
async def test_config_defaults():
    """Проверяет значения по умолчанию"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump({}, f)
    
    config = Config(f.name)
    await config.load()
    
    assert config.config["listen_host"] == "0.0.0.0"
    assert config.config["listen_port"] == 8765
    assert "securetermchat" in config.data_dir
    assert config.config["log_level"] == "INFO"
    assert len(config.config["bootstrap_nodes"]) == 2
    
    os.unlink(f.name)

@pytest.mark.asyncio
async def test_contact_management(config_file):
    """Проверяет управление списком контактов"""
    config = Config(config_file)
    await config.load()
    
    # Добавляем контакт
    test_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    await config.add_contact("test_user", test_key)
    assert "test_user" in config.contacts
    assert config.contacts["test_user"]["public_key"] == test_key
    
    # Удаляем контакт
    await config.remove_contact("test_user")
    assert "test_user" not in config.contacts

@pytest.mark.asyncio
async def test_peer_management(config_file):
    """Проверяет управление списком пиров"""
    config = Config(config_file)
    await config.load()
    
    # Добавляем пира
    await config.add_peer("127.0.0.1", 10004)
    assert len(config.config["bootstrap_nodes"]) == 3
    assert "127.0.0.1:10004" in config.config["bootstrap_nodes"]
    
    # Удаляем пира
    await config.remove_peer("127.0.0.1", 10002)
    assert len(config.config["bootstrap_nodes"]) == 2
    assert "127.0.0.1:10002" not in config.config["bootstrap_nodes"] 