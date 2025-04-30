"""
Модуль соединений с узлами для SecureTermChat

Реализует класс для работы с соединениями между узлами в P2P-сети.
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Any, Optional, Generator, Tuple
import websockets
from websockets.exceptions import WebSocketException

logger = logging.getLogger("securetermchat.p2p_connection")

async def connect_to_node(host: str, port: int) -> Tuple[Optional[asyncio.StreamReader], Optional[asyncio.StreamWriter]]:
    """
    Устанавливает соединение с узлом
    
    Args:
        host (str): Хост узла
        port (int): Порт узла
        
    Returns:
        Tuple[Optional[asyncio.StreamReader], Optional[asyncio.StreamWriter]]: 
            Кортеж из reader и writer для соединения, или (None, None) при ошибке
    """
    try:
        # Устанавливаем TCP соединение
        reader, writer = await asyncio.open_connection(host, port)
        return reader, writer
    except Exception as e:
        logger.error(f"Ошибка при подключении к {host}:{port}: {e}")
        return None, None

class NodeConnection:
    """
    Представляет соединение с узлом в P2P-сети
    """
    
    def __init__(self, websocket, remote_address: str):
        """
        Инициализирует соединение с узлом
        
        Args:
            websocket: WebSocket-соединение
            remote_address (str): Удаленный адрес узла
        """
        self.websocket = websocket
        self.remote_address = remote_address
        self.connected = True
        self.connected_since = time.time()
        
        # Статистика сообщений
        self.messages_sent = 0
        self.messages_received = 0
        
        # Время последнего взаимодействия
        self.last_message_sent = 0
        self.last_message_received = 0
        
    async def connect(self, host: str, port: int) -> bool:
        """
        Устанавливает WebSocket соединение с узлом
        
        Args:
            host (str): Хост узла
            port (int): Порт узла
            
        Returns:
            bool: True если соединение успешно установлено
        """
        try:
            # Устанавливаем WebSocket соединение
            self.websocket = await websockets.connect(f"ws://{host}:{port}")
            self.connected = True
            self.connected_since = time.time()
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке WebSocket соединения с {host}:{port}: {e}")
            self.connected = False
            return False

    async def send_message(self, message: Dict) -> bool:
        """
        Отправляет сообщение узлу
        
        Args:
            message (Dict): Сообщение для отправки
            
        Returns:
            bool: True если сообщение успешно отправлено, иначе False
        """
        if not self.connected or not self.websocket:
            logger.warning(f"Попытка отправить сообщение узлу {self.remote_address}, с которым нет соединения")
            return False
            
        try:
            # Сериализуем сообщение в JSON
            message_json = json.dumps(message)
            
            # Отправляем через WebSocket
            await self.websocket.send(message_json)
            
            # Обновляем статистику
            self.messages_sent += 1
            self.last_message_sent = time.time()
            
            return True
            
        except WebSocketException as e:
            logger.warning(f"Ошибка при отправке сообщения узлу {self.remote_address}: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при отправке сообщения узлу {self.remote_address}: {e}")
            return False
    
    async def listen(self):
        """
        Генератор для прослушивания входящих сообщений
        
        Yields:
            Dict: Полученное сообщение
        """
        if not self.connected or not self.websocket:
            logger.warning(f"Попытка слушать сообщения от узла {self.remote_address}, с которым нет соединения")
            return
            
        try:
            async for message in self.websocket:
                try:
                    # Парсим JSON
                    data = json.loads(message)
                    
                    # Обновляем статистику
                    self.messages_received += 1
                    self.last_message_received = time.time()
                    
                    # Обрабатываем служебные сообщения
                    if data.get("type") == "ping":
                        # Отвечаем на пинг
                        await self.send_message({
                            "type": "pong",
                            "timestamp": time.time()
                        })
                        continue
                        
                    # Возвращаем сообщение
                    yield data
                    
                except json.JSONDecodeError:
                    logger.warning(f"Получено некорректное JSON-сообщение от узла {self.remote_address}")
                    
        except WebSocketException as e:
            logger.info(f"WebSocket соединение с узлом {self.remote_address} закрыто: {e}")
        except Exception as e:
            logger.error(f"Ошибка при прослушивании сообщений от узла {self.remote_address}: {e}")
        finally:
            self.connected = False
    
    async def close(self):
        """Закрывает соединение с узлом"""
        self.connected = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии соединения с узлом {self.remote_address}: {e}")
            finally:
                self.websocket = None
                
    def is_idle(self, timeout: int = 300) -> bool:
        """
        Проверяет, было ли соединение неактивно в течение указанного времени
        
        Args:
            timeout (int): Время неактивности в секундах
            
        Returns:
            bool: True если соединение неактивно, иначе False
        """
        if not self.connected:
            return True
            
        current_time = time.time()
        last_activity = max(self.last_message_sent, self.last_message_received)
        
        return current_time - last_activity > timeout 

    async def send(self, message: str):
        """Send a message through the WebSocket connection"""
        if not self.connected:
            raise Exception("Connection is closed")
        await self.websocket.send(message)
        self.messages_sent += 1
        self.last_message_sent = time.time()
        
    def __aiter__(self):
        """Make the connection async iterable for receiving messages"""
        return self
        
    async def __anext__(self):
        """Get the next message from the WebSocket connection"""
        if not self.connected:
            raise StopAsyncIteration
        try:
            message = await self.websocket.recv()
            self.messages_received += 1
            self.last_message_received = time.time()
            return message
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            raise StopAsyncIteration 