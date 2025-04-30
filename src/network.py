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
from .e2e_encryption import E2EEncryption, E2EEncryptionError
from .signatures import MessageSigner, SignatureVerificationError
from .reputation import ReputationManager, ReputationEvent

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
    """Represents a P2P connection with another node"""
    
    def __init__(self, websocket: WebSocketServerProtocol, peer_id: str):
        self.websocket = websocket
        self.peer_id = peer_id
        self.connected = True
        
    @property
    def is_connected(self) -> bool:
        return self.connected and self.websocket.open
        
    async def send_message(self, message: str) -> None:
        """Send an encrypted message through the websocket"""
        if not self.is_connected:
            raise ConnectionError("Connection is closed")
            
        try:
            await self.websocket.send(message)
        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to send message: {e}")
            
    async def close(self) -> None:
        """Close the connection"""
        self.connected = False
        if self.websocket.open:
            await self.websocket.close()

class Network:
    """
    Реализует P2P-сеть для обмена сообщениями между узлами
    """
    
    def __init__(self, config: Config, encryption: E2EEncryption):
        self.config = config
        self.encryption = encryption
        self.signer = MessageSigner()
        self.reputation = ReputationManager()
        self.connections: Dict[str, P2PConnection] = {}
        self.server = None
        self.connection_timeout = 30  # seconds
        self.is_running = False
        self.message_handlers = []
        
    async def start(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        """Start the network server"""
        try:
            self.server = await websockets.serve(
                self._handle_connection,
                host,
                port,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            logger.info(f"Network server started on {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to start network server: {e}")
            raise NetworkError(f"Server start failed: {e}")
            
    async def _handle_connection(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Handle incoming connections"""
        try:
            # Exchange keys and signatures
            my_key = self.encryption.get_public_key()
            my_sig_key = self.signer.get_public_key()
            
            await websocket.send(json.dumps({
                "type": "key_exchange",
                "key": my_key,
                "sig_key": my_sig_key,
                "node_id": self.config.get_node_id()
            }))
            
            # Get peer's keys
            msg = await asyncio.wait_for(websocket.recv(), timeout=self.connection_timeout)
            data = json.loads(msg)
            if data["type"] != "key_exchange":
                raise NetworkError("Invalid key exchange message")
                
            peer_id = data["node_id"]
            peer_key = data["key"]
            peer_sig_key = data["sig_key"]
            
            # Проверяем репутацию пира
            if not self.reputation.is_trusted(peer_id):
                logger.warning(f"Connection attempt from untrusted peer {peer_id}")
                await websocket.close()
                return
                
            # Store peer's keys
            self.encryption.add_peer_key(peer_id, peer_key)
            
            # Create connection
            connection = P2PConnection(websocket, peer_id)
            self.connections[peer_id] = connection
            
            # Handle messages
            try:
                async for message in websocket:
                    try:
                        # Расшифровываем сообщение
                        decrypted = self.encryption.decrypt_message(message, peer_id)
                        data = json.loads(decrypted)
                        
                        # Проверяем подпись
                        if not MessageSigner.verify_json_message(data):
                            logger.error(f"Invalid signature from {peer_id}")
                            self.reputation.update_reputation(peer_id, ReputationEvent.INVALID_SIGNATURE)
                            continue
                            
                        # Обновляем репутацию
                        self.reputation.update_reputation(peer_id, ReputationEvent.MESSAGE_RECEIVED)
                        
                        await self._handle_message(data, peer_id)
                    except E2EEncryptionError as e:
                        logger.error(f"Failed to decrypt message from {peer_id}: {e}")
                        self.reputation.update_reputation(peer_id, ReputationEvent.INVALID_ENCRYPTION)
                    except SignatureVerificationError as e:
                        logger.error(f"Invalid signature from {peer_id}: {e}")
                        self.reputation.update_reputation(peer_id, ReputationEvent.INVALID_SIGNATURE)
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Connection closed with peer {peer_id}")
                self.reputation.update_reputation(peer_id, ReputationEvent.CONNECTION_DROPPED)
            finally:
                await self._remove_connection(peer_id)
                
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
            if websocket.open:
                await websocket.close()
                
    async def _handle_message(self, message: str, peer_id: str) -> None:
        """Handle decrypted messages"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "chat":
                # Handle chat message
                await self._handle_chat_message(data, peer_id)
            elif message_type == "system":
                # Handle system message
                await self._handle_system_message(data, peer_id)
            else:
                logger.warning(f"Unknown message type from {peer_id}: {message_type}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message from {peer_id}")
            
    async def send_message(self, peer_id: str, message: str) -> None:
        """Send an encrypted and signed message to a specific peer"""
        if peer_id not in self.connections:
            raise NetworkError(f"No connection to peer {peer_id}")
            
        try:
            # Создаем сообщение с подписью
            data = {
                "type": "chat",
                "content": message,
                "sender": self.config.get_node_id()
            }
            signed_data = self.signer.sign_json_message(data)
            
            # Шифруем подписанное сообщение
            encrypted = self.encryption.encrypt_message(json.dumps(signed_data), peer_id)
            await self.connections[peer_id].send_message(encrypted)
            
            # Обновляем репутацию
            self.reputation.update_reputation(peer_id, ReputationEvent.MESSAGE_SENT)
            
        except E2EEncryptionError as e:
            logger.error(f"Failed to encrypt message for {peer_id}: {e}")
            raise NetworkError(f"Encryption failed: {e}")
        except Exception as e:
            logger.error(f"Failed to send message to {peer_id}: {e}")
            await self._remove_connection(peer_id)
            raise NetworkError(f"Send failed: {e}")
            
    async def broadcast_message(self, message: str) -> None:
        """Send an encrypted message to all connected peers"""
        failed_peers = []
        for peer_id in list(self.connections.keys()):
            try:
                await self.send_message(peer_id, message)
            except NetworkError:
                failed_peers.append(peer_id)
                
        if failed_peers:
            logger.warning(f"Failed to send message to peers: {', '.join(failed_peers)}")
            
    async def _remove_connection(self, peer_id: str) -> None:
        """Remove a peer connection"""
        if peer_id in self.connections:
            await self.connections[peer_id].close()
            del self.connections[peer_id]
            self.encryption.remove_peer_key(peer_id)
            
    async def stop(self) -> None:
        """Stop the network server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        for peer_id in list(self.connections.keys()):
            await self._remove_connection(peer_id)
            
        logger.info("Network server stopped")

    def add_message_handler(self, handler: Callable):
        """
        Добавляет обработчик входящих сообщений
        
        Args:
            handler: Функция-обработчик сообщений
        """
        self.message_handlers.append(handler)
        
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