"""
Модуль распределенной хеш-таблицы (DHT) для маршрутизации

Реализует Kademlia DHT для поиска узлов и маршрутов в сети.
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
import hashlib

logger = logging.getLogger("securetermchat.dht")

@dataclass
class NodeInfo:
    """Информация об узле в DHT"""
    node_id: str
    address: str
    port: int
    last_seen: float
    distance: int = 0  # Расстояние до текущего узла

class DHT:
    """Реализация Kademlia DHT"""
    
    def __init__(self, config):
        """
        Инициализирует DHT
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.node_id = self._generate_node_id()
        self.k_buckets = {}  # k-buckets для хранения узлов
        self.routing_table = {}  # Таблица маршрутизации
        self.max_bucket_size = config.get("max_bucket_size", 20)
        self.refresh_interval = config.get("refresh_interval", 3600)
        self.last_refresh = time.time()
        
    def _generate_node_id(self) -> str:
        """Генерирует ID узла"""
        return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()
        
    def _calculate_distance(self, node_id1: str, node_id2: str) -> int:
        """Вычисляет расстояние между узлами (XOR)"""
        return int(node_id1, 16) ^ int(node_id2, 16)
        
    def _get_bucket_index(self, node_id: str) -> int:
        """Возвращает индекс k-bucket для узла"""
        distance = self._calculate_distance(self.node_id, node_id)
        return distance.bit_length() - 1
        
    async def add_node(self, node_id: str, address: str, port: int) -> bool:
        """
        Добавляет узел в DHT
        
        Args:
            node_id: ID узла
            address: IP-адрес
            port: Порт
            
        Returns:
            bool: True если узел добавлен
        """
        try:
            bucket_index = self._get_bucket_index(node_id)
            
            if bucket_index not in self.k_buckets:
                self.k_buckets[bucket_index] = []
                
            # Проверяем, есть ли уже такой узел
            for node in self.k_buckets[bucket_index]:
                if node.node_id == node_id:
                    node.last_seen = time.time()
                    return True
                    
            # Если бакет полон, удаляем самый старый узел
            if len(self.k_buckets[bucket_index]) >= self.max_bucket_size:
                self.k_buckets[bucket_index].pop(0)
                
            # Добавляем новый узел
            node = NodeInfo(
                node_id=node_id,
                address=address,
                port=port,
                last_seen=time.time(),
                distance=self._calculate_distance(self.node_id, node_id)
            )
            self.k_buckets[bucket_index].append(node)
            
            # Обновляем таблицу маршрутизации
            await self._update_routing_table()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении узла {node_id}: {e}")
            return False
            
    async def remove_node(self, node_id: str) -> bool:
        """
        Удаляет узел из DHT
        
        Args:
            node_id: ID узла
            
        Returns:
            bool: True если узел удален
        """
        try:
            bucket_index = self._get_bucket_index(node_id)
            
            if bucket_index in self.k_buckets:
                self.k_buckets[bucket_index] = [
                    node for node in self.k_buckets[bucket_index]
                    if node.node_id != node_id
                ]
                
                # Обновляем таблицу маршрутизации
                await self._update_routing_table()
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при удалении узла {node_id}: {e}")
            return False
            
    async def find_node(self, target_id: str) -> Optional[NodeInfo]:
        """
        Ищет ближайший узел к целевому ID
        
        Args:
            target_id: Целевой ID
            
        Returns:
            Optional[NodeInfo]: Информация о найденном узле
        """
        try:
            # Получаем все узлы из k-buckets
            all_nodes = []
            for bucket in self.k_buckets.values():
                all_nodes.extend(bucket)
                
            if not all_nodes:
                return None
                
            # Сортируем узлы по расстоянию до целевого ID
            all_nodes.sort(
                key=lambda node: self._calculate_distance(node.node_id, target_id)
            )
            
            return all_nodes[0]
            
        except Exception as e:
            logger.error(f"Ошибка при поиске узла {target_id}: {e}")
            return None
            
    async def find_route(self, target_id: str) -> List[NodeInfo]:
        """
        Ищет маршрут до целевого узла
        
        Args:
            target_id: ID целевого узла
            
        Returns:
            List[NodeInfo]: Список узлов маршрута
        """
        try:
            # Проверяем кэш маршрутов
            if target_id in self.routing_table:
                route = self.routing_table[target_id]
                if time.time() - route["timestamp"] < self.refresh_interval:
                    return route["nodes"]
                    
            # Ищем ближайший узел
            next_node = await self.find_node(target_id)
            if not next_node:
                return []
                
            # Строим маршрут
            route = [next_node]
            current_id = next_node.node_id
            
            # Продолжаем поиск, пока не достигнем целевого узла
            # или не превысим максимальное количество хопов
            max_hops = self.config.get("max_route_hops", 5)
            for _ in range(max_hops):
                if current_id == target_id:
                    break
                    
                next_node = await self.find_node(target_id)
                if not next_node or next_node.node_id in [node.node_id for node in route]:
                    break
                    
                route.append(next_node)
                current_id = next_node.node_id
                
            # Кэшируем маршрут
            self.routing_table[target_id] = {
                "nodes": route,
                "timestamp": time.time()
            }
            
            return route
            
        except Exception as e:
            logger.error(f"Ошибка при поиске маршрута к {target_id}: {e}")
            return []
            
    async def _update_routing_table(self):
        """Обновляет таблицу маршрутизации"""
        try:
            # Очищаем устаревшие маршруты
            current_time = time.time()
            self.routing_table = {
                target_id: route
                for target_id, route in self.routing_table.items()
                if current_time - route["timestamp"] < self.refresh_interval
            }
            
            # Обновляем маршруты для всех известных узлов
            for bucket in self.k_buckets.values():
                for node in bucket:
                    if node.node_id not in self.routing_table:
                        await self.find_route(node.node_id)
                        
        except Exception as e:
            logger.error(f"Ошибка при обновлении таблицы маршрутизации: {e}")
            
    async def get_closest_nodes(self, target_id: str, count: int = 8) -> List[NodeInfo]:
        """
        Возвращает ближайшие узлы к целевому ID
        
        Args:
            target_id: Целевой ID
            count: Количество узлов
            
        Returns:
            List[NodeInfo]: Список ближайших узлов
        """
        try:
            # Получаем все узлы
            all_nodes = []
            for bucket in self.k_buckets.values():
                all_nodes.extend(bucket)
                
            if not all_nodes:
                return []
                
            # Сортируем по расстоянию
            all_nodes.sort(
                key=lambda node: self._calculate_distance(node.node_id, target_id)
            )
            
            return all_nodes[:count]
            
        except Exception as e:
            logger.error(f"Ошибка при получении ближайших узлов к {target_id}: {e}")
            return [] 
Модуль распределенной хеш-таблицы (DHT) для маршрутизации

Реализует Kademlia DHT для поиска узлов и маршрутов в сети.
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
import hashlib

logger = logging.getLogger("securetermchat.dht")

@dataclass
class NodeInfo:
    """Информация об узле в DHT"""
    node_id: str
    address: str
    port: int
    last_seen: float
    distance: int = 0  # Расстояние до текущего узла

class DHT:
    """Реализация Kademlia DHT"""
    
    def __init__(self, config):
        """
        Инициализирует DHT
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.node_id = self._generate_node_id()
        self.k_buckets = {}  # k-buckets для хранения узлов
        self.routing_table = {}  # Таблица маршрутизации
        self.max_bucket_size = config.get("max_bucket_size", 20)
        self.refresh_interval = config.get("refresh_interval", 3600)
        self.last_refresh = time.time()
        
    def _generate_node_id(self) -> str:
        """Генерирует ID узла"""
        return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()
        
    def _calculate_distance(self, node_id1: str, node_id2: str) -> int:
        """Вычисляет расстояние между узлами (XOR)"""
        return int(node_id1, 16) ^ int(node_id2, 16)
        
    def _get_bucket_index(self, node_id: str) -> int:
        """Возвращает индекс k-bucket для узла"""
        distance = self._calculate_distance(self.node_id, node_id)
        return distance.bit_length() - 1
        
    async def add_node(self, node_id: str, address: str, port: int) -> bool:
        """
        Добавляет узел в DHT
        
        Args:
            node_id: ID узла
            address: IP-адрес
            port: Порт
            
        Returns:
            bool: True если узел добавлен
        """
        try:
            bucket_index = self._get_bucket_index(node_id)
            
            if bucket_index not in self.k_buckets:
                self.k_buckets[bucket_index] = []
                
            # Проверяем, есть ли уже такой узел
            for node in self.k_buckets[bucket_index]:
                if node.node_id == node_id:
                    node.last_seen = time.time()
                    return True
                    
            # Если бакет полон, удаляем самый старый узел
            if len(self.k_buckets[bucket_index]) >= self.max_bucket_size:
                self.k_buckets[bucket_index].pop(0)
                
            # Добавляем новый узел
            node = NodeInfo(
                node_id=node_id,
                address=address,
                port=port,
                last_seen=time.time(),
                distance=self._calculate_distance(self.node_id, node_id)
            )
            self.k_buckets[bucket_index].append(node)
            
            # Обновляем таблицу маршрутизации
            await self._update_routing_table()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении узла {node_id}: {e}")
            return False
            
    async def remove_node(self, node_id: str) -> bool:
        """
        Удаляет узел из DHT
        
        Args:
            node_id: ID узла
            
        Returns:
            bool: True если узел удален
        """
        try:
            bucket_index = self._get_bucket_index(node_id)
            
            if bucket_index in self.k_buckets:
                self.k_buckets[bucket_index] = [
                    node for node in self.k_buckets[bucket_index]
                    if node.node_id != node_id
                ]
                
                # Обновляем таблицу маршрутизации
                await self._update_routing_table()
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при удалении узла {node_id}: {e}")
            return False
            
    async def find_node(self, target_id: str) -> Optional[NodeInfo]:
        """
        Ищет ближайший узел к целевому ID
        
        Args:
            target_id: Целевой ID
            
        Returns:
            Optional[NodeInfo]: Информация о найденном узле
        """
        try:
            # Получаем все узлы из k-buckets
            all_nodes = []
            for bucket in self.k_buckets.values():
                all_nodes.extend(bucket)
                
            if not all_nodes:
                return None
                
            # Сортируем узлы по расстоянию до целевого ID
            all_nodes.sort(
                key=lambda node: self._calculate_distance(node.node_id, target_id)
            )
            
            return all_nodes[0]
            
        except Exception as e:
            logger.error(f"Ошибка при поиске узла {target_id}: {e}")
            return None
            
    async def find_route(self, target_id: str) -> List[NodeInfo]:
        """
        Ищет маршрут до целевого узла
        
        Args:
            target_id: ID целевого узла
            
        Returns:
            List[NodeInfo]: Список узлов маршрута
        """
        try:
            # Проверяем кэш маршрутов
            if target_id in self.routing_table:
                route = self.routing_table[target_id]
                if time.time() - route["timestamp"] < self.refresh_interval:
                    return route["nodes"]
                    
            # Ищем ближайший узел
            next_node = await self.find_node(target_id)
            if not next_node:
                return []
                
            # Строим маршрут
            route = [next_node]
            current_id = next_node.node_id
            
            # Продолжаем поиск, пока не достигнем целевого узла
            # или не превысим максимальное количество хопов
            max_hops = self.config.get("max_route_hops", 5)
            for _ in range(max_hops):
                if current_id == target_id:
                    break
                    
                next_node = await self.find_node(target_id)
                if not next_node or next_node.node_id in [node.node_id for node in route]:
                    break
                    
                route.append(next_node)
                current_id = next_node.node_id
                
            # Кэшируем маршрут
            self.routing_table[target_id] = {
                "nodes": route,
                "timestamp": time.time()
            }
            
            return route
            
        except Exception as e:
            logger.error(f"Ошибка при поиске маршрута к {target_id}: {e}")
            return []
            
    async def _update_routing_table(self):
        """Обновляет таблицу маршрутизации"""
        try:
            # Очищаем устаревшие маршруты
            current_time = time.time()
            self.routing_table = {
                target_id: route
                for target_id, route in self.routing_table.items()
                if current_time - route["timestamp"] < self.refresh_interval
            }
            
            # Обновляем маршруты для всех известных узлов
            for bucket in self.k_buckets.values():
                for node in bucket:
                    if node.node_id not in self.routing_table:
                        await self.find_route(node.node_id)
                        
        except Exception as e:
            logger.error(f"Ошибка при обновлении таблицы маршрутизации: {e}")
            
    async def get_closest_nodes(self, target_id: str, count: int = 8) -> List[NodeInfo]:
        """
        Возвращает ближайшие узлы к целевому ID
        
        Args:
            target_id: Целевой ID
            count: Количество узлов
            
        Returns:
            List[NodeInfo]: Список ближайших узлов
        """
        try:
            # Получаем все узлы
            all_nodes = []
            for bucket in self.k_buckets.values():
                all_nodes.extend(bucket)
                
            if not all_nodes:
                return []
                
            # Сортируем по расстоянию
            all_nodes.sort(
                key=lambda node: self._calculate_distance(node.node_id, target_id)
            )
            
            return all_nodes[:count]
            
        except Exception as e:
            logger.error(f"Ошибка при получении ближайших узлов к {target_id}: {e}")
            return [] 
 