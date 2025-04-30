"""
Модуль обнаружения пиров для SecureTermChat

Реализует алгоритмы поиска и подключения к пирам в P2P сети.
"""

import os
import json
import time
import random
import socket
import logging
import asyncio
from typing import Dict, List, Tuple, Optional, Any, Set
import aiohttp

from src.p2p_connection import NodeConnection, connect_to_node

logger = logging.getLogger("securetermchat.peer_discovery")

class PeerDiscovery:
    """
    Класс для обнаружения пиров в сети
    """
    
    def __init__(self, config, network):
        """
        Инициализирует модуль обнаружения пиров
        
        Args:
            config: Объект конфигурации
            network: Объект сети
        """
        self.config = config
        self.network = network
        self.known_peers = set()
        self.is_running = False
        self.discovery_task = None
        self.discovery_interval = 60  # 60 seconds between discovery attempts
        self.max_peers = 10  # Maximum number of peers to maintain
        
    async def start(self):
        """Start peer discovery service"""
        if self.is_running:
            return
            
        self.is_running = True
        self.discovery_task = asyncio.create_task(self._discovery_loop())
        logger.info("Peer discovery service started")
        
    async def stop(self):
        """Stop peer discovery service"""
        if not self.is_running:
            return
            
        self.is_running = False
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
        logger.info("Peer discovery service stopped")
        
    async def _discovery_loop(self):
        """Main discovery loop"""
        while self.is_running:
            try:
                await self._discover_peers()
                await asyncio.sleep(self.discovery_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
                
    async def _discover_peers(self):
        """Discover new peers"""
        if len(self.known_peers) >= self.max_peers:
            return
            
        try:
            # Try bootstrap nodes first
            for bootstrap_node in self.config.bootstrap_nodes:
                if bootstrap_node not in self.known_peers:
                    try:
                        await self._connect_to_peer(bootstrap_node)
                    except Exception as e:
                        logger.warning(f"Failed to connect to bootstrap node {bootstrap_node}: {e}")
                        
            # Then try known peers
            for peer in list(self.known_peers):
                try:
                    await self._get_peer_list(peer)
                except Exception as e:
                    logger.warning(f"Failed to get peer list from {peer}: {e}")
                    self.known_peers.remove(peer)
        except Exception as e:
            logger.error(f"Error discovering peers: {e}")
            
    async def _connect_to_peer(self, peer_address):
        """Connect to a peer"""
        if peer_address in self.known_peers:
            return
            
        try:
            await self.network.connect(peer_address)
            self.known_peers.add(peer_address)
            logger.info(f"Connected to peer: {peer_address}")
        except Exception as e:
            logger.warning(f"Failed to connect to peer {peer_address}: {e}")
            raise
            
    async def _get_peer_list(self, peer_address):
        """Get list of peers from a node"""
        try:
            response = await self.network.send_message(peer_address, {
                "type": "get_peers"
            })
            
            if response and "peers" in response:
                for peer in response["peers"]:
                    if peer not in self.known_peers and len(self.known_peers) < self.max_peers:
                        await self._connect_to_peer(peer)
        except Exception as e:
            logger.warning(f"Failed to get peer list from {peer_address}: {e}")
            raise
    
    def get_active_peers(self) -> List[str]:
        """
        Возвращает список активных пиров
        
        Returns:
            List[str]: Список идентификаторов активных пиров
        """
        return list(self.known_peers)
    
    def get_active_connections_count(self) -> int:
        """
        Возвращает количество активных соединений
        
        Returns:
            int: Количество активных соединений
        """
        return len(self.known_peers)
    
    def get_known_peers_count(self) -> int:
        """
        Возвращает количество известных пиров
        
        Returns:
            int: Количество известных пиров
        """
        return len(self.known_peers)
    
    def select_random_peers(self, count: int) -> List[str]:
        """
        Выбирает случайные активные соединения с пирами
        
        Args:
            count (int): Желаемое количество пиров
            
        Returns:
            List[str]: Список идентификаторов выбранных пиров
        """
        if not self.known_peers:
            return []
        
        peer_ids = list(self.known_peers)
        selected_count = min(count, len(peer_ids))
        
        if selected_count == 0:
            return []
            
        selected_ids = random.sample(peer_ids, selected_count)
        return selected_ids
    
    async def load_bootstrap_peers(self):
        """Загружает начальный список пиров с bootstrap-серверов"""
        bootstrap_nodes = self.config.get_bootstrap_nodes()
        
        if not bootstrap_nodes:
            logger.warning("Список начальных узлов пуст")
            return
            
        logger.info(f"Загрузка списка пиров с bootstrap-узлов: {bootstrap_nodes}")
        
        for node_address in bootstrap_nodes:
            try:
                # Разбиваем адрес на хост и порт
                host, port_str = node_address.split(":")
                port = int(port_str)
                
                # Для простоты добавляем bootstrap-узлы в список известных пиров
                # В реальной реализации здесь должен быть запрос к API для получения списка пиров
                self.known_peers.add(f"{host}:{port}")
                
            except Exception as e:
                logger.warning(f"Ошибка при загрузке пиров с {node_address}: {e}")
    
    async def update_peers(self, active_peers: List[str]):
        """
        Обновляет информацию о пирах
        
        Args:
            active_peers (List[str]): Список ID активных пиров
        """
        self.known_peers.update(active_peers)
    
    async def get_nodes(self, limit: int = 10) -> List[Dict]:
        """
        Возвращает список доступных узлов
        
        Args:
            limit (int): Максимальное количество узлов
            
        Returns:
            List[Dict]: Список узлов с информацией
        """
        # Фильтруем и сортируем узлы по времени последнего контакта
        peers = sorted(
            [{"node_id": node_id} for node_id in self.known_peers],
            key=lambda x: x["node_id"],
            reverse=True
        )
        
        # Ограничиваем количество
        return peers[:limit]
    
    def select_random_peers(self, count: int) -> List[Dict]:
        """
        Выбирает случайные узлы из списка известных пиров
        
        Args:
            count (int): Количество узлов для выбора
            
        Returns:
            List[Dict]: Список выбранных узлов
        """
        # Преобразуем множество пиров в список
        peers = list(self.known_peers)
        
        # Если у нас недостаточно пиров, возвращаем все имеющиеся
        if len(peers) <= count:
            return [{"node_id": peer} for peer in peers]
            
        # Выбираем случайные узлы
        selected_peers = random.sample(peers, count)
        return [{"node_id": peer} for peer in selected_peers]
    
    def get_peer_count(self) -> int:
        """
        Возвращает количество известных пиров
        
        Returns:
            int: Количество пиров
        """
        return len(self.known_peers) 