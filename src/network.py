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

class P2PNetwork:
    """
    Реализует P2P-сеть для обмена сообщениями между узлами
    """
    
    def __init__(self, config, crypto):
        """
        Инициализирует сетевой модуль
        
        Args:
            config: Объект конфигурации
            crypto: Объект шифрования
        """
        self.config = config
        self.crypto = crypto
        self.connections = []
        self.is_running = False
        self.server = None
        self.on_message = None
        
    async def start(self):
        """Start the network server"""
        self.is_running = True
        
        async def handler(websocket):
            # Определяем порт из адреса подключения
            local_port = websocket.local_address[1]
            remote_port = websocket.remote_address[1]
            
            # Если это входящее соединение, используем порт из конфигурации
            if local_port == self.config.port:
                for conn in self.connections:
                    if conn.remote_address.endswith(str(remote_port)):
                        remote_port = int(conn.remote_address.split(":")[-1])
                        break
            
            remote_address = f"ws://localhost:{remote_port}"
            connection = NodeConnection(websocket, remote_address)
            self.connections.append(connection)
            try:
                await self._handle_messages(connection)
            finally:
                if connection in self.connections:
                    self.connections.remove(connection)
                await connection.close()
        
        self.server = await websockets.serve(
            handler,
            'localhost',
            self.config.port,
            ping_interval=None,  # Отключаем автоматические пинги
            ping_timeout=None    # Отключаем таймаут пингов
        )
        
    async def stop(self):
        """Stop the network server and close all connections"""
        self.is_running = False
        for conn in self.connections:
            await conn.close()
        self.connections = []
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
    async def connect(self, remote_address: str):
        """Connect to a remote peer"""
        try:
            websocket = await websockets.connect(
                remote_address,
                ping_interval=None,
                ping_timeout=None
            )
            connection = NodeConnection(websocket, remote_address)
            self.connections.append(connection)
            asyncio.create_task(self._handle_messages(connection))
            return connection
        except Exception as e:
            logger.error(f"Failed to connect to {remote_address}: {e}")
            raise
            
    async def send_message(self, remote_address: str, message: str):
        """Send a message to a specific peer"""
        for conn in self.connections:
            if conn.remote_address == remote_address:
                try:
                    # Отправляем сообщение как есть, без дополнительного шифрования
                    await conn.send(message)
                    return
                except Exception as e:
                    logger.error(f"Error sending message: {e}")
                    raise
        raise Exception(f"No connection found for {remote_address}")
        
    async def _handle_messages(self, connection):
        """Handle messages from a connection"""
        try:
            async for message in connection:
                logger.info(f"Received message: {message}")
                if self.on_message:
                    try:
                        data = json.loads(message)
                        logger.info(f"Parsed JSON: {data}")
                        if data.get("type") == "onion":
                            logger.info("Processing onion message")
                            
                            # Process the onion layer
                            try:
                                # Call message handler to process the layer
                                await self.on_message(connection, message)
                                
                                # Если есть другие соединения, пересылаем сообщение первому из них
                                other_connections = [c for c in self.connections if c != connection]
                                if other_connections:
                                    next_hop = other_connections[0]
                                    logger.info(f"Forwarding onion message to {next_hop.remote_address}")
                                    await next_hop.send(message)
                                else:
                                    logger.info("This is the final hop, processing message")
                            except Exception as e:
                                logger.error(f"Error processing onion layer: {e}")
                                raise
                        else:
                            # Regular message
                            logger.info("Processing regular message")
                            await self.on_message(connection, message)
                    except json.JSONDecodeError:
                        # Not a JSON message, treat as regular message
                        logger.info("Processing non-JSON message")
                        await self.on_message(connection, message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        raise
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed: {connection.remote_address}")
        except Exception as e:
            logger.error(f"Error handling messages: {e}")
        finally:
            if connection in self.connections:
                self.connections.remove(connection)
            await connection.close()
        
    def set_message_handler(self, handler):
        """Set the message handler"""
        self.on_message = handler
        
    async def broadcast_message(self, message: Dict) -> int:
        """
        Отправляет сообщение всем подключенным узлам
        
        Args:
            message (Dict): Сообщение для отправки
            
        Returns:
            int: Количество узлов, которым было отправлено сообщение
        """
        sent_count = 0
        
        for connection in self.connections:
            try:
                encrypted = self.crypto.encrypt(message)
                await connection.send(encrypted)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Ошибка при отправке сообщения узлу {connection.remote_address}: {e}")
                
        return sent_count
        
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