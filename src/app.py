"""
Основной модуль приложения SecureTermChat

Координирует работу всех компонентов:
- Конфигурация
- P2P сеть
- Обнаружение пиров
- Луковая маршрутизация
- Пользовательский интерфейс
"""

import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime
import os
import json

from src.config import Config
from src.network import P2PNetwork
from src.peer_discovery import PeerDiscovery
from src.onion_routing import OnionRoutingManager
from src.ui import TerminalUI
from src.crypto import CryptoManager

logger = logging.getLogger("securetermchat.app")

class SecureTermChat:
    """Основной класс приложения"""
    
    def __init__(self):
        """Инициализация приложения"""
        # Инициализация компонентов
        self.config = Config()
        self.crypto = CryptoManager()
        self.peer_discovery = PeerDiscovery(self.config)
        self.network = P2PNetwork(self.config, self.peer_discovery)
        self.onion_routing = OnionRoutingManager(self.config, self.peer_discovery)
        self.ui = TerminalUI(self.config.data_dir)
        
        # Состояние приложения
        self.is_running = False
        self.contacts: Dict[str, Dict] = {}  # contact_id -> contact_info
        self.message_history: Dict[str, List[Dict]] = {}  # contact_id -> messages
        
        # Регистрируем обработчики событий
        self._register_event_handlers()
        
    def _register_event_handlers(self):
        """Регистрация обработчиков событий"""
        # Обработчики для UI
        self.ui.on_message_send = self._handle_message_send
        self.ui.on_contact_add = self._handle_contact_add
        self.ui.on_contact_remove = self._handle_contact_remove
        self.ui.on_quit = self.stop
        
        # Обработчики для сети
        self.network.on_message = self._handle_network_message
        self.network.on_peer_status = self._handle_peer_status
        
    async def start(self):
        """Запуск приложения"""
        logger.info("Запуск SecureTermChat...")
        self.is_running = True
        
        try:
            # Загружаем конфигурацию
            await self.config.load()
            
            # Запускаем компоненты
            await self.peer_discovery.start()
            await self.network.start()
            await self.onion_routing.start()
            self.ui.start()
            
            # Загружаем контакты и историю
            self._load_contacts()
            self._load_message_history()
            
            logger.info("Приложение запущено")
            
        except Exception as e:
            logger.error(f"Ошибка при запуске: {e}")
            await self.stop()
            raise
            
    async def stop(self):
        """Остановка приложения"""
        logger.info("Остановка SecureTermChat...")
        self.is_running = False
        
        # Останавливаем компоненты
        await self.onion_routing.stop()
        await self.peer_discovery.stop()
        await self.network.stop()
        
        # Сохраняем данные
        self._save_contacts()
        self._save_message_history()
        
        # Останавливаем UI
        self.ui.stop()
        
    async def _handle_message_send(self, recipient_id: str, message: str):
        """Обработка отправки сообщения"""
        try:
            # Шифруем сообщение
            encrypted_message = self.crypto.encrypt_message(message, recipient_id)
            
            # Формируем пакет сообщения
            message_packet = {
                'type': 'chat_message',
                'sender_id': self.network.node_id,
                'recipient_id': recipient_id,
                'content': encrypted_message,
                'timestamp': datetime.now().isoformat()
            }
            
            # Отправляем через луковую маршрутизацию
            success = await self.onion_routing.send_message(recipient_id, message_packet)
            
            if success:
                # Добавляем в историю
                self._add_message_to_history(recipient_id, {
                    'type': 'outgoing',
                    'content': message,
                    'timestamp': message_packet['timestamp']
                })
                
                # Обновляем UI
                self.ui.add_message(recipient_id, message, is_outgoing=True)
            else:
                self.ui.show_error("Не удалось отправить сообщение")
                
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            self.ui.show_error("Ошибка при отправке сообщения")
            
    async def _handle_network_message(self, message: Dict):
        """Обработка входящего сообщения"""
        try:
            if message['type'] != 'chat_message':
                return
                
            # Расшифровываем сообщение
            decrypted_content = self.crypto.decrypt_message(message['content'])
            
            # Добавляем в историю
            self._add_message_to_history(message['sender_id'], {
                'type': 'incoming',
                'content': decrypted_content,
                'timestamp': message['timestamp']
            })
            
            # Обновляем UI
            self.ui.add_message(message['sender_id'], decrypted_content, is_outgoing=False)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке входящего сообщения: {e}")
            
    def _handle_contact_add(self, contact_id: str, contact_info: Dict):
        """Обработка добавления контакта"""
        try:
            # Добавляем контакт
            self.contacts[contact_id] = contact_info
            
            # Сохраняем контакты
            self._save_contacts()
            
            # Обновляем UI
            self.ui.add_contact(contact_id, contact_info)
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении контакта: {e}")
            self.ui.show_error("Ошибка при добавлении контакта")
            
    def _handle_contact_remove(self, contact_id: str):
        """Обработка удаления контакта"""
        try:
            # Удаляем контакт
            if contact_id in self.contacts:
                del self.contacts[contact_id]
                
            # Сохраняем контакты
            self._save_contacts()
            
            # Обновляем UI
            self.ui.remove_contact(contact_id)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении контакта: {e}")
            self.ui.show_error("Ошибка при удалении контакта")
            
    def _handle_peer_status(self, peer_id: str, status: str):
        """Обработка изменения статуса пира"""
        self.ui.update_peer_status(peer_id, status)
        
    def _load_contacts(self):
        """Загрузка контактов"""
        try:
            contacts_file = os.path.join(self.config.data_dir, "contacts.json")
            if os.path.exists(contacts_file):
                with open(contacts_file, 'r') as f:
                    self.contacts = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке контактов: {e}")
            
    def _save_contacts(self):
        """Сохранение контактов"""
        try:
            contacts_file = os.path.join(self.config.data_dir, "contacts.json")
            with open(contacts_file, 'w') as f:
                json.dump(self.contacts, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении контактов: {e}")
            
    def _load_message_history(self):
        """Загрузка истории сообщений"""
        try:
            history_file = os.path.join(self.config.data_dir, "message_history.json")
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    self.message_history = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке истории сообщений: {e}")
            
    def _save_message_history(self):
        """Сохранение истории сообщений"""
        try:
            history_file = os.path.join(self.config.data_dir, "message_history.json")
            with open(history_file, 'w') as f:
                json.dump(self.message_history, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении истории сообщений: {e}")
            
    def _add_message_to_history(self, contact_id: str, message: Dict):
        """Добавление сообщения в историю"""
        if contact_id not in self.message_history:
            self.message_history[contact_id] = []
        self.message_history[contact_id].append(message)
        self._save_message_history() 