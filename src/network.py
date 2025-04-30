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

from src.p2p_connection import NodeConnection
from src.protocol import (
    Message, MessageType, HandshakeMessage, OnionMessage,
    PingMessage, PongMessage, ErrorMessage, RouteUpdateMessage,
    NodeInfoMessage
)
from src.crypto import CryptoManager
from src.security import SecurityManager

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
    """P2P соединение для обмена сообщениями"""
    
    def __init__(self, host: str, port: int, node_id: str, public_key: str,
                 crypto_manager: CryptoManager, security_manager: SecurityManager):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.public_key = public_key
        self.crypto = crypto_manager
        self.security = security_manager
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1.0
        self.message_handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}
        self.server = None
        self.connection_state = "disconnected"
        self.error_count = 0
        self.max_errors = 3
        self.last_ping_time = None
        
    async def connect(self) -> None:
        """Устанавливает соединение с узлом"""
        try:
            uri = f"ws://{self.host}:{self.port}"
            self.websocket = await websockets.connect(uri)
            self.connected = True
            self.connection_state = "connected"
            self.reconnect_attempts = 0
            self.error_count = 0
            logger.info(f"Connected to {uri}")
            
            # Запускаем обработку сообщений
            asyncio.create_task(self._handle_messages())
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.connected = False
            self.connection_state = "disconnected"
            self.error_count += 1
            if self.error_count < self.max_errors:
                await self._handle_connection_error()
            
    async def _handle_connection_error(self) -> None:
        """Обрабатывает ошибки соединения"""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))
            logger.info(f"Reconnecting in {delay} seconds...")
            await asyncio.sleep(delay)
            await self.connect()
        else:
            logger.error(f"Превышено максимальное количество попыток переподключения ({self.max_reconnect_attempts})")
            self.connection_state = "disconnected"
            
    async def _handle_messages(self) -> None:
        """Обрабатывает входящие сообщения"""
        if not self.websocket:
            return
            
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get("type")
                    
                    if message_type in self.message_handlers:
                        await self.message_handlers[message_type](data)
                    else:
                        logger.warning(f"Unknown message type: {message_type}")
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON message")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
        except ConnectionClosedOK:
            logger.info("Connection closed normally")
        except ConnectionClosedError as e:
            logger.error(f"Connection closed with error: {e}")
        finally:
            self.connected = False
            self.connection_state = "disconnected"
            if self.error_count < self.max_errors:
                await self._handle_connection_error()
            
    async def send_message(self, message_type: str, data: Dict[str, Any]) -> None:
        """Отправляет сообщение"""
        if not self.connected or not self.websocket:
            raise ConnectionError("Not connected")
            
        try:
            message = {
                "type": message_type,
                "data": data
            }
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
            
    async def ping(self) -> None:
        """Отправляет пинг для проверки соединения"""
        if not self.connected or not self.websocket:
            return
            
        try:
            await self.send_message("ping", {"timestamp": time.time()})
            self.last_ping_time = time.time()
        except Exception as e:
            logger.error(f"Error sending ping: {e}")
            self.error_count += 1
            if self.error_count < self.max_errors:
                await self._handle_connection_error()
            
    async def stop(self) -> None:
        """Останавливает соединение"""
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        self.connection_state = "disconnected"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return None

    async def init(self):
        """Initialize any async resources"""
        pass  # Add async initialization if needed

class Network:
    """
    Реализует P2P-сеть для обмена сообщениями между узлами
    """
    
    def __init__(self, config):
        """
        Инициализирует сетевой модуль
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.connections: Dict[str, P2PConnection] = {}
        self.server = None
        self.is_running = False
        self.connection_timeout = 30
        self.crypto_manager = CryptoManager(config)
        self.security_manager = SecurityManager(config)
        self.message_handlers = []
        
    async def start(self):
        """Запускает сетевой сервер"""
        try:
            host = self.config.get_listen_address()[0]
            port = self.config.get_listen_address()[1]
            
            self.server = await websockets.serve(
                self._handle_connection,
                host,
                port,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            
            self.is_running = True
            logger.info(f"Network server started on {host}:{port}")
            
            # Подключаемся к известным узлам
            for node in self.config.get_bootstrap_nodes():
                host, port = node.split(":")
                asyncio.create_task(self.connect_to_peer(host, int(port)))
                
        except Exception as e:
            logger.error(f"Failed to start network server: {e}")
            raise
            
    async def connect_to_peer(self, host: str, port: int) -> bool:
        """
        Подключается к новому пиру
        
        Args:
            host: Хост пира
            port: Порт пира
            
        Returns:
            bool: True если подключение успешно, False в противном случае
        """
        peer_address = f"{host}:{port}"
        
        if peer_address in self.connections:
            logger.warning(f"Already connected to {peer_address}")
            return False
            
        try:
            connection = P2PConnection(
                host=host,
                port=port,
                node_id=self.config.get_node_id(),
                public_key=self.config.public_key.encode().hex(),
                crypto_manager=self.crypto_manager,
                security_manager=self.security_manager
            )
            
            await connection.connect()
            
            if connection.connected:
                self.connections[peer_address] = connection
                logger.info(f"Successfully connected to peer {peer_address}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to connect to peer {peer_address}: {e}")
            
        return False
        
    async def disconnect_from_peer(self, peer_address: str):
        """
        Отключается от пира
        
        Args:
            peer_address: Адрес пира в формате host:port
        """
        if peer_address in self.connections:
            connection = self.connections[peer_address]
            await connection.stop()
            del self.connections[peer_address]
            logger.info(f"Disconnected from peer {peer_address}")
            
    async def send_to_peer(self, peer_address: str, message: dict) -> bool:
        """
        Отправляет сообщение конкретному пиру
        
        Args:
            peer_address: Адрес пира в формате host:port
            message: Сообщение для отправки
            
        Returns:
            bool: True если сообщение отправлено успешно, False в противном случае
        """
        if peer_address not in self.connections:
            logger.error(f"No connection to peer {peer_address}")
            return False
            
        try:
            connection = self.connections[peer_address]
            await connection.send_message(message["type"], message["data"])
            return True
        except Exception as e:
            logger.error(f"Failed to send message to peer {peer_address}: {e}")
            return False
            
    def add_message_handler(self, handler: Callable):
        """
        Добавляет обработчик входящих сообщений
        
        Args:
            handler: Функция-обработчик сообщений
        """
        self.message_handlers.append(handler)
        
    async def _handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        Обрабатывает входящее подключение
        
        Args:
            websocket: WebSocket соединение
            path: Путь запроса
        """
        peer_address = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"New connection from {peer_address}")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Уведомляем всех обработчиков о новом сообщении
                    for handler in self.message_handlers:
                        await handler(peer_address, data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from {peer_address}")
                except Exception as e:
                    logger.error(f"Error handling message from {peer_address}: {e}")
                    
        except WebSocketException as e:
            logger.error(f"WebSocket error with {peer_address}: {e}")
        finally:
            await self.disconnect_from_peer(peer_address)
            
    def get_connected_peers(self) -> List[str]:
        """
        Возвращает список подключенных пиров
        
        Returns:
            List[str]: Список адресов подключенных пиров
        """
        return list(self.connections.keys())
        
    async def stop(self):
        """Stop the network server"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        # Close all connections
        for conn in list(self.connections.values()):
            try:
                await conn.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
                
        self.connections.clear()
        
        # Stop the server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        logger.info("Network server stopped")
        
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