"""
Общие фикстуры для тестов
"""

import pytest
import os
import tempfile
import json
from src.config import Config
from src.message_history import MessageHistory
from src.ui import TerminalUI
from src.securetermchat import SecureTermChat

@pytest.fixture
def temp_dir():
    """Создает временную директорию"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def config_file(temp_dir):
    """Создает временный конфигурационный файл"""
    config_path = os.path.join(temp_dir, "config.json")
    with open(config_path, 'w') as f:
        json.dump({
            "host": "127.0.0.1",
            "port": 10001,
            "data_dir": temp_dir,
            "log_level": "INFO",
            "peers": []
        }, f)
    yield config_path

@pytest.fixture
def history_file(temp_dir):
    """Создает временный файл истории сообщений"""
    history_path = os.path.join(temp_dir, "chat_history")
    with open(history_path, 'w') as f:
        json.dump({
            "messages": {},
            "unread": {}
        }, f)
    yield history_path

@pytest.fixture
def config(config_file):
    """Создает экземпляр конфигурации"""
    return Config(config_file)

@pytest.fixture
def history(history_file):
    """Создает экземпляр истории сообщений"""
    return MessageHistory(history_file)

@pytest.fixture
def ui(temp_dir):
    """Создает экземпляр пользовательского интерфейса"""
    return TerminalUI(temp_dir)

@pytest.fixture
def app(config_file):
    """Создает экземпляр приложения"""
    return SecureTermChat(config_file)

@pytest.fixture
def mock_peer():
    """Создает тестового пира"""
    return {
        "host": "127.0.0.1",
        "port": 10002
    }

@pytest.fixture
def mock_message():
    """Создает тестовое сообщение"""
    return {
        "sender": "peer1",
        "content": "Test message",
        "timestamp": 1000
    }

@pytest.fixture
def mock_circuit():
    """Создает тестовую цепочку маршрутизации"""
    return [
        ("127.0.0.1", 10002),
        ("127.0.0.1", 10003)
    ] 