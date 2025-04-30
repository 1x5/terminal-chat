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
        
        # Инициализируем терминал
        self.term = Terminal()
        
        # Директория для данных
        self.data_dir = config.data_dir
        
        # Инициализируем историю сообщений
        self.history = MessageHistory(self.data_dir)
        self.history.load()
        
        # Текущее состояние интерфейса
        self.current_contact = None
        self.input_buffer = ""
        self.input_cursor = 0
        self.command_mode = False
        self.is_running = False
        self.view_mode = "chat"  # chat, contacts, status
        
        # Контакты
        self.contacts = {}  # contact_id -> contact_info
        
        # Статусы пиров
        self.peer_statuses = {}  # peer_id -> status
        
        # Обработчики событий
        self.on_message_send: Optional[Callable] = None
        self.on_contact_add: Optional[Callable] = None
        self.on_contact_remove: Optional[Callable] = None
        self.on_quit: Optional[Callable] = None
        
        self.history_file = os.path.join(self.data_dir, "chat_history")
        self.session = PromptSession(
            history=FileHistory(self.history_file),
            style=Style.from_dict({
                'prompt': 'ansicyan bold',
                'input': 'ansigreen',
            })
        )
        
        self.messages = []
        self.terminal = None
        self.input_task = None
        
    async def start(self):
        """Запускает пользовательский интерфейс"""
        try:
            self.is_running = True
            self.terminal = Terminal()
            
            # Запускаем обработку ввода в отдельной задаче
            self.input_task = asyncio.create_task(self._process_input())
            
            # Основной цикл обновления UI
            while self.is_running:
                self._draw()
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Ошибка в UI: {e}")
            raise
        finally:
            self.stop()

    def stop(self):
        """Останавливает пользовательский интерфейс"""
        self.is_running = False
        print(self.term.normal + self.term.clear)
        logger.info("Пользовательский интерфейс остановлен")
        
    async def _run(self):
        """Основной цикл пользовательского интерфейса"""
        try:
            # Очищаем экран и скрываем курсор
            print(self.term.clear + self.term.hide_cursor)
            
            # Запускаем обработку ввода
            input_task = asyncio.create_task(self._process_input())
            
            # Запускаем обновление UI
            ui_update_task = asyncio.create_task(self._update_ui())
            
            # Ждем, пока пользовательский интерфейс не будет остановлен
            while self.is_running:
                await asyncio.sleep(0.1)
                
            # Отменяем задачи
            input_task.cancel()
            ui_update_task.cancel()
            
            # Восстанавливаем настройки терминала
            print(self.term.normal + self.term.clear + self.term.show_cursor)
            
        except Exception as e:
            # При ошибке восстанавливаем настройки терминала
            print(self.term.normal + self.term.clear + self.term.show_cursor)
            logger.error(f"Ошибка в работе пользовательского интерфейса: {e}")
            raise e
            
    def _draw(self):
        """Отрисовывает интерфейс"""
        # Очищаем экран
        print(self.terminal.clear)
        
        # Отрисовываем заголовок
        print(self.terminal.move(0, 0) + self.terminal.bold + "SecureTermChat" + self.terminal.normal)
        
        # Отрисовываем сообщения
        y = 2
        for msg in self.messages[-10:]:  # Показываем последние 10 сообщений
            print(self.terminal.move(y, 0) + msg)
            y += 1
            
        # Отрисовываем строку ввода
        print(self.terminal.move(self.terminal.height - 2, 0) + "> " + self.input_buffer)
        
        # Перемещаем курсор в конец строки ввода
        print(self.terminal.move(self.terminal.height - 2, len(self.input_buffer) + 2))

    def _draw_header(self):
        """Отрисовывает заголовок интерфейса"""
        # Очищаем верхнюю строку
        print(self.term.move(0, 0) + self.term.clear_eol)
        
        # Заголовок
        print(self.term.move(0, 0) + self.term.green + "SecureTermChat" + self.term.normal)
        
        # Версия и количество контактов
        print(self.term.move(0, 20) + self.term.blue + 
              f"Версия: 0.1.0  |  Контактов: {len(self.contacts)}" + 
              self.term.normal)
              
        # Текущий режим просмотра
        mode_colors = {
            "chat": self.term.green,
            "contacts": self.term.yellow,
            "status": self.term.cyan
        }
        print(self.term.move(0, 60) + mode_colors.get(self.view_mode, self.term.normal) + 
              f"Режим: {self.view_mode}" + self.term.normal)

    def _draw_status(self):
        """Отрисовывает статусную строку"""
        # Очищаем статусную строку
        print(self.term.move(self.term.height - 1, 0) + self.term.clear_eol)
        
        # Текущий чат
        chat_status = f"Чат с: {self.current_contact}" if self.current_contact else "Чат не выбран"
        print(self.term.move(self.term.height - 1, 0) + self.term.cyan + chat_status + self.term.normal)
        
        # Количество активных соединений
        active_peers = sum(1 for s in self.peer_statuses.values() if s == "connected")
        print(self.term.move(self.term.height - 1, 30) + self.term.green + 
              f"Активных соединений: {active_peers}" + self.term.normal)
              
        # Время
        current_time = datetime.now().strftime("%H:%M:%S")
        print(self.term.move(self.term.height - 1, self.term.width - 10) + 
              self.term.blue + current_time + self.term.normal)

    def _draw_chat(self):
        """Отрисовывает окно чата"""
        if not self.current_contact:
            return
            
        # Очищаем область чата
        for i in range(2, self.term.height - 3):
            print(self.term.move(i, 0) + self.term.clear_eol)
            
        # Отображаем последние сообщения
        messages = self.history.get_messages(self.current_contact, limit=10)
        for i, msg in enumerate(messages):
            # Время сообщения
            time_str = datetime.fromisoformat(msg['timestamp']).strftime("%H:%M")
            
            # Стили для разных типов сообщений
            if msg["type"] == "outgoing":
                sender = "Вы"
                sender_style = self.term.green
                content_style = self.term.green
            else:
                sender = self.current_contact
                sender_style = self.term.cyan
                content_style = self.term.normal
                
            # Отображаем сообщение
            print(self.term.move(i + 2, 0) + sender_style + f"{sender} [{time_str}]" + self.term.normal)
            print(self.term.move(i + 2, 12) + content_style + msg["content"])
            
        # Отмечаем сообщения как прочитанные
        self.history.mark_as_read(self.current_contact)

    def _draw_contacts(self):
        """Отрисовывает список контактов"""
        # Очищаем область контактов
        for i in range(2, self.term.height - 3):
            print(self.term.move(i, 0) + self.term.clear_eol)
            
        # Отображаем контакты
        for i, (contact_id, info) in enumerate(self.contacts.items()):
            # Статус контакта
            status = self.peer_statuses.get(contact_id, "offline")
            status_color = self.term.green if status == "connected" else self.term.red
            
            # Выделяем текущий контакт
            if contact_id == self.current_contact:
                contact_style = self.term.bold
            else:
                contact_style = self.term.normal
                
            # Количество непрочитанных сообщений
            unread = self.history.get_unread_count(contact_id)
            unread_str = f" ({unread})" if unread > 0 else ""
                
            # Отображаем контакт
            print(self.term.move(i + 2, 0) + contact_style + 
                  f"{info['name']} ({contact_id}) - {status_color}{status}{self.term.normal}{unread_str}")

    def _draw_status_view(self):
        """Отрисовывает подробный статус системы"""
        # Очищаем область статуса
        for i in range(2, self.term.height - 3):
            print(self.term.move(i, 0) + self.term.clear_eol)
            
        # Отображаем информацию о системе
        status_info = [
            f"Всего контактов: {len(self.contacts)}",
            f"Активных соединений: {sum(1 for s in self.peer_statuses.values() if s == 'connected')}",
            f"Текущий чат: {self.current_contact if self.current_contact else 'нет'}",
            f"Режим просмотра: {self.view_mode}",
            f"Размер терминала: {self.term.width}x{self.term.height}",
            f"Время работы: {time.strftime('%H:%M:%S')}",
            f"Всего сообщений: {sum(len(msgs) for msgs in self.history.messages.values())}",
            f"Непрочитанных: {sum(self.history.get_unread_count(cid) for cid in self.contacts)}"
        ]
        
        for i, line in enumerate(status_info):
            print(self.term.move(i + 2, 0) + self.term.blue + line + self.term.normal)

    def _draw_input(self):
        """Отрисовывает строку ввода"""
        print(self.term.move(self.term.height - 3, 0) + self.term.clear_eol)
        
        # Префикс в зависимости от режима
        if self.command_mode:
            prefix = self.term.yellow + "/" + self.term.normal
        else:
            prefix = "> "
            
        print(self.term.move(self.term.height - 3, 0) + prefix + self.input_buffer, end='')
        print(self.term.move(self.term.height - 3, len(prefix) + self.input_cursor) + 
              self.term.yellow + "_" + self.term.normal)
        
    async def _process_input(self):
        """Обрабатывает пользовательский ввод"""
        try:
            while self.is_running:
                with self.term.cbreak():
                    key = self.term.inkey(timeout=0.1)
                    
                    if not key:
                        continue
                        
                    if key.name == 'KEY_ENTER':
                        # Enter - отправка сообщения или выполнение команды
                        await self._handle_input()
                    elif key == '/' and not self.input_buffer:
                        # Слэш в начале ввода - режим команды
                        self.command_mode = True
                        self.input_buffer = "/"
                        self.input_cursor = 1
                    elif key.name == 'KEY_BACKSPACE':
                        # Backspace - удаление символа
                        if self.input_cursor > 0:
                            self.input_buffer = self.input_buffer[:self.input_cursor-1] + self.input_buffer[self.input_cursor:]
                            self.input_cursor -= 1
                    elif key.name == 'KEY_LEFT':
                        # Стрелка влево - перемещение курсора
                        if self.input_cursor > 0:
                            self.input_cursor -= 1
                    elif key.name == 'KEY_RIGHT':
                        # Стрелка вправо - перемещение курсора
                        if self.input_cursor < len(self.input_buffer):
                            self.input_cursor += 1
                    elif key.name == 'KEY_TAB':
                        # Tab - переключение режимов просмотра
                        modes = ["chat", "contacts", "status"]
                        current_index = modes.index(self.view_mode)
                        self.view_mode = modes[(current_index + 1) % len(modes)]
                    elif key.is_sequence:
                        continue
                    else:
                        # Печатный символ - добавление в буфер
                        self.input_buffer = self.input_buffer[:self.input_cursor] + key + self.input_buffer[self.input_cursor:]
                        self.input_cursor += 1
                    
                    # Обновляем отображение ввода
                    self._draw_input()
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ошибка в обработке ввода: {e}")
            self.is_running = False
            
    async def _update_ui(self):
        """Периодически обновляет пользовательский интерфейс"""
        try:
            while self.is_running:
                # Обновляем все элементы интерфейса
                self._draw_header()
                self._draw_status()
                
                # Отображаем текущий режим
                if self.view_mode == "chat":
                    self._draw_chat()
                elif self.view_mode == "contacts":
                    self._draw_contacts()
                else:  # status
                    self._draw_status_view()
                    
                self._draw_input()
                
                # Ждем перед следующим обновлением
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ошибка в обновлении UI: {e}")
            self.is_running = False

    async def _handle_input(self):
        """Обрабатывает введенную команду или сообщение"""
        if not self.input_buffer.strip():
            return
            
        if self.command_mode:
            # Убираем начальный слэш и разбиваем на команду и аргументы
            command = self.input_buffer.lstrip('/')
            parts = command.split()
            if not parts:
                return
                
            cmd = parts[0].lower()
            args = parts[1:]
            
            try:
                # Обрабатываем команды
                if cmd == "help":
                    self._show_help()
                elif cmd == "add":
                    self._add_contact(args)
                elif cmd == "connect":
                    self._connect_contact(args)
                elif cmd == "disconnect":
                    self._disconnect_contact()
                elif cmd == "contacts":
                    self.view_mode = "contacts"
                    self.show_message("Переключено в режим просмотра контактов")
                elif cmd == "status":
                    self.view_mode = "status"
                    self.show_message("Переключено в режим просмотра статуса")
                elif cmd == "chat":
                    self.view_mode = "chat"
                    self.show_message("Переключено в режим чата")
                elif cmd == "clear":
                    self._clear_history(args)
                elif cmd == "quit" or cmd == "exit":
                    self.is_running = False
                else:
                    self.show_error(f"Неизвестная команда: {cmd}")
            except Exception as e:
                self.show_error(f"Ошибка при выполнении команды: {e}")
        else:
            # Отправляем сообщение
            await self._send_message(self.input_buffer)
            
        # Очищаем буфер ввода
        self.input_buffer = ""
        self.input_cursor = 0
        self.command_mode = False

    def _add_contact(self, args):
        """Добавляет новый контакт"""
        if len(args) < 2:
            self.show_error("Использование: /add <id> <name>")
            return
            
        contact_id = args[0]
        contact_name = " ".join(args[1:])  # Имя может содержать пробелы
        
        try:
            # Добавляем контакт в список
            self.contacts[contact_id] = {
                'name': contact_name,
                'added_at': datetime.now().isoformat()
            }
            
            # Вызываем обработчик если он установлен
            if self.on_contact_add:
                asyncio.create_task(self.on_contact_add(contact_id, self.contacts[contact_id]))
            
            # Показываем сообщение об успехе
            self.show_message(f"Контакт {contact_name} ({contact_id}) успешно добавлен")
            
        except Exception as e:
            self.show_error(f"Ошибка при добавлении контакта: {e}")

    def _connect_contact(self, args):
        """Подключается к контакту"""
        if not args:
            self.show_error("Использование: /connect <id>")
            return
            
        contact_id = args[0]
        if contact_id not in self.contacts:
            self.show_error(f"Контакт {contact_id} не найден")
            return
            
        self.current_contact = contact_id
        self.view_mode = "chat"
        self.show_message(f"Подключено к чату с {self.contacts[contact_id]['name']}")

    def _disconnect_contact(self):
        """Отключается от текущего контакта"""
        if not self.current_contact:
            self.show_error("Нет активного чата")
            return
            
        contact_name = self.contacts[self.current_contact]['name']
        self.current_contact = None
        self.show_message(f"Отключено от чата с {contact_name}")

    def _clear_history(self, args):
        """Очищает историю сообщений"""
        try:
            if args:
                contact_id = args[0]
                if contact_id in self.contacts:
                    self.history.clear_history(contact_id)
                    self.show_message(f"История сообщений для {contact_id} очищена")
                else:
                    self.show_error(f"Контакт {contact_id} не найден")
            else:
                self.history.clear_all_history()
                self.show_message("Вся история сообщений очищена")
        except Exception as e:
            self.show_error(f"Ошибка при очистке истории: {e}")

    async def _send_message(self, text: str):
        """Отправляет сообщение"""
        if not text.strip():
            return
            
        if not self.current_contact:
            self.show_error("Сначала выберите контакт (/connect <id>)")
            return
            
        try:
            if self.on_message_send:
                await self.on_message_send(self.current_contact, text)
                
            # Добавляем сообщение в историю
            self.add_message(self.current_contact, text, True)
            
        except Exception as e:
            self.show_error(f"Ошибка при отправке сообщения: {e}")

    def _show_help(self):
        """Показывает справку по командам"""
        self.view_mode = "help"
        help_text = [
            "Доступные команды:",
            "/help - Показать эту справку",
            "/add <id> <name> - Добавить новый контакт",
            "/contacts - Показать список контактов",
            "/connect <id> - Начать чат с контактом",
            "/disconnect - Закрыть текущий чат",
            "/status - Показать статус системы",
            "/chat - Вернуться к чату",
            "/clear [id] - Очистить историю сообщений",
            "/exit - Выйти из приложения",
            "",
            "Горячие клавиши:",
            "Tab - Переключение режимов просмотра",
            "Ctrl+C - Выход из приложения"
        ]
        
        # Очищаем область вывода
        for i in range(2, self.term.height - 3):
            print(self.term.move(i, 0) + self.term.clear_eol)
            
        # Выводим справку
        for i, line in enumerate(help_text):
            print(self.term.move(i + 2, 0) + line)

    def add_message(self, contact_id: str, content: str, is_outgoing: bool):
        """Добавляет сообщение в историю"""
        self.history.add_message(contact_id, content, is_outgoing)

    def add_contact(self, contact_id: str, contact_info: Dict):
        """Добавляет контакт"""
        self.contacts[contact_id] = contact_info

    def remove_contact(self, contact_id: str):
        """Удаляет контакт"""
        if contact_id in self.contacts:
            del self.contacts[contact_id]
        if contact_id == self.current_contact:
            self.current_contact = None

    def update_peer_status(self, peer_id: str, status: str):
        """Обновляет статус пира"""
        self.peer_statuses[peer_id] = status

    def show_error(self, message: str):
        """Показывает сообщение об ошибке"""
        print(self.term.move(self.term.height - 2, 0) + self.term.red + message + self.term.normal)

    def show_message(self, message: str):
        """Показывает информационное сообщение"""
        print(self.term.move(self.term.height - 2, 0) + 
              self.term.clear_eol + 
              self.term.green + message + self.term.normal) 