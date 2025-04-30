"""
Модуль управления узлами в сети

Реализует регистрацию узлов, поддержание списка активных узлов и обновление маршрутов.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from src.crypto import CryptoManager
from src.dht import DHT, NodeInfo as DHTNodeInfo

logger = logging.getLogger("securetermchat.node_manager")

@dataclass
class NodeInfo:
    """Информация об узле в сети"""
    node_id: str
    public_key: str
    address: str
    last_seen: float
    is_active: bool = True
    routes: Dict[str, List[str]] = None  # node_id -> [hop1, hop2, ...]

class NodeManager:
    """Менеджер узлов в сети"""
    
    def __init__(self, config, crypto: CryptoManager):
        """
        Инициализирует менеджер узлов
        
        Args:
            config: Объект конфигурации
            crypto: Объект шифрования
        """
        self.config = config
        self.crypto = crypto
        self.nodes: Dict[str, NodeInfo] = {}
        self.active_nodes: Set[str] = set()
        self.dht = DHT(config)
        self._running = False
        self._monitor_task = None
        
    async def start(self) -> None:
        """Запускает менеджер узлов"""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_nodes())
        
    async def stop(self) -> None:
        """Останавливает менеджер узлов"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
    async def add_node(self, node_id: str, public_key: str, address: str) -> bool:
        """
        Добавляет новый узел
        
        Args:
            node_id: ID узла
            public_key: Публичный ключ
            address: Адрес узла
            
        Returns:
            bool: True если узел добавлен
        """
        try:
            # Добавляем в DHT
            host, port = address.split(":")
            await self.dht.add_node(node_id, host, int(port))
            
            # Добавляем в локальный список
            self.nodes[node_id] = NodeInfo(
                node_id=node_id,
                public_key=public_key,
                address=address,
                last_seen=time.time(),
                is_active=True,
                routes={}
            )
            self.active_nodes.add(node_id)
            
            logger.info(f"Добавлен узел {node_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении узла {node_id}: {e}")
            return False
            
    async def remove_node(self, node_id: str) -> bool:
        """
        Удаляет узел
        
        Args:
            node_id: ID узла
            
        Returns:
            bool: True если узел удален
        """
        try:
            # Удаляем из DHT
            await self.dht.remove_node(node_id)
            
            # Удаляем из локального списка
            if node_id in self.nodes:
                del self.nodes[node_id]
                self.active_nodes.discard(node_id)
                
            logger.info(f"Удален узел {node_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при удалении узла {node_id}: {e}")
            return False
            
    async def update_routes(self, node_id: str, routes: Dict[str, List[str]]) -> bool:
        """
        Обновляет маршруты для узла
        
        Args:
            node_id: ID узла
            routes: Словарь маршрутов (node_id -> [hop1, hop2, ...])
            
        Returns:
            bool: True если маршруты успешно обновлены
        """
        try:
            if node_id in self.nodes:
                self.nodes[node_id].routes = routes
                logger.info(f"Маршруты для узла {node_id} обновлены")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении маршрутов для узла {node_id}: {e}")
            return False
            
    async def get_route(self, target_node_id: str) -> Optional[List[str]]:
        """
        Возвращает маршрут до целевого узла
        
        Args:
            target_node_id: ID целевого узла
            
        Returns:
            Optional[List[str]]: Список узлов для маршрута или None если маршрут не найден
        """
        try:
            # Ищем маршрут через DHT
            route = await self.dht.find_route(target_node_id)
            if not route:
                return None
                
            # Преобразуем в список ID узлов
            return [node.node_id for node in route]
            
        except Exception as e:
            logger.error(f"Ошибка при поиске маршрута к {target_node_id}: {e}")
            return None
            
    async def _monitor_nodes(self):
        """Мониторит состояние узлов"""
        while self._running:
            try:
                current_time = time.time()
                
                # Проверяем активность узлов
                for node_id, node in list(self.nodes.items()):
                    if current_time - node.last_seen > 3600:  # 1 час
                        await self.remove_node(node_id)
                        
                # Обновляем маршруты
                for node_id in self.active_nodes:
                    if node_id in self.nodes:
                        route = await self.get_route(node_id)
                        if route:
                            await self.update_routes(node_id, {node_id: route})
                            
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в мониторинге узлов: {e}")
                await asyncio.sleep(5)
 
 