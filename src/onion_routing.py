"""
Модуль луковой маршрутизации для SecureTermChat

Реализует анонимную передачу сообщений через цепочки узлов
с многослойным шифрованием.
"""

import os
import json
import time
import random
import logging
import asyncio
import base64
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Set, Callable

from nacl.public import PrivateKey, PublicKey, Box
import nacl.utils

from src.p2p_connection import NodeConnection
from src.crypto import (
    generate_onion_layers,
    wrap_in_onion_layers,
    unwrap_onion_layer,
    CryptoManager
)
from src.network import Network
from src.config import Config

logger = logging.getLogger("securetermchat.onion_routing")

class OnionCircuit:
    """
    Представляет анонимную цепочку узлов для луковой маршрутизации
    """
    
    def __init__(self, circuit_id: str, nodes: List[Dict], config):
        """
        Инициализирует цепочку узлов
        
        Args:
            circuit_id (str): Уникальный идентификатор цепочки
            nodes (List[Dict]): Список узлов в цепочке
            config: Объект конфигурации
        """
        self.circuit_id = circuit_id
        self.nodes = nodes
        self.config = config
        
        # Состояние цепочки
        self.established = False
        self.created_at = time.time()
        self.last_used = time.time()
        self.bytes_sent = 0
        self.bytes_received = 0
        self.error_count = 0
        
        # Ключи шифрования для каждого хопа
        self.hop_keys = []
        self.hop_boxes = []
        
        # Соединения с узлами
        self.connections = {}  # node_id -> NodeConnection
        self.hops = []  # Список активных хопов
        
        # Статистика
        self.messages_sent = 0
        self.messages_received = 0
        
        # Флаги состояния
        self.setup_in_progress = False
        self.teardown_in_progress = False
        
    async def establish(self) -> bool:
        """
        Устанавливает цепочку узлов
        
        Returns:
            bool: True если цепочка успешно установлена
        """
        if self.setup_in_progress:
            logger.warning(f"Установка цепочки {self.circuit_id} уже выполняется")
            return False
            
        self.setup_in_progress = True
        
        try:
            # Генерируем ключи для каждого хопа
            for _ in range(len(self.nodes)):
                private_key = PrivateKey.generate()
                public_key = private_key.public_key
                self.hop_keys.append((private_key, public_key))
            
            # Устанавливаем соединения с узлами
            for i, node in enumerate(self.nodes):
                try:
                    # Создаем соединение с узлом
                    connection = await self._connect_to_node(node)
                    if not connection:
                        raise ConnectionError(f"Не удалось подключиться к узлу {node['address']}")
                        
                    self.connections[node['node_id']] = connection
                    self.hops.append(connection)
                    
                    # Создаем Box для шифрования с этим хопом
                    node_public_key = PublicKey(bytes.fromhex(node['public_key']))
                    box = Box(self.hop_keys[i][0], node_public_key)
                    self.hop_boxes.append(box)
                    
                    # Отправляем команду создания цепочки
                    message = {
                        'type': 'create_circuit',
                        'circuit_id': self.circuit_id,
                        'next_hop': self.nodes[i+1]['address'] if i < len(self.nodes)-1 else None,
                        'public_key': bytes(self.hop_keys[i][1]).hex()
                    }
                    
                    # Шифруем сообщение для текущего хопа
                    encrypted = box.encrypt(json.dumps(message).encode())
                    
                    # Отправляем сообщение узлу
                    success = await connection.send_message({
                        'type': 'onion_relay',
                        'circuit_id': self.circuit_id,
                        'payload': encrypted
                    })
                    
                    if not success:
                        raise ConnectionError(f"Не удалось отправить сообщение узлу {node['address']}")
                        
                    # Ждем подтверждения
                    response = await self._wait_for_response(connection, 'circuit_established', timeout=10)
                    if not response:
                        raise ConnectionError(f"Не получено подтверждение от узла {node['address']}")
                        
                except Exception as e:
                    logger.error(f"Ошибка при установке хопа {i} в цепочке {self.circuit_id}: {e}")
                    await self._cleanup_connections()
                    return False
                    
            self.established = True
            self.last_used = time.time()
            logger.info(f"Цепочка {self.circuit_id} успешно установлена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при установке цепочки {self.circuit_id}: {e}")
            self.error_count += 1
            await self._cleanup_connections()
            return False
        finally:
            self.setup_in_progress = False
            
    async def _connect_to_node(self, node: Dict) -> Optional[NodeConnection]:
        """
        Устанавливает соединение с узлом
        
        Args:
            node (Dict): Информация об узле
            
        Returns:
            Optional[NodeConnection]: Соединение с узлом или None при ошибке
        """
        try:
            # Разбиваем адрес на хост и порт
            host, port = node['address'].split(':')
            port = int(port)
            
            # Создаем соединение
            connection = NodeConnection(node['node_id'], None)  # WebSocket будет установлен позже
            await connection.connect(host, port)
            
            return connection
            
        except Exception as e:
            logger.error(f"Ошибка при подключении к узлу {node['address']}: {e}")
            return None
            
    async def _wait_for_response(self, connection: NodeConnection, expected_type: str, timeout: float = 10) -> Optional[Dict]:
        """
        Ожидает ответ от узла
        
        Args:
            connection (NodeConnection): Соединение с узлом
            expected_type (str): Ожидаемый тип сообщения
            timeout (float): Таймаут ожидания в секундах
            
        Returns:
            Optional[Dict]: Полученное сообщение или None при таймауте
        """
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                message = await connection.receive_message()
                if message and message.get('type') == expected_type:
                    return message
                await asyncio.sleep(0.1)
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при ожидании ответа: {e}")
            return None
            
    async def _cleanup_connections(self):
        """Закрывает все соединения с узлами"""
        for connection in self.connections.values():
            try:
                await connection.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии соединения: {e}")
        self.connections.clear()
        
    async def send_message(self, message: Dict) -> bool:
        """
        Отправляет сообщение через цепочку
        
        Args:
            message (Dict): Сообщение для отправки
            
        Returns:
            bool: True если сообщение успешно отправлено
        """
        if not self.established:
            logger.warning(f"Попытка отправить сообщение через неустановленную цепочку {self.circuit_id}")
            return False
            
        try:
            # Шифруем сообщение
            encrypted = self.encrypt_message(message, final_hop=True)
            
            # Отправляем через первый узел
            first_node = self.nodes[0]
            connection = self.connections.get(first_node['node_id'])
            
            if not connection:
                logger.error(f"Нет соединения с первым узлом в цепочке {self.circuit_id}")
                return False
                
            success = await connection.send_message({
                'type': 'onion_relay',
                'circuit_id': self.circuit_id,
                'payload': encrypted
            })
            
            if success:
                self.update_stats(sent=len(encrypted))
                return True
            else:
                logger.warning(f"Не удалось отправить сообщение через цепочку {self.circuit_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения через цепочку {self.circuit_id}: {e}")
            self.error_count += 1
            return False
            
    async def teardown(self):
        """
        Закрывает цепочку и все соединения
        """
        if self.teardown_in_progress:
            return
            
        self.teardown_in_progress = True
        
        try:
            # Отправляем команду закрытия всем узлам
            for node in self.nodes:
                connection = self.connections.get(node['node_id'])
                if connection:
                    try:
                        await connection.send_message({
                            'type': 'destroy_circuit',
                            'circuit_id': self.circuit_id
                        })
                    except Exception as e:
                        logger.warning(f"Ошибка при отправке команды закрытия узлу {node['address']}: {e}")
                        
            # Закрываем все соединения
            await self._cleanup_connections()
            
            self.established = False
            logger.info(f"Цепочка {self.circuit_id} закрыта")
            
        except Exception as e:
            logger.error(f"Ошибка при закрытии цепочки {self.circuit_id}: {e}")
        finally:
            self.teardown_in_progress = False
            
    async def is_healthy(self) -> bool:
        """
        Проверяет состояние цепочки
        
        Returns:
            bool: True если цепочка в хорошем состоянии
        """
        if not self.established:
            return False
            
        # Проверяем все соединения
        for node in self.nodes:
            connection = self.connections.get(node['node_id'])
            if not connection or not connection.connected:
                return False
                
        return True
        
    def get_connection_stats(self) -> Dict:
        """
        Возвращает статистику соединений
        
        Returns:
            Dict: Статистика по соединениям
        """
        stats = {
            'total_connections': len(self.connections),
            'active_connections': sum(1 for c in self.connections.values() if c.connected),
            'connections': {}
        }
        
        for node_id, connection in self.connections.items():
            stats['connections'][node_id] = {
                'connected': connection.connected,
                'messages_sent': connection.messages_sent,
                'messages_received': connection.messages_received,
                'last_active': connection.last_message_sent
            }
            
        return stats
        
    def encrypt_message(self, message: Dict, final_hop: bool = False) -> bytes:
        """
        Шифрует сообщение для передачи через цепочку
        
        Args:
            message (Dict): Сообщение для шифрования
            final_hop (bool): Является ли это последним хопом
            
        Returns:
            bytes: Зашифрованное сообщение
        """
        try:
            # Сериализуем сообщение в JSON
            current_message = json.dumps(message).encode()
            
            # Шифруем для каждого хопа в обратном порядке
            for i in range(len(self.hop_boxes) - 1, -1, -1):
                # Если не последний хоп и не финальное сообщение, оборачиваем в relay
                if not final_hop and i > 0:
                    relay_message = {
                        'type': 'relay',
                        'next_hop': self.nodes[i]['address'],
                        'payload': base64.b64encode(current_message).decode()
                    }
                    current_message = json.dumps(relay_message).encode()
                
                # Шифруем текущий слой
                try:
                    current_message = self.hop_boxes[i].encrypt(current_message)
                except Exception as e:
                    logger.error(f"Ошибка при шифровании слоя {i}: {e}")
                    return b''
                
            return current_message
            
        except Exception as e:
            logger.error(f"Ошибка при шифровании сообщения: {e}")
            self.error_count += 1
            return b''
        
    def decrypt_message(self, encrypted_message: bytes) -> Optional[Dict]:
        """
        Расшифровывает сообщение, полученное через цепочку
        
        Args:
            encrypted_message (bytes): Зашифрованное сообщение
            
        Returns:
            Optional[Dict]: Расшифрованное сообщение или None в случае ошибки
        """
        try:
            current_message = encrypted_message
            
            # Расшифровываем каждый слой
            for box in self.hop_boxes:
                # Расшифровываем текущий слой
                current_message = box.decrypt(current_message)
                if not current_message:
                    logger.error("Не удалось расшифровать слой")
                    return None
                    
                # Пробуем распарсить как JSON
                try:
                    decrypted = json.loads(current_message.decode())
                except json.JSONDecodeError:
                    logger.error("Не удалось распарсить JSON")
                    return None
                    
                # Если это relay сообщение, извлекаем payload
                if isinstance(decrypted, dict) and decrypted.get('type') == 'relay':
                    try:
                        current_message = base64.b64decode(decrypted['payload'])
                    except:
                        logger.error("Не удалось декодировать payload")
                        return None
                else:
                    # Это финальное сообщение
                    return decrypted
                    
            return json.loads(current_message.decode())
            
        except Exception as e:
            logger.error(f"Ошибка при расшифровке сообщения: {e}")
            self.error_count += 1
            return None
            
    def is_expired(self) -> bool:
        """
        Проверяет, истекло ли время жизни цепочки
        
        Returns:
            bool: True если цепочка устарела
        """
        current_time = time.time()
        max_age = self.config.config.get('circuit_max_age', 3600)  # 1 час по умолчанию
        idle_timeout = self.config.config.get('circuit_idle_timeout', 600)  # 10 минут по умолчанию
        
        return (current_time - self.created_at > max_age or 
                current_time - self.last_used > idle_timeout)
                
    def is_overloaded(self) -> bool:
        """
        Проверяет, превышен ли лимит трафика
        
        Returns:
            bool: True если цепочка перегружена
        """
        max_traffic = self.config.config.get('circuit_max_traffic', 1024 * 1024)  # 1 МБ по умолчанию
        threshold = self.config.config.get('circuit_rotation_threshold', 0.8)  # 80% по умолчанию
        
        total_traffic = self.bytes_sent + self.bytes_received
        return total_traffic > (max_traffic * threshold)
        
    def update_stats(self, sent: int = 0, received: int = 0):
        """
        Обновляет статистику использования цепочки
        
        Args:
            sent (int): Количество отправленных байт
            received (int): Количество полученных байт
        """
        self.bytes_sent += sent
        self.bytes_received += received
        self.last_used = time.time()
        
        if sent > 0:
            self.messages_sent += 1
        if received > 0:
            self.messages_received += 1

class OnionRoutingManager:
    """
    Менеджер луковой маршрутизации
    
    Управляет созданием и поддержанием цепочек луковой маршрутизации,
    обеспечивает анонимную передачу сообщений через сеть.
    """
    
    def __init__(self, config: Config, crypto: CryptoManager, network: Network):
        """
        Инициализирует менеджер луковой маршрутизации
        
        Args:
            config (Config): Конфигурация приложения
            crypto (CryptoManager): Менеджер шифрования
            network (Network): Сетевой модуль
        """
        self.config = config
        self.crypto = crypto
        self.network = network
        self.circuits = {}  # circuit_id -> OnionCircuit
        self.message_handler = None
        self.next_circuit_id = 0
        
    async def start(self):
        """Запускает менеджер луковой маршрутизации"""
        await self.network.start()
        self.network.on_message = self._handle_message
        
    async def stop(self):
        """Останавливает менеджер луковой маршрутизации"""
        await self.network.stop()
        
    async def create_circuit(self, route: List[Tuple[str, int]]) -> str:
        """
        Создает новую цепочку луковой маршрутизации
        
        Args:
            route: Список узлов маршрута в формате (host, port)
            
        Returns:
            str: ID созданной цепочки
        """
        circuit_id = str(self.next_circuit_id)
        self.next_circuit_id += 1
        
        # Генерируем слои шифрования
        layers = generate_onion_layers(len(route))
        
        # Сохраняем информацию о цепочке
        self.circuits[circuit_id] = {
            "route": route,
            "layers": layers,
            "status": "creating"
        }
        
        # Устанавливаем соединения с узлами маршрута
        for i, (host, port) in enumerate(route):
            try:
                await self.network.connect(f"ws://{host}:{port}")
            except Exception as e:
                logger.error(f"Failed to connect to {host}:{port}: {e}")
                await self.teardown_circuit(circuit_id)
                raise
                
        self.circuits[circuit_id]["status"] = "active"
        return circuit_id
        
    async def teardown_circuit(self, circuit_id: str):
        """
        Разрывает цепочку луковой маршрутизации
        
        Args:
            circuit_id: ID цепочки
        """
        if circuit_id in self.circuits:
            circuit = self.circuits[circuit_id]
            
            # Отправляем команду разрыва всем узлам
            for host, port in circuit["route"]:
                try:
                    await self.network.send_message(
                        f"ws://{host}:{port}",
                        json.dumps({"type": "teardown", "circuit_id": circuit_id})
                    )
                except Exception as e:
                    logger.warning(f"Error sending teardown to {host}:{port}: {e}")
                    
            del self.circuits[circuit_id]
            
    async def send_message(self, circuit_id: str, message: Dict):
        """
        Отправляет сообщение через цепочку луковой маршрутизации
        
        Args:
            circuit_id: ID цепочки
            message: Сообщение для отправки
        """
        if circuit_id not in self.circuits:
            raise ValueError(f"Circuit {circuit_id} not found")
            
        circuit = self.circuits[circuit_id]
        if circuit["status"] != "active":
            raise ValueError(f"Circuit {circuit_id} is not active")
            
        # Получаем публичные ключи узлов маршрута
        route_public_keys = [
            circuit["layers"][f"hop_{i}"]["public_key"]
            for i in range(len(circuit["route"]))
        ]
        
        # Оборачиваем сообщение в слои шифрования
        wrapped = wrap_in_onion_layers(message, route_public_keys)
        
        # Отправляем через первый узел маршрута
        first_host, first_port = circuit["route"][0]
        await self.network.send_message(
            f"ws://{first_host}:{first_port}",
            json.dumps({
                "type": "onion",
                "circuit_id": circuit_id,
                "payload": wrapped
            })
        )
        
    async def _handle_message(self, connection, message: str):
        """
        Обрабатывает входящие сообщения
        
        Args:
            connection: Соединение
            message: Полученное сообщение
        """
        try:
            data = json.loads(message)
            
            if data["type"] == "onion":
                # Получаем ID цепочки и зашифрованные данные
                circuit_id = data["circuit_id"]
                wrapped = data["payload"]
                
                if circuit_id in self.circuits:
                    circuit = self.circuits[circuit_id]
                    
                    # Находим наш индекс в маршруте
                    our_index = None
                    for i, (host, port) in enumerate(circuit["route"]):
                        if f"ws://{host}:{port}" == connection.remote_address:
                            our_index = i
                            break
                            
                    if our_index is not None:
                        # Снимаем наш слой шифрования
                        private_key = circuit["layers"][f"hop_{our_index}"]["private_key"]
                        unwrapped = unwrap_onion_layer(wrapped, private_key)
                        
                        if our_index < len(circuit["route"]) - 1:
                            # Пересылаем дальше
                            next_host, next_port = circuit["route"][our_index + 1]
                            await self.network.send_message(
                                f"ws://{next_host}:{next_port}",
                                json.dumps({
                                    "type": "onion",
                                    "circuit_id": circuit_id,
                                    "payload": unwrapped
                                })
                            )
                        else:
                            # Это последний узел, обрабатываем сообщение
                            if self.message_handler:
                                await self.message_handler(circuit_id, unwrapped)
                                
            elif data["type"] == "teardown":
                # Обрабатываем команду разрыва цепочки
                circuit_id = data["circuit_id"]
                if circuit_id in self.circuits:
                    await self.teardown_circuit(circuit_id)
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    def set_message_handler(self, handler):
        """
        Устанавливает обработчик входящих сообщений
        
        Args:
            handler: Функция-обработчик
        """
        self.message_handler = handler 