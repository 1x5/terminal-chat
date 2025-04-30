"""
Тесты для модуля истории сообщений
"""

import pytest
import os
import tempfile
import json
from src.message_history import MessageHistory

@pytest.fixture
def history_file():
    """Создает временный файл истории сообщений"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("""
        {
            "messages": {
                "peer1": [
                    {"sender": "peer1", "content": "Hello", "timestamp": 1000},
                    {"sender": "me", "content": "Hi", "timestamp": 1001}
                ],
                "peer2": [
                    {"sender": "peer2", "content": "Test", "timestamp": 1002}
                ]
            },
            "unread": {
                "peer1": 1,
                "peer2": 1
            }
        }
        """)
    yield f.name
    os.unlink(f.name)

def test_history_loading(history_file):
    """Проверяет загрузку истории сообщений"""
    history = MessageHistory(history_file)
    
    # Проверяем сообщения для peer1
    messages = history.get_messages("peer1")
    assert len(messages) == 2
    assert messages[0]["sender"] == "peer1"
    assert messages[0]["content"] == "Hello"
    assert messages[1]["sender"] == "me"
    assert messages[1]["content"] == "Hi"
    
    # Проверяем сообщения для peer2
    messages = history.get_messages("peer2")
    assert len(messages) == 1
    assert messages[0]["sender"] == "peer2"
    assert messages[0]["content"] == "Test"
    
    # Проверяем счетчики непрочитанных сообщений
    assert history.get_unread_count("peer1") == 1
    assert history.get_unread_count("peer2") == 1

def test_history_saving(history_file):
    """Проверяет сохранение истории сообщений"""
    history = MessageHistory(history_file)
    
    # Добавляем новое сообщение
    history.add_message("peer1", "me", "New message")
    
    # Сохраняем историю
    history.save()
    
    # Загружаем историю заново
    new_history = MessageHistory(history_file)
    
    # Проверяем, что сообщение сохранено
    messages = new_history.get_messages("peer1")
    assert len(messages) == 3
    assert messages[2]["sender"] == "me"
    assert messages[2]["content"] == "New message"

def test_unread_count_management(history_file):
    """Проверяет управление счетчиками непрочитанных сообщений"""
    history = MessageHistory(history_file)
    
    # Проверяем начальные значения
    assert history.get_unread_count("peer1") == 1
    assert history.get_unread_count("peer2") == 1
    
    # Отмечаем сообщения как прочитанные
    history.mark_as_read("peer1")
    assert history.get_unread_count("peer1") == 0
    
    # Добавляем новое сообщение
    history.add_message("peer1", "peer1", "New message")
    assert history.get_unread_count("peer1") == 1

def test_message_retrieval(history_file):
    """Проверяет получение сообщений"""
    history = MessageHistory(history_file)
    
    # Получаем все сообщения
    messages = history.get_messages("peer1")
    assert len(messages) == 2
    
    # Получаем сообщения с ограничением
    messages = history.get_messages("peer1", limit=1)
    assert len(messages) == 1
    assert messages[0]["content"] == "Hi"
    
    # Получаем сообщения с временным диапазоном
    messages = history.get_messages("peer1", start_time=1000, end_time=1001)
    assert len(messages) == 2

def test_history_cleanup(history_file):
    """Проверяет очистку истории сообщений"""
    history = MessageHistory(history_file)
    
    # Очищаем историю для peer1
    history.clear_history("peer1")
    
    # Проверяем, что история очищена
    messages = history.get_messages("peer1")
    assert len(messages) == 0
    assert history.get_unread_count("peer1") == 0
    
    # Проверяем, что история для peer2 не затронута
    messages = history.get_messages("peer2")
    assert len(messages) == 1
    assert history.get_unread_count("peer2") == 1 