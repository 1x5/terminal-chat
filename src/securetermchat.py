"""
Основной модуль приложения SecureTermChat

Реализует инициализацию и управление всеми компонентами приложения.
"""

import asyncio
import logging
import os
import sys
from typing import Optional

from src.config import Config
from src.network import P2PNetwork
from src.peer_discovery import PeerDiscovery
from src.onion_routing import OnionRoutingManager
from src.ui import TerminalUI

logger = logging.getLogger("securetermchat")

class SecureTermChat:
    """
    Основной класс приложения, управляющий всеми компонентами
    """
    
    def __init__(self, config_path: str = None):
        """
        Инициализирует приложение
        
        Args:
            config_path (str): Путь к файлу конфигурации
        """
        # Инициализируем конфигурацию
        self.config = Config(config_path)
        
        # Инициализируем компоненты
        self.peer_discovery = PeerDiscovery(self.config)
        self.network = P2PNetwork(self.config, self.peer_discovery)
        self.onion_manager = OnionRoutingManager(self.config)
        self.ui = TerminalUI(self.config.data_dir)
        
        # Устанавливаем обработчики событий
        self._setup_event_handlers()
        
    def _setup_event_handlers(self):
        """Настраивает обработчики событий между компонентами"""
        # Обработчики для UI
        self.ui.on_message_send = self._handle_message_send
        self.ui.on_contact_add = self._handle_contact_add
        self.ui.on_contact_remove = self._handle_contact_remove
        self.ui.on_quit = self.stop
        
        # Обработчики для сети
        self.network.on_message = self._handle_network_message
        self.network.on_peer_status = self._handle_peer_status
        
    async def start(self):
        """Запускает приложение"""
        try:
            # Загружаем конфигурацию
            await self.config.load()
            
            # Запускаем компоненты
            await self.network.start()
            await self.onion_manager.start()
            self.ui.start()
            
            logger.info("Приложение запущено")
            
        except Exception as e:
            logger.error(f"Ошибка при запуске приложения: {e}")
            await self.stop()
            raise e
            
    async def stop(self):
        """Останавливает приложение"""
        try:
            # Останавливаем компоненты в обратном порядке
            self.ui.stop()
            await self.onion_manager.stop()
            await self.network.stop()
            
            logger.info("Приложение остановлено")
            
        except Exception as e:
            logger.error(f"Ошибка при остановке приложения: {e}")
            raise e
            
    async def _handle_message_send(self, contact_id: str, message: str):
        """Обрабатывает отправку сообщения"""
        try:
            # Шифруем сообщение
            encrypted_message = await self.onion_manager.encrypt_message(message)
            
            # Отправляем через сеть
            await self.network.send_message(contact_id, encrypted_message)
            
            # Добавляем в историю
            self.ui.add_message(contact_id, message, True)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            self.ui.show_error(f"Не удалось отправить сообщение: {e}")
            
    async def _handle_network_message(self, peer_id: str, message: str):
        """Обрабатывает входящее сообщение"""
        try:
            # Расшифровываем сообщение
            decrypted_message = await self.onion_manager.decrypt_message(message)
            
            # Добавляем в историю
            self.ui.add_message(peer_id, decrypted_message, False)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке входящего сообщения: {e}")
            
    def _handle_contact_add(self, contact_id: str, contact_info: dict):
        """Обрабатывает добавление контакта"""
        try:
            # Добавляем контакт в UI
            self.ui.add_contact(contact_id, contact_info)
            
            # Сохраняем в конфигурации
            self.config.add_contact(contact_id, contact_info)
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении контакта: {e}")
            self.ui.show_error(f"Не удалось добавить контакт: {e}")
            
    def _handle_contact_remove(self, contact_id: str):
        """Обрабатывает удаление контакта"""
        try:
            # Удаляем контакт из UI
            self.ui.remove_contact(contact_id)
            
            # Удаляем из конфигурации
            self.config.remove_contact(contact_id)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении контакта: {e}")
            self.ui.show_error(f"Не удалось удалить контакт: {e}")
            
    def _handle_peer_status(self, peer_id: str, status: str):
        """Обрабатывает изменение статуса пира"""
        self.ui.update_peer_status(peer_id, status)

async def main():
    """Точка входа в приложение"""
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Создаем и запускаем приложение
    app = SecureTermChat()
    await app.start()
    
    try:
        # Ждем завершения
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        # Останавливаем приложение при Ctrl+C
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main()) 