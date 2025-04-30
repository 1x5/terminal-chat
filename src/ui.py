"""
Терминальный интерфейс для SecureTermChat

Реализует пользовательский интерфейс на базе консольного вывода.
"""

import asyncio
import logging
import time
import sys
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Callable
from blessed import Terminal
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from prompt_toolkit.patch_stdout import patch_stdout

from src.message_history import MessageHistory
from src.config import Config
from src.network import Network
from src.onion_routing import OnionRoutingManager

logger = logging.getLogger("securetermchat.ui")

class TerminalUI:
    """
    Реализует терминальный интерфейс для мессенджера
    """
    
    def __init__(self, config: Config, network: Network, onion_manager: OnionRoutingManager):
        """
        Инициализирует пользовательский интерфейс
        
        Args:
            config (Config): Конфигурация приложения
            network (Network): Сетевой модуль
            onion_manager (OnionRoutingManager): Менеджер луковой маршрутизации
        """
        # Сохраняем зависимости
        self.config = config
        self.network = network
        self.onion_manager = onion_manager
        
        # Директория для данных
        self.data_dir = config.data_dir
        
        # Инициализируем историю сообщений
        self.history = MessageHistory(self.data_dir)
        self.history.load()
        
        # Текущее состояние интерфейса
        self.current_contact = None
        self.is_running = False
        
        # Контакты
        self.contacts = {}  # contact_id -> contact_info
        
        # История сообщений
        self.messages = []
        
        # Настройка prompt_toolkit
        self.history_file = os.path.join(self.data_dir, "chat_history")
        self.session = PromptSession(
            history=FileHistory(self.history_file),
            style=Style.from_dict({
                'prompt': '#00aa00',
                'input': '#00aa00',
            })
        )
        
    async def start(self):
        """Запускает пользовательский интерфейс"""
        try:
            # Регистрируем обработчик сообщений
            self.network.set_message_handler(self.handle_message)
            
            self.is_running = True
            print("\nSecureTermChat v0.1.0")
            print("Введите /помощь для просмотра доступных команд\n")
            
            while self.is_running:
                try:
                    with patch_stdout():
                        command = await self.session.prompt_async(">>> ")
                        if command:
                            await self._handle_command(command.strip())
                except (EOFError, KeyboardInterrupt):
                    self.is_running = False
                    break
                except Exception as e:
                    print(f"\nОшибка: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Ошибка в UI: {e}")
            raise
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Очищает ресурсы UI"""
        self.is_running = False
        print("\nЗавершение работы...")
        logger.info("Пользовательский интерфейс остановлен")
        
    async def _handle_command(self, command: str):
        """Обрабатывает команды пользователя"""
        if command.startswith('/'):
            parts = command[1:].split()
            if not parts:
                return
                
            cmd = parts[0].lower()
            args = parts[1:]
            
            if cmd in ('help', 'помощь'):
                print("\nДоступные команды:")
                print("  /add <адрес>:<порт> - Добавить новый контакт")
                print("  /подключить <адрес> <порт> - Подключиться к пиру")
                print("  /отключить - Отключиться от текущего чата")
                print("  /контакты - Показать список контактов")
                print("  /статус - Показать статус сети")
                print("  /очистить - Очистить историю чата")
                print("  /выход - Выйти из приложения")
                
            elif cmd == 'add':
                if len(args) != 1:
                    print("Использование: /add <адрес>:<порт>")
                    return
                try:
                    address, port = args[0].split(':')
                    port = int(port)
                    peer_id = await self.network.connect(address, port)
                    if peer_id:
                        self.contacts[peer_id] = {
                            'address': address,
                            'port': port,
                            'added_at': datetime.now().isoformat()
                        }
                        print(f"\nКонтакт добавлен: {peer_id}")
                        # Устанавливаем добавленный контакт как текущий чат
                        self.current_contact = peer_id
                        print(f"Установлен текущий чат с {peer_id}")
                except ValueError:
                    print("Неверный формат. Используйте: /add адрес:порт")
                except Exception as e:
                    print(f"\nОшибка добавления контакта: {e}")
                    
            elif cmd in ('connect', 'подключить'):
                if len(args) != 2:
                    print("Использование: /подключить <адрес> <порт>")
                    return
                try:
                    address = args[0]
                    port = int(args[1])
                    peer_id = await self.network.connect(address, port)
                    print(f"\nПодключено к пиру {peer_id}")
                    self.current_contact = peer_id
                except Exception as e:
                    print(f"\nОшибка подключения: {e}")
                    
            elif cmd in ('disconnect', 'отключить'):
                if self.current_contact:
                    print(f"\nОтключено от {self.current_contact}")
                    self.current_contact = None
                else:
                    print("\nНет активного чата")
                    
            elif cmd in ('contacts', 'контакты'):
                if self.contacts:
                    print("\nКонтакты:")
                    for contact_id, info in self.contacts.items():
                        print(f"  {info['name']} ({contact_id})")
                else:
                    print("\nНет контактов")
                    
            elif cmd in ('status', 'статус'):
                peers = self.network.get_peer_ids()
                print(f"\nПодключенные пиры: {len(peers)}")
                for peer_id in peers:
                    print(f"  {peer_id}")
                    
            elif cmd in ('clear', 'очистить'):
                self.messages.clear()
                print("\nИстория чата очищена")
                
            elif cmd in ('quit', 'выход'):
                self.is_running = False
                
            else:
                print(f"\nНеизвестная команда: {cmd}")
                print("Введите /помощь для просмотра доступных команд")
                
        else:
            # Обычное сообщение
            if not self.current_contact:
                print("\nНет выбранного чата. Используйте /подключить <адрес> <порт>")
                return
                
            try:
                await self.network.send_message(self.current_contact, command)
                self.messages.append({
                    'timestamp': time.time(),
                    'sender': 'me',
                    'content': command
                })
                print(f"\nя: {command}")
            except Exception as e:
                print(f"\nОшибка отправки сообщения: {e}")
                
    async def handle_message(self, peer_id: str, message: str):
        """Обрабатывает входящие сообщения"""
        self.messages.append({
            'timestamp': time.time(),
            'sender': peer_id,
            'content': message
        })
        print(f"\n{peer_id}: {message}")
        
    async def handle_peer_connected(self, peer_id: str):
        """Обрабатывает подключение пиров"""
        if peer_id not in self.contacts:
            self.contacts[peer_id] = {
                'name': peer_id,
                'added_at': datetime.now().isoformat()
            }
            print(f"\nПодключен новый пир: {peer_id}")
            
    async def handle_peer_disconnected(self, peer_id: str):
        """Обрабатывает отключение пиров"""
        if peer_id in self.contacts:
            del self.contacts[peer_id]
            if peer_id == self.current_contact:
                self.current_contact = None
            print(f"\nПир отключен: {peer_id}")