"""
Модуль для работы с историей сообщений

Реализует сохранение, загрузку и управление историей сообщений.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("securetermchat.history")

class MessageHistory:
    """
    Класс для управления историей сообщений
    """
    
    def __init__(self, data_dir: str):
        """
        Инициализирует менеджер истории сообщений
        
        Args:
            data_dir (str): Директория для хранения истории
        """
        self.data_dir = data_dir
        self.history_file = os.path.join(data_dir, "message_history.json")
        self.max_history_size = 1000  # Максимальное количество сообщений на контакт
        
        # История сообщений
        self.messages: Dict[str, List[Dict]] = {}  # contact_id -> list of messages
        
        # Создаем директорию, если не существует
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
    def load(self) -> bool:
        """
        Загружает историю сообщений из файла
        
        Returns:
            bool: True если загрузка успешна, False в случае ошибки
        """
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.messages = json.load(f)
                logger.info(f"История сообщений загружена из {self.history_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при загрузке истории сообщений: {e}")
            return False
            
    def save(self) -> bool:
        """
        Сохраняет историю сообщений в файл
        
        Returns:
            bool: True если сохранение успешно, False в случае ошибки
        """
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
            logger.info(f"История сообщений сохранена в {self.history_file}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении истории сообщений: {e}")
            return False
            
    def add_message(self, contact_id: str, content: str, is_outgoing: bool) -> None:
        """
        Добавляет сообщение в историю
        
        Args:
            contact_id (str): ID контакта
            content (str): Текст сообщения
            is_outgoing (bool): True если сообщение исходящее, False если входящее
        """
        if contact_id not in self.messages:
            self.messages[contact_id] = []
            
        message = {
            'type': 'outgoing' if is_outgoing else 'incoming',
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        self.messages[contact_id].append(message)
        
        # Ограничиваем размер истории
        if len(self.messages[contact_id]) > self.max_history_size:
            self.messages[contact_id] = self.messages[contact_id][-self.max_history_size:]
            
        # Сохраняем изменения
        self.save()
        
    def get_messages(self, contact_id: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Получает историю сообщений для контакта
        
        Args:
            contact_id (str): ID контакта
            limit (Optional[int]): Максимальное количество сообщений
            
        Returns:
            List[Dict]: Список сообщений
        """
        messages = self.messages.get(contact_id, [])
        if limit:
            messages = messages[-limit:]
        return messages
        
    def clear_history(self, contact_id: str) -> None:
        """
        Очищает историю сообщений для контакта
        
        Args:
            contact_id (str): ID контакта
        """
        if contact_id in self.messages:
            del self.messages[contact_id]
            self.save()
            
    def clear_all_history(self) -> None:
        """
        Очищает всю историю сообщений
        """
        self.messages.clear()
        self.save()
        
    def get_contacts_with_history(self) -> List[str]:
        """
        Получает список контактов, у которых есть история сообщений
        
        Returns:
            List[str]: Список ID контактов
        """
        return list(self.messages.keys())
        
    def get_last_message(self, contact_id: str) -> Optional[Dict]:
        """
        Получает последнее сообщение для контакта
        
        Args:
            contact_id (str): ID контакта
            
        Returns:
            Optional[Dict]: Последнее сообщение или None, если история пуста
        """
        messages = self.messages.get(contact_id, [])
        return messages[-1] if messages else None
        
    def get_unread_count(self, contact_id: str) -> int:
        """
        Получает количество непрочитанных сообщений для контакта
        
        Args:
            contact_id (str): ID контакта
            
        Returns:
            int: Количество непрочитанных сообщений
        """
        messages = self.messages.get(contact_id, [])
        return sum(1 for msg in messages if msg['type'] == 'incoming' and not msg.get('read', False))
        
    def mark_as_read(self, contact_id: str) -> None:
        """
        Отмечает все сообщения контакта как прочитанные
        
        Args:
            contact_id (str): ID контакта
        """
        if contact_id in self.messages:
            for msg in self.messages[contact_id]:
                if msg['type'] == 'incoming':
                    msg['read'] = True
            self.save() 