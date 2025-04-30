"""
Тесты для основного модуля приложения
"""

import pytest
import asyncio
import os
import tempfile
from src.securetermchat import SecureTermChat
from src.config import Config
from src.peer_discovery import PeerDiscovery
from src.network import P2PNetwork
from src.onion_routing import OnionRoutingManager
from src.ui import TerminalUI

@pytest.fixture
def config_file():
    """Создает временный конфигурационный файл"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("""
        {
            "host": "127.0.0.1",
            "port": 10001,
            "data_dir": "/tmp/securetermchat",
            "log_level": "INFO",
            "peers": []
        }
        """)
    yield f.name
    os.unlink(f.name)

@pytest.fixture
def app(config_file):
    """Создает экземпляр приложения"""
    return SecureTermChat(config_file)

def test_app_initialization(app, config_file):
    """Проверяет инициализацию приложения"""
    assert isinstance(app.config, Config)
    assert isinstance(app.peer_discovery, PeerDiscovery)
    assert isinstance(app.p2p_network, P2PNetwork)
    assert isinstance(app.onion_routing, OnionRoutingManager)
    assert isinstance(app.ui, TerminalUI)

def test_app_startup(app):
    """Проверяет запуск приложения"""
    # Запускаем приложение
    app.start()
    
    # Проверяем, что все компоненты запущены
    assert app.peer_discovery.is_running
    assert app.p2p_network.is_running
    assert app.onion_routing.is_running
    assert app.ui.is_running

def test_app_shutdown(app):
    """Проверяет остановку приложения"""
    # Запускаем приложение
    app.start()
    
    # Останавливаем приложение
    app.stop()
    
    # Проверяем, что все компоненты остановлены
    assert not app.peer_discovery.is_running
    assert not app.p2p_network.is_running
    assert not app.onion_routing.is_running
    assert not app.ui.is_running

def test_peer_discovery_integration(app):
    """Проверяет интеграцию с модулем обнаружения пиров"""
    # Запускаем приложение
    app.start()
    
    # Добавляем пира
    app.peer_discovery.announce_peer("127.0.0.1", 10002)
    
    # Проверяем, что пир обнаружен
    peers = app.peer_discovery.get_peers()
    assert len(peers) == 1
    assert peers[0]["host"] == "127.0.0.1"
    assert peers[0]["port"] == 10002

def test_p2p_network_integration(app):
    """Проверяет интеграцию с модулем P2P сети"""
    # Запускаем приложение
    app.start()
    
    # Подключаемся к пиру
    app.p2p_network.connect_to_peer("127.0.0.1", 10002)
    
    # Проверяем, что соединение установлено
    assert app.p2p_network.is_connected_to("127.0.0.1", 10002)

def test_onion_routing_integration(app):
    """Проверяет интеграцию с модулем луковой маршрутизации"""
    # Запускаем приложение
    app.start()
    
    # Создаем цепочку маршрутизации
    circuit = app.onion_routing.create_circuit([
        ("127.0.0.1", 10002),
        ("127.0.0.1", 10003)
    ])
    
    # Проверяем, что цепочка создана
    assert circuit is not None
    assert len(circuit) == 2

def test_ui_integration(app):
    """Проверяет интеграцию с модулем пользовательского интерфейса"""
    # Запускаем приложение
    app.start()
    
    # Добавляем контакт через UI
    app.ui.add_contact("peer1", "127.0.0.1", 10002)
    
    # Проверяем, что контакт добавлен
    assert "peer1" in app.ui.contacts
    assert app.ui.contacts["peer1"]["host"] == "127.0.0.1"
    assert app.ui.contacts["peer1"]["port"] == 10002

def test_message_flow(app):
    """Проверяет поток сообщений через все компоненты"""
    # Запускаем приложение
    app.start()
    
    # Добавляем контакт
    app.ui.add_contact("peer1", "127.0.0.1", 10002)
    
    # Создаем цепочку маршрутизации
    circuit = app.onion_routing.create_circuit([
        ("127.0.0.1", 10002)
    ])
    
    # Отправляем сообщение
    app.ui.send_message("peer1", "Hello, world!")
    
    # Проверяем, что сообщение добавлено в историю
    messages = app.ui.history.get_messages("peer1")
    assert len(messages) == 1
    assert messages[0]["sender"] == "me"
    assert messages[0]["content"] == "Hello, world!"

def test_error_handling(app):
    """Проверяет обработку ошибок"""
    # Запускаем приложение
    app.start()
    
    # Пытаемся подключиться к несуществующему пиру
    with pytest.raises(Exception):
        app.p2p_network.connect_to_peer("invalid", 10002)
    
    # Проверяем, что статус обновлен
    assert app.ui.status.startswith("Error:")
    assert app.ui.status_is_error 