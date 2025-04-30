import asyncio
import random
import socket
import struct
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
import logging
import time
from collections import defaultdict
import aiohttp
import json

logger = logging.getLogger(__name__)

@dataclass
class PeerInfo:
    node_id: str
    address: str
    port: int
    public_key: str
    last_seen: float
    services: Set[str] = None
    latency: float = float('inf')
    success_rate: float = 1.0
    reputation: float = 1.0
    connection_attempts: int = 0
    last_error: Optional[str] = None
    is_bootstrap: bool = False

class PeerDiscovery:
    def __init__(self, node_id: str, port: int, bootstrap_nodes: List[Tuple[str, int]] = None):
        self.node_id = node_id
        self.port = port
        self.bootstrap_nodes = bootstrap_nodes or []
        self.known_peers: Dict[str, PeerInfo] = {}
        self.active_peers: Set[str] = set()
        self.discovery_task: Optional[asyncio.Task] = None
        self.running = False
        self.discovery_cache: Dict[str, Tuple[float, List[PeerInfo]]] = {}
        self.cache_ttl = 300
        self.service_peers: Dict[str, List[PeerInfo]] = defaultdict(list)
        self.last_discovery_time: Dict[str, float] = {}
        self.min_discovery_interval = 60
        self.max_connection_attempts = 3
        self.connection_timeout = 5
        self.reputation_decay = 0.1
        self.session: Optional[aiohttp.ClientSession] = None
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.max_errors = 5
        self.error_reset_time = 3600  # 1 час

    async def start(self):
        """Start the peer discovery service"""
        if self.running:
            return
            
        self.running = True
        self.session = aiohttp.ClientSession()
        self.discovery_task = asyncio.create_task(self._discovery_loop())
        logger.info("Peer discovery service started")
        
    async def stop(self):
        """Stop the peer discovery service"""
        if not self.running:
            return
            
        self.running = False
        
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
            finally:
                self.discovery_task = None
                
        if self.session:
            await self.session.close()
            self.session = None
                
        logger.info("Peer discovery service stopped")

    async def _discovery_loop(self):
        """Main discovery loop with improved error handling and metrics"""
        while self.running:
            try:
                if not self.known_peers:
                    await self._bootstrap()
                    
                # Параллельное выполнение задач с таймаутами
                tasks = [
                    asyncio.create_task(self._discover_peers()),
                    asyncio.create_task(self._cleanup_peers()),
                    asyncio.create_task(self._update_peer_metrics()),
                    asyncio.create_task(self._check_network_health())
                ]
                
                # Ждем завершения всех задач с таймаутом
                await asyncio.wait(tasks, timeout=55)
                
                # Очищаем невыполненные задачи
                for task in tasks:
                    if not task.done():
                        task.cancel()
                
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(5)

    async def _check_network_health(self):
        """Проверка здоровья сети и восстановление соединений"""
        current_time = time.time()
        
        # Проверяем количество активных пиров
        if len(self.active_peers) < len(self.bootstrap_nodes):
            logger.warning("Low number of active peers, attempting to reconnect to bootstrap nodes")
            await self._bootstrap()
            
        # Проверяем и сбрасываем счетчики ошибок
        for peer_id, error_count in list(self.error_counts.items()):
            if current_time - self.last_discovery_time.get(peer_id, 0) > self.error_reset_time:
                self.error_counts[peer_id] = 0
                
        # Проверяем репутацию пиров
        for peer in self.known_peers.values():
            if peer.reputation < 0.3 and not peer.is_bootstrap:
                logger.warning(f"Low reputation peer detected: {peer.node_id}")
                await self._reconnect_peer(peer)

    async def _reconnect_peer(self, peer: PeerInfo):
        """Попытка переподключения к пиру с низкой репутацией"""
        try:
            if peer.connection_attempts >= self.max_connection_attempts:
                logger.info(f"Max connection attempts reached for peer {peer.node_id}")
                return
                
            peer.connection_attempts += 1
            await self._bootstrap_node(peer.address, peer.port)
            
        except Exception as e:
            logger.error(f"Reconnection failed for peer {peer.node_id}: {e}")
            peer.last_error = str(e)
            self.error_counts[peer.node_id] += 1

    async def _discover_peers(self):
        """Discover new peers with improved routing"""
        current_time = time.time()
        
        # Выбираем пиров для запроса с учетом их метрик и репутации
        candidates = [
            peer for peer in self.known_peers.values()
            if (current_time - self.last_discovery_time.get(peer.node_id, 0) >= self.min_discovery_interval
                and peer.reputation > 0.5
                and self.error_counts[peer.node_id] < self.max_errors)
        ]
        
        if not candidates:
            return
            
        # Сортируем по репутации, успешности и латентности
        candidates.sort(key=lambda p: (p.reputation, p.success_rate, -p.latency))
        sample_size = min(5, len(candidates))
        sample_peers = candidates[:sample_size]
        
        tasks = []
        for peer in sample_peers:
            tasks.append(self._discover_from_peer(peer))
            self.last_discovery_time[peer.node_id] = current_time
            
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _discover_from_peer(self, peer: PeerInfo):
        """Discover peers from a single peer with improved error handling"""
        try:
            async with self.session.get(
                f"http://{peer.address}:{peer.port}/peers",
                timeout=self.connection_timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    for new_peer_data in data.get("peers", []):
                        await self._process_peer_data(new_peer_data)
                    peer.success_rate = min(1.0, peer.success_rate + 0.1)
                    peer.reputation = min(1.0, peer.reputation + 0.05)
                else:
                    raise Exception(f"HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Discovery failed for {peer.address}:{peer.port}: {e}")
            peer.success_rate = max(0.0, peer.success_rate - 0.2)
            peer.reputation = max(0.0, peer.reputation - 0.1)
            peer.last_error = str(e)
            self.error_counts[peer.node_id] += 1

    async def _process_peer_data(self, data: Dict) -> Optional[PeerInfo]:
        """Process peer data with validation"""
        try:
            required_fields = ["node_id", "address", "port", "public_key"]
            if not all(field in data for field in required_fields):
                logger.warning("Invalid peer data: missing required fields")
                return None
                
            peer = PeerInfo(
                node_id=data["node_id"],
                address=data["address"],
                port=data["port"],
                public_key=data["public_key"],
                last_seen=time.time(),
                services=set(data.get("services", [])),
                latency=data.get("latency", float("inf")),
                success_rate=data.get("success_rate", 1.0),
                reputation=data.get("reputation", 1.0)
            )
            
            # Валидация данных пира
            if not self._validate_peer(peer):
                return None
                
            self.known_peers[peer.node_id] = peer
            self.active_peers.add(peer.node_id)
            
            # Обновляем индекс по сервисам
            for service in peer.services:
                self.service_peers[service].append(peer)
                
            return peer
            
        except Exception as e:
            logger.error(f"Error processing peer data: {e}")
            return None

    def _validate_peer(self, peer: PeerInfo) -> bool:
        """Validate peer data"""
        try:
            # Проверка формата node_id
            if not isinstance(peer.node_id, str) or len(peer.node_id) != 40:
                return False
                
            # Проверка IP-адреса
            try:
                socket.inet_aton(peer.address)
            except socket.error:
                return False
                
            # Проверка порта
            if not isinstance(peer.port, int) or not (0 < peer.port < 65536):
                return False
                
            # Проверка публичного ключа
            if not isinstance(peer.public_key, str) or len(peer.public_key) != 64:
                return False
                
            return True
            
        except Exception:
            return False

    async def _update_peer_metrics(self):
        """Update peer metrics with reputation system"""
        current_time = time.time()
        for peer in self.known_peers.values():
            # Уменьшаем репутацию и успешность со временем
            time_diff = current_time - peer.last_seen
            if time_diff > 300:  # 5 минут
                decay = min(0.1, time_diff / 3600)  # Максимум 10% за час
                peer.success_rate = max(0.0, peer.success_rate - decay)
                peer.reputation = max(0.0, peer.reputation - decay)
                
            # Сбрасываем счетчик ошибок для стабильных пиров
            if peer.reputation > 0.8 and time_diff > self.error_reset_time:
                self.error_counts[peer.node_id] = 0

    def get_peers(self, service: Optional[str] = None, min_reputation: float = 0.5) -> List[PeerInfo]:
        """Get list of known peers with reputation filtering"""
        current_time = time.time()
        
        if service:
            # Проверяем кэш
            cache_key = f"service:{service}:{min_reputation}"
            if cache_key in self.discovery_cache:
                cache_time, cached_peers = self.discovery_cache[cache_key]
                if current_time - cache_time < self.cache_ttl:
                    return cached_peers
                    
            # Получаем из индекса с фильтрацией по репутации
            peers = [
                peer for peer in self.service_peers.get(service, [])
                if peer.reputation >= min_reputation
            ]
            # Кэшируем результат
            self.discovery_cache[cache_key] = (current_time, peers)
            return peers
            
        # Возвращаем всех пиров с достаточной репутацией
        return [
            peer for peer in self.known_peers.values()
            if peer.reputation >= min_reputation
        ]

    def get_network_stats(self) -> Dict:
        """Get network statistics"""
        return {
            "total_peers": len(self.known_peers),
            "active_peers": len(self.active_peers),
            "services": {
                service: len(peers)
                for service, peers in self.service_peers.items()
            },
            "reputation_stats": {
                "high": len([p for p in self.known_peers.values() if p.reputation > 0.8]),
                "medium": len([p for p in self.known_peers.values() if 0.5 <= p.reputation <= 0.8]),
                "low": len([p for p in self.known_peers.values() if p.reputation < 0.5])
            },
            "error_counts": dict(self.error_counts)
        }

    async def _bootstrap(self):
        """Connect to bootstrap nodes to get initial peers"""
        tasks = []
        for address, port in self.bootstrap_nodes:
            tasks.append(self._bootstrap_node(address, port))
            
        await asyncio.gather(*tasks)
                
    async def _bootstrap_node(self, address: str, port: int):
        """Bootstrap single node"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            
            start_time = time.time()
            message = struct.pack("!20s", self.node_id.encode())
            sock.sendto(message, (address, port))
            
            data, addr = sock.recvfrom(1024)
            latency = time.time() - start_time
            
            peer = self._process_peer_response(data, addr)
            if peer:
                peer.latency = latency
                
        except Exception as e:
            logger.error(f"Bootstrap failed for {address}:{port}: {e}")
        finally:
            sock.close()
                
    def _process_peer_response(self, data: bytes, addr: Tuple[str, int]) -> Optional[PeerInfo]:
        """Process peer discovery response"""
        try:
            node_id = data[:20].hex()
            public_key = data[20:52].hex()
            services = struct.unpack("!I", data[52:56])[0]
            port = struct.unpack("!H", data[56:58])[0]
            
            peer = PeerInfo(
                node_id=node_id,
                address=addr[0],
                port=port,
                public_key=public_key,
                last_seen=time.time(),
                services=set()
            )
            
            if services & 0x01:
                peer.services.add("chat")
            if services & 0x02:
                peer.services.add("storage")
            if services & 0x04:
                peer.services.add("relay")
                
            self.known_peers[node_id] = peer
            self.active_peers.add(node_id)
            
            # Обновляем индекс по сервисам
            for service in peer.services:
                self.service_peers[service].append(peer)
                
            return peer
            
        except Exception as e:
            logger.error(f"Error processing peer response: {e}")
            return None
            
    async def _cleanup_peers(self):
        """Remove inactive peers"""
        current_time = time.time()
        inactive_peers = [
            node_id for node_id, peer in self.known_peers.items()
            if current_time - peer.last_seen > 3600
        ]
        
        for node_id in inactive_peers:
            peer = self.known_peers[node_id]
            # Удаляем из индекса сервисов
            for service in peer.services:
                self.service_peers[service].remove(peer)
            del self.known_peers[node_id]
            self.active_peers.discard(node_id)
            
    def add_peer(self, peer: PeerInfo) -> bool:
        """Add a new peer manually"""
        try:
            self.known_peers[peer.node_id] = peer
            self.active_peers.add(peer.node_id)
            # Обновляем индекс сервисов
            for service in peer.services:
                self.service_peers[service].append(peer)
            return True
        except Exception as e:
            logger.error(f"Error adding peer: {e}")
            return False
            
    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer"""
        try:
            if node_id in self.known_peers:
                peer = self.known_peers[node_id]
                # Удаляем из индекса сервисов
                for service in peer.services:
                    self.service_peers[service].remove(peer)
                del self.known_peers[node_id]
                self.active_peers.discard(node_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing peer: {e}")
            return False 
    def get_peers(self, service: Optional[str] = None, min_reputation: float = 0.5) -> List[PeerInfo]:
        """Get list of known peers with reputation filtering"""
        current_time = time.time()
        
        if service:
            # Проверяем кэш
            cache_key = f"service:{service}:{min_reputation}"
            if cache_key in self.discovery_cache:
                cache_time, cached_peers = self.discovery_cache[cache_key]
                if current_time - cache_time < self.cache_ttl:
                    return cached_peers
                    
            # Получаем из индекса с фильтрацией по репутации
            peers = [
                peer for peer in self.service_peers.get(service, [])
                if peer.reputation >= min_reputation
            ]
            # Кэшируем результат
            self.discovery_cache[cache_key] = (current_time, peers)
            return peers
            
        # Возвращаем всех пиров с достаточной репутацией
        return [
            peer for peer in self.known_peers.values()
            if peer.reputation >= min_reputation
        ]

    def get_network_stats(self) -> Dict:
        """Get network statistics"""
        return {
            "total_peers": len(self.known_peers),
            "active_peers": len(self.active_peers),
            "services": {
                service: len(peers)
                for service, peers in self.service_peers.items()
            },
            "reputation_stats": {
                "high": len([p for p in self.known_peers.values() if p.reputation > 0.8]),
                "medium": len([p for p in self.known_peers.values() if 0.5 <= p.reputation <= 0.8]),
                "low": len([p for p in self.known_peers.values() if p.reputation < 0.5])
            },
            "error_counts": dict(self.error_counts)
        }

    async def _bootstrap(self):
        """Connect to bootstrap nodes to get initial peers"""
        tasks = []
        for address, port in self.bootstrap_nodes:
            tasks.append(self._bootstrap_node(address, port))
            
        await asyncio.gather(*tasks)
                
    async def _bootstrap_node(self, address: str, port: int):
        """Bootstrap single node"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            
            start_time = time.time()
            message = struct.pack("!20s", self.node_id.encode())
            sock.sendto(message, (address, port))
            
            data, addr = sock.recvfrom(1024)
            latency = time.time() - start_time
            
            peer = self._process_peer_response(data, addr)
            if peer:
                peer.latency = latency
                
        except Exception as e:
            logger.error(f"Bootstrap failed for {address}:{port}: {e}")
        finally:
            sock.close()
                
    def _process_peer_response(self, data: bytes, addr: Tuple[str, int]) -> Optional[PeerInfo]:
        """Process peer discovery response"""
        try:
            node_id = data[:20].hex()
            public_key = data[20:52].hex()
            services = struct.unpack("!I", data[52:56])[0]
            port = struct.unpack("!H", data[56:58])[0]
            
            peer = PeerInfo(
                node_id=node_id,
                address=addr[0],
                port=port,
                public_key=public_key,
                last_seen=time.time(),
                services=set()
            )
            
            if services & 0x01:
                peer.services.add("chat")
            if services & 0x02:
                peer.services.add("storage")
            if services & 0x04:
                peer.services.add("relay")
                
            self.known_peers[node_id] = peer
            self.active_peers.add(node_id)
            
            # Обновляем индекс по сервисам
            for service in peer.services:
                self.service_peers[service].append(peer)
                
            return peer
            
        except Exception as e:
            logger.error(f"Error processing peer response: {e}")
            return None
            
    async def _cleanup_peers(self):
        """Remove inactive peers"""
        current_time = time.time()
        inactive_peers = [
            node_id for node_id, peer in self.known_peers.items()
            if current_time - peer.last_seen > 3600
        ]
        
        for node_id in inactive_peers:
            peer = self.known_peers[node_id]
            # Удаляем из индекса сервисов
            for service in peer.services:
                self.service_peers[service].remove(peer)
            del self.known_peers[node_id]
            self.active_peers.discard(node_id)
            
    def add_peer(self, peer: PeerInfo) -> bool:
        """Add a new peer manually"""
        try:
            self.known_peers[peer.node_id] = peer
            self.active_peers.add(peer.node_id)
            # Обновляем индекс сервисов
            for service in peer.services:
                self.service_peers[service].append(peer)
            return True
        except Exception as e:
            logger.error(f"Error adding peer: {e}")
            return False
            
    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer"""
        try:
            if node_id in self.known_peers:
                peer = self.known_peers[node_id]
                # Удаляем из индекса сервисов
                for service in peer.services:
                    self.service_peers[service].remove(peer)
                del self.known_peers[node_id]
                self.active_peers.discard(node_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing peer: {e}")
            return False 