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
        self.connections = {}
        self.server = None
        self.is_running = False
        self.connection_timeout = 30  # 30 seconds timeout for connections
        
    async def start(self):
        """Start the network server"""
        if self.is_running:
            return
            
        self.is_running = True
        self.server = await websockets.serve(
            self._handle_connection,
            '0.0.0.0',  # Listen on all interfaces
            self.config.port,
            ping_interval=20,  # Send ping every 20 seconds
            ping_timeout=10,   # Wait 10 seconds for pong
            close_timeout=5    # Wait 5 seconds for close
        )
        logger.info(f"Network server started on port {self.config.port}")
        
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
        
    async def _handle_connection(self, websocket, path):
        """Handle incoming websocket connection"""
        try:
            async with websocket:
                # Set connection timeout
                websocket.timeout = self.connection_timeout
                
                # Get peer address
                peer = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
                
                # Create connection object
                conn = P2PConnection(websocket, peer)
                self.connections[peer] = conn
                
                try:
                    # Handle messages
                    async for message in websocket:
                        await self._handle_message(conn, message)
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"Connection closed with {peer}")
                except Exception as e:
                    logger.error(f"Error handling connection with {peer}: {e}")
                finally:
                    # Remove connection
                    self.connections.pop(peer, None)
        except Exception as e:
            logger.error(f"Error in connection handler: {e}")
            
    async def _handle_message(self, conn, message):
        """Handle incoming message"""
        try:
            data = json.loads(message)
            # Process message based on type
            if data.get("type") == "get_peers":
                await self._handle_get_peers(conn)
            # Add other message type handlers here
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message from {conn.peer}")
        except Exception as e:
            logger.error(f"Error handling message from {conn.peer}: {e}")
            
    async def _handle_get_peers(self, conn):
        """Handle get_peers request"""
        try:
            # Get list of known peers
            peers = list(self.connections.keys())
            
            # Send response
            await conn.send_message({
                "type": "peers_list",
                "peers": peers
            })
        except Exception as e:
            logger.error(f"Error handling get_peers request: {e}")
            
    async def connect(self, peer_address):
        """Connect to a peer"""
        if peer_address in self.connections:
            return
            
        try:
            # Parse address
            host, port = peer_address.split(':')
            port = int(port)
            
            # Connect with timeout
            websocket = await websockets.connect(
                f"ws://{host}:{port}",
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            
            # Create connection object
            conn = P2PConnection(websocket, peer_address)
            self.connections[peer_address] = conn
            
            # Start message handler
            asyncio.create_task(self._handle_connection(websocket, None))
            
            logger.info(f"Connected to peer: {peer_address}")
        except Exception as e:
            logger.warning(f"Failed to connect to {peer_address}: {e}")
            raise
            
    async def send_message(self, peer_address, message):
        """Send message to peer"""
        conn = self.connections.get(peer_address)
        if not conn:
            raise ConnectionError(f"No connection to {peer_address}")
            
        try:
            await conn.send_message(message)
        except Exception as e:
            logger.error(f"Error sending message to {peer_address}: {e}")
            raise
        
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