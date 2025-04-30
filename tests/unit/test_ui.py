"""
Тесты для модуля пользовательского интерфейса
"""

import pytest
import os
import tempfile
from src.ui import TerminalUI
from src.message_history import MessageHistory

@pytest.fixture
def data_dir():
    """Создает временную директорию для данных"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def ui(data_dir):
    """Создает экземпляр пользовательского интерфейса"""
    return TerminalUI(data_dir)

def test_ui_initialization(ui, data_dir):
    """Проверяет инициализацию пользовательского интерфейса"""
    assert ui.data_dir == data_dir
    assert os.path.exists(os.path.join(data_dir, "chat_history"))
    assert isinstance(ui.history, MessageHistory)

def test_command_parsing(ui):
    """Проверяет разбор команд"""
    # Проверяем команду /help
    command, args = ui.parse_command("/help")
    assert command == "help"
    assert args == []
    
    # Проверяем команду /add
    command, args = ui.parse_command("/add 127.0.0.1 10001")
    assert command == "add"
    assert args == ["127.0.0.1", "10001"]
    
    # Проверяем команду /chat
    command, args = ui.parse_command("/chat peer1")
    assert command == "chat"
    assert args == ["peer1"]
    
    # Проверяем обычное сообщение
    command, args = ui.parse_command("Hello, world!")
    assert command is None
    assert args == ["Hello, world!"]

def test_contact_management(ui):
    """Проверяет управление контактами"""
    # Добавляем контакт
    ui.add_contact("peer1", "127.0.0.1", 10001)
    assert "peer1" in ui.contacts
    assert ui.contacts["peer1"]["host"] == "127.0.0.1"
    assert ui.contacts["peer1"]["port"] == 10001
    
    # Удаляем контакт
    ui.remove_contact("peer1")
    assert "peer1" not in ui.contacts

def test_message_handling(ui):
    """Проверяет обработку сообщений"""
    # Добавляем контакт
    ui.add_contact("peer1", "127.0.0.1", 10001)
    
    # Отправляем сообщение
    ui.send_message("peer1", "Hello, world!")
    
    # Проверяем, что сообщение добавлено в историю
    messages = ui.history.get_messages("peer1")
    assert len(messages) == 1
    assert messages[0]["sender"] == "me"
    assert messages[0]["content"] == "Hello, world!"
    
    # Получаем сообщение
    ui.receive_message("peer1", "Hi there!")
    
    # Проверяем, что сообщение добавлено в историю
    messages = ui.history.get_messages("peer1")
    assert len(messages) == 2
    assert messages[1]["sender"] == "peer1"
    assert messages[1]["content"] == "Hi there!"

def test_status_updates(ui):
    """Проверяет обновление статуса"""
    # Проверяем начальный статус
    assert ui.status == "Ready"
    
    # Обновляем статус
    ui.update_status("Connecting...")
    assert ui.status == "Connecting..."
    
    # Обновляем статус с ошибкой
    ui.update_status("Error: Connection failed", is_error=True)
    assert ui.status == "Error: Connection failed"
    assert ui.status_is_error

def test_chat_session_management(ui):
    """Проверяет управление сессиями чата"""
    # Добавляем контакт
    ui.add_contact("peer1", "127.0.0.1", 10001)
    
    # Начинаем чат
    ui.start_chat("peer1")
    assert ui.current_chat == "peer1"
    
    # Завершаем чат
    ui.stop_chat()
    assert ui.current_chat is None

def test_ui_cleanup(ui, data_dir):
    """Проверяет очистку пользовательского интерфейса"""
    # Добавляем контакт и сообщения
    ui.add_contact("peer1", "127.0.0.1", 10001)
    ui.send_message("peer1", "Test message")
    
    # Очищаем UI
    ui.cleanup()
    
    # Проверяем, что данные сохранены
    assert os.path.exists(os.path.join(data_dir, "chat_history"))
    new_ui = TerminalUI(data_dir)
    assert "peer1" in new_ui.contacts
    messages = new_ui.history.get_messages("peer1")
    assert len(messages) == 1 