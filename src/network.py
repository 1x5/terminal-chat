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
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
import websockets
from websockets.exceptions import WebSocketException

from src.p2p_connection import NodeConnection

logger = logging.getLogger("securetermchat.network")

class P2PConnection:
    """
    Реализует P2P-соединение между двумя узлами
    """
    
    def __init__(self, host: str, port: int):
        """
        Инициализирует P2P-соединение
        
        Args:
            host (str): Хост для прослушивания
            port (int): Порт для прослушивания
        """
        self.host = host
        self.port = port
        self.websocket = None
        self.is_running = False
        self.message_queue = asyncio.Queue()
        self.remote_address = None
        
    async def start(self):
        """Запускает прослушивание входящих соединений"""
        self.is_running = True
        self.server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port
        )
        logger.info(f"P2P-соединение запущено на {self.host}:{self.port}")
        
    async def stop(self):
        """Останавливает соединение"""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("P2P-соединение остановлено")
        
    async def connect(self, host: str, port: int):
        """
        Устанавливает соединение с удаленным узлом
        
        Args:
            host (str): Хост удаленного узла
            port (int): Порт удаленного узла
        """
        try:
            self.websocket = await websockets.connect(f"ws://{host}:{port}")
            self.remote_address = (host, port)
            logger.info(f"Установлено соединение с {host}:{port}")
        except Exception as e:
            logger.error(f"Ошибка при установке соединения с {host}:{port}: {e}")
            raise
            
    def is_connected(self) -> bool:
        """
        Проверяет, установлено ли соединение
        
        Returns:
            bool: True если соединение установлено
        """
        return self.websocket is not None and not self.websocket.closed
        
    async def send_message(self, message: str):
        """
        Отправляет сообщение
        
        Args:
            message (str): Текст сообщения
        """
        if not self.is_connected():
            raise Exception("Соединение не установлено")
            
        try:
            await self.websocket.send(message)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            raise
            
    async def receive_message(self) -> str:
        """
        Получает сообщение
        
        Returns:
            str: Текст сообщения
        """
        if not self.is_connected():
            raise Exception("Соединение не установлено")
            
        try:
            return await self.websocket.recv()
        except Exception as e:
            logger.error(f"Ошибка при получении сообщения: {e}")
            raise
            
    async def _handle_connection(self, websocket, path):
        """
        Обрабатывает входящее соединение
        
        Args:
            websocket: WebSocket-соединение
            path: Путь запроса
        """
        self.websocket = websocket
        self.remote_address = websocket.remote_address
        logger.info(f"Получено входящее соединение от {self.remote_address}")
        
        try:
            async for message in websocket:
                await self.message_queue.put(message)
        except Exception as e:
            logger.error(f"Ошибка при обработке входящего соединения: {e}")
        finally:
            await self.stop()

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