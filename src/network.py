"""
Сетевой модуль для P2P-соединений SecureTermChat

Реализует установку и поддержание P2P-соединений между узлами,
обеспечивает надежную передачу сообщений.
"""

import asyncio
import logging
import json
import socket
import time
import random
from typing import Dict, List, Any, Optional, Callable, Set, Tuple, Awaitable
import websockets
from websockets.exceptions import (
    WebSocketException, ConnectionClosed, ConnectionClosedError,
    ConnectionClosedOK, InvalidStatusCode, InvalidMessage
)
from websockets.client import WebSocketClientProtocol
from websockets.server import WebSocketServerProtocol
from datetime import datetime

from src.p2p_connection import NodeConnection
from src.protocol import (
    Message, MessageType, HandshakeMessage, OnionMessage,
    PingMessage, PongMessage, ErrorMessage, RouteUpdateMessage,
    NodeInfoMessage
)
from src.crypto import CryptoManager
from src.security import SecurityManager
from .e2e_encryption import E2EEncryption, E2EEncryptionError, KeyLoadError
from .signatures import MessageSigner, SignatureVerificationError
from .reputation import ReputationManager, ReputationEvent
from .nat_traversal import NATTraversal
from .config import Config

logger = logging.getLogger("securetermchat.network")

class NetworkError(Exception):
    """Базовый класс для сетевых ошибок"""
    pass

class ConnectionError(NetworkError):
    """Ошибка установки соединения"""
    pass

class MessageError(NetworkError):
    """Ошибка обработки сообщения"""
    pass

class P2PConnection:
    """Представляет P2P соединение с удаленным узлом"""
    
    def __init__(self, websocket: WebSocketServerProtocol, peer_id: str):
        """Инициализирует P2P соединение
        
        Args:
            websocket: WebSocket соединение
            peer_id: Идентификатор удаленного узла
        """
        self.websocket = websocket
        self.peer_id = peer_id
        self.logger = logging.getLogger("securetermchat.network.connection")
        
    @property
    def is_connected(self) -> bool:
        """Возвращает статус соединения"""
        return self.websocket.open
        
    async def send_message(self, message: str):
        """Отправляет сообщение
        
        Args:
            message: Сообщение для отправки
            
        Raises:
            ConnectionError: Если соединение закрыто
        """
        if not self.is_connected:
            raise ConnectionError("Соединение закрыто")
            
        try:
            await self.websocket.send(message)
        except Exception as e:
            self.logger.error(f"Ошибка при отправке сообщения: {e}")
            raise ConnectionError(f"Не удалось отправить сообщение: {e}")
            
    async def close(self):
        """Закрывает соединение"""
        if self.is_connected:
            await self.websocket.close()
            self.logger.info(f"Соединение с {self.peer_id} закрыто")

class Network:
    """Сетевой модуль для P2P соединений"""
    
    def __init__(self, config: Config, security_manager: SecurityManager, port: int = 8765):
        """
        Инициализирует сетевой модуль
        
        Args:
            config (Config): Конфигурация приложения
            security_manager (SecurityManager): Менеджер безопасности
            port (int): Порт для прослушивания (по умолчанию 8765)
        """
        self.config = config
        self.security = security_manager
        self.port = port
        self.connections = {}  # peer_id -> connection
        self._message_handler = None
        self.server = None
        self.is_running = False
        self.connection_timeout = 30  # seconds
        self.e2e = E2EEncryption()
        
        # Настраиваем логирование
        self.logger = logging.getLogger("securetermchat.network")
        
    async def start(self):
        """Запускает сетевой модуль"""
        if self.is_running:
            return
            
        try:
            # Инициализируем E2E шифрование
            try:
                self.e2e.load_keys()
            except KeyLoadError:
                self.logger.info("Генерация новых E2E ключей...")
                self.e2e.generate_keys()
            
            # Запускаем websocket сервер
            self.logger.info(f"Запуск WebSocket сервера на порту {self.port}")
            self.server = await websockets.serve(
                self._handle_connection,
                "0.0.0.0",  # Слушаем все интерфейсы
                self.port,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            self.is_running = True
            self.logger.info(f"Сетевой модуль запущен на порту {self.port}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при запуске сетевого модуля: {e}", exc_info=True)
            raise NetworkError(f"Не удалось запустить сетевой модуль: {e}")
            
    async def _handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """Обрабатывает входящее соединение"""
        peer_id = None
        try:
            # Валидируем соединение
            peer_id = await self.security.validate_connection(websocket)
            if not peer_id:
                self.logger.warning("Соединение не прошло валидацию")
                await websocket.close()
                return

            # Добавляем соединение
            self.connections[peer_id] = P2PConnection(websocket, peer_id)
            self.logger.info(f"Новое соединение установлено с {peer_id}")

            # Обмениваемся ключами E2E шифрования
            try:
                # Отправляем наш публичный ключ
                public_key = self.e2e.get_public_key()
                await websocket.send(f"KEY:{public_key}")
                
                # Получаем публичный ключ пира
                peer_key_msg = await websocket.recv()
                if peer_key_msg.startswith("KEY:"):
                    peer_key = peer_key_msg[4:]
                    self.e2e.add_peer_key(peer_id, peer_key)
                    self.logger.info(f"Ключи E2E обменяны с {peer_id}")
            except Exception as e:
                self.logger.error(f"Ошибка при обмене ключами с {peer_id}: {e}")
                await websocket.close()
                return

            # Запускаем обработку сообщений в фоновом режиме
            message_task = asyncio.create_task(self._handle_messages(peer_id, websocket))
            
            # Ждем завершения обработки сообщений
            try:
                await message_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            self.logger.error(f"Ошибка при обработке соединения: {e}", exc_info=True)
            if peer_id and peer_id in self.connections:
                del self.connections[peer_id]
            await websocket.close()

    async def connect(self, host: str, port: int) -> Optional[str]:
        """Устанавливает соединение с удаленным узлом"""
        websocket = None
        peer_id = None
        try:
            self.logger.info(f"Попытка подключения к {host}:{port}")
            
            # Устанавливаем WebSocket соединение
            uri = f"ws://{host}:{port}"
            websocket = await websockets.connect(uri)
            
            # Валидируем соединение
            peer_id = await self.security.validate_outgoing_connection(websocket)
            if not peer_id:
                await websocket.close()
                raise ConnectionError("Соединение отклонено по соображениям безопасности")

            # Добавляем соединение
            self.connections[peer_id] = P2PConnection(websocket, peer_id)
            self.logger.info(f"Соединение установлено с {peer_id}")
            
            # Обмениваемся ключами E2E шифрования
            try:
                # Получаем публичный ключ пира
                peer_key_msg = await websocket.recv()
                if peer_key_msg.startswith("KEY:"):
                    peer_key = peer_key_msg[4:]
                    self.e2e.add_peer_key(peer_id, peer_key)
                    
                    # Отправляем наш публичный ключ
                    public_key = self.e2e.get_public_key()
                    await websocket.send(f"KEY:{public_key}")
                    
                    self.logger.info(f"Ключи E2E обменяны с {peer_id}")
            except Exception as e:
                self.logger.error(f"Ошибка при обмене ключами с {peer_id}: {e}")
                await websocket.close()
                raise ConnectionError(f"Ошибка при обмене ключами: {e}")
            
            # Запускаем обработку сообщений в фоновом режиме
            asyncio.create_task(self._handle_messages(peer_id, websocket))
            
            return peer_id

        except Exception as e:
            if websocket:
                await websocket.close()
            if peer_id and peer_id in self.connections:
                del self.connections[peer_id]
            self.logger.error(f"Ошибка подключения к {host}:{port}: {e}")
            raise ConnectionError(f"Не удалось установить соединение: {str(e)}")

    async def _handle_messages(self, peer_id: str, websocket):
        """Обрабатывает входящие сообщения от пира"""
        try:
            while True:
                try:
                    message = await websocket.recv()
                    
                    # Пропускаем сообщения обмена ключами
                    if message.startswith("KEY:"):
                        continue
                        
                    # Пробуем расшифровать сообщение
                    try:
                        decrypted = self.e2e.decrypt_message(peer_id, message)
                        message = decrypted
                    except Exception as e:
                        self.logger.error(f"Ошибка расшифровки сообщения от {peer_id}: {e}")
                        continue
                        
                    # Вызываем обработчик сообщений
                    if self._message_handler:
                        await self._message_handler(peer_id, message)
                        self.logger.debug(f"Получено сообщение от {peer_id}: {message}")
                        
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    self.logger.error(f"Ошибка при обработке сообщения от {peer_id}: {e}")
                    continue
                    
        finally:
            if peer_id in self.connections:
                del self.connections[peer_id]
                self.logger.info(f"Соединение с {peer_id} удалено")
            
    async def send_message(self, peer_id: str, message: str):
        """Отправляет сообщение указанному пиру
        
        Args:
            peer_id: Идентификатор пира
            message: Сообщение для отправки
            
        Raises:
            ConnectionError: Если соединение не установлено
        """
        if peer_id not in self.connections:
            raise ConnectionError(f"Нет соединения с {peer_id}")
            
        try:
            # Шифруем сообщение
            encrypted = self.e2e.encrypt_message(peer_id, message)
            
            # Отправляем сообщение
            connection = self.connections[peer_id]
            await connection.send_message(encrypted)
        except E2EEncryptionError as e:
            self.logger.error(f"Ошибка шифрования сообщения для {peer_id}: {e}")
            raise ConnectionError(f"Не удалось зашифровать сообщение: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка при отправке сообщения {peer_id}: {e}")
            raise
            
    async def stop(self):
        """Останавливает сетевой модуль"""
        if not self.is_running:
            return
            
        # Закрываем все соединения
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()
        
        # Останавливаем сервер
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        self.is_running = False
        self.logger.info("Сетевой модуль остановлен")
        
    async def _handle_message(self, peer_id: str, message: str):
        """Обрабатывает входящее сообщение
        
        Args:
            peer_id: Идентификатор отправителя
            message: Полученное сообщение
        """
        try:
            # Обновляем репутацию пира
            await self.security.update_reputation(peer_id, True)
            
            try:
                # Пробуем расшифровать сообщение если оно зашифровано
                decrypted = self.e2e.decrypt_message(peer_id, message)
                message = decrypted
            except E2EEncryptionError:
                # Если не удалось расшифровать, используем как есть
                pass
            
            # Вызываем обработчик сообщений если он установлен
            if self._message_handler:
                await self._message_handler(peer_id, message)
            
            self.logger.debug(f"Получено сообщение от {peer_id}: {message}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при обработке сообщения от {peer_id}: {e}")
            
    @property
    def active_connections(self) -> int:
        """Возвращает количество активных соединений"""
        return len(self.connections)
        
    def get_peer_ids(self) -> List[str]:
        """Возвращает список идентификаторов подключенных пиров"""
        return list(self.connections.keys())

    def get_active_connections(self) -> List[Dict]:
        """
        Возвращает информацию об активных соединениях
        
        Returns:
            List[Dict]: Список с информацией о каждом соединении
        """
        connections_info = []
        
        for connection in self.connections:
            remote_address = connection.remote_address
            address = f"{remote_address[0]}:{remote_address[1]}" if remote_address else "unknown"
            
            connections_info.append({
                "remote_address": address,
                "connected_since": connection.connected_since,
                "connected": connection.connected,
                "messages_sent": connection.messages_sent,
                "messages_received": connection.messages_received
            })
            
        return connections_info
        
    def get_connection_count(self) -> int:
        """
        Возвращает количество активных соединений
        
        Returns:
            int: Количество подключенных узлов
        """
        return len(self.connections)

    def get_peer_reputation(self, peer_id: str) -> float:
        """Получить репутацию пира"""
        return self.reputation.get_reputation(peer_id)
        
    def get_top_peers(self, limit: int = 10) -> List[tuple]:
        """Получить список пиров с наивысшей репутацией"""
        return self.reputation.get_top_peers(limit)
        
    def set_message_handler(self, handler: Callable[[str, str], Awaitable[None]]):
        """Устанавливает обработчик входящих сообщений
        
        Args:
            handler: Функция обработки сообщений (peer_id, message) -> None
        """
        self._message_handler = handler 