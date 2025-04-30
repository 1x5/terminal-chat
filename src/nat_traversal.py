"""
Модуль для обхода NAT и установки P2P соединений
"""

import asyncio
import logging
import socket
import json
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import miniupnpc
from .config import Config

logger = logging.getLogger("securetermchat.nat")

class NATType(Enum):
    """Типы NAT"""
    UNKNOWN = "unknown"
    OPEN = "open"
    UPNP = "upnp"
    BLOCKED = "blocked"

@dataclass
class ConnectionInfo:
    """Информация о соединении"""
    ip: str
    port: int
    nat_type: NATType

class NATTraversal:
    """
    Реализует механизмы для обхода NAT:
    - UPnP для проброса портов
    - Прямые соединения
    """
    
    def __init__(self, config: Config):
        """
        Инициализация
        
        Args:
            config: Конфигурация
        """
        self.config = config
        self.nat_type = NATType.UNKNOWN
        self.upnp = None
        self.local_ip = None
        self.local_port = None
        self.external_ip = None
        self.external_port = None
        self.connections: Dict[str, ConnectionInfo] = {}
        
    async def init(self):
        """Инициализация NAT traversal"""
        # Определяем локальный IP и порт
        self.local_ip = socket.gethostbyname(socket.gethostname())
        self.local_port = self.config.get("port", 8000)
        
        # Пробуем настроить UPnP
        if await self.setup_upnp():
            self.nat_type = NATType.UPNP
            self.external_ip = self.upnp.lanaddr
            self.external_port = self.local_port
        else:
            # Проверяем доступность из интернета
            if await self.check_direct_connection():
                self.nat_type = NATType.OPEN
                self.external_ip = self.local_ip
                self.external_port = self.local_port
            else:
                self.nat_type = NATType.BLOCKED
                
        logger.info(f"NAT type: {self.nat_type}")
        logger.info(f"Local: {self.local_ip}:{self.local_port}")
        if self.external_ip:
            logger.info(f"External: {self.external_ip}:{self.external_port}")
            
    async def setup_upnp(self) -> bool:
        """
        Настраивает UPnP для проброса портов
        
        Returns:
            bool: True если UPnP настроен успешно
        """
        try:
            self.upnp = miniupnpc.UPnP()
            self.upnp.discoverdelay = 200
            
            # Ищем UPnP устройства
            devices = self.upnp.discover()
            if devices == 0:
                logger.warning("No UPnP devices found")
                return False
                
            # Выбираем первое устройство
            self.upnp.selectigd()
            
            # Пробрасываем порт
            self.upnp.addportmapping(
                self.local_port, 'TCP',
                self.upnp.lanaddr, self.local_port,
                'SecureTermChat', ''
            )
            logger.info(f"Port {self.local_port} forwarded via UPnP")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to setup UPnP: {e}")
            self.upnp = None
            return False
            
    async def check_direct_connection(self) -> bool:
        """
        Проверяет доступность из интернета
        
        Returns:
            bool: True если порт доступен извне
        """
        try:
            # Создаем тестовый сервер
            server = await asyncio.start_server(
                lambda r, w: None,
                self.local_ip,
                self.local_port
            )
            
            # Пробуем подключиться к себе через внешний IP
            reader, writer = await asyncio.open_connection(
                self.local_ip,
                self.local_port
            )
            
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            
            return True
            
        except Exception as e:
            logger.debug(f"Direct connection test failed: {e}")
            return False
            
    def get_connection_info(self) -> Dict:
        """
        Возвращает информацию для установки соединения
        
        Returns:
            Dict: Информация о соединении
        """
        return {
            "nat_type": self.nat_type.value,
            "ip": self.external_ip or self.local_ip,
            "port": self.external_port or self.local_port
        }
        
    async def connect_to_peer(self, peer_id: str, peer_info: Dict) -> bool:
        """
        Устанавливает соединение с пиром
        
        Args:
            peer_id: ID пира
            peer_info: Информация о соединении пира
            
        Returns:
            bool: True если соединение установлено
        """
        try:
            # Создаем сокет
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            # Пробуем подключиться
            sock.connect((peer_info["ip"], peer_info["port"]))
            sock.close()
            
            # Сохраняем информацию о соединении
            self.connections[peer_id] = ConnectionInfo(
                ip=peer_info["ip"],
                port=peer_info["port"],
                nat_type=NATType(peer_info["nat_type"])
            )
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to connect to peer {peer_id}: {e}")
            return False
            
    async def cleanup(self):
        """Очистка ресурсов"""
        if self.upnp:
            try:
                # Удаляем проброс порта
                self.upnp.deleteportmapping(self.local_port, 'TCP')
                logger.info(f"UPnP port mapping removed for port {self.local_port}")
            except Exception as e:
                logger.warning(f"Failed to remove UPnP mapping: {e}")
                
    async def _cleanup_connection(self, peer_id: str):
        """
        Очищает ресурсы соединения
        
        Args:
            peer_id: ID пира
        """
        if peer_id in self.connections:
            del self.connections[peer_id]
 