"""
Модуль для обхода NAT в P2P-сети

Реализует механизмы определения типа NAT и установки соединений через STUN/TURN/ICE.
"""

import asyncio
import logging
import socket
import struct
import random
from typing import Dict, List, Optional, Tuple
import aiohttp
import miniupnpc
from stun import stun

logger = logging.getLogger("securetermchat.nat_traversal")

class NATType:
    """Типы NAT"""
    OPEN = "open"
    FULL_CONE = "full_cone"
    RESTRICTED = "restricted"
    PORT_RESTRICTED = "port_restricted"
    SYMMETRIC = "symmetric"
    UNKNOWN = "unknown"

class NATTraversal:
    """Класс для обхода NAT"""
    
    def __init__(self, config):
        """
        Инициализирует модуль обхода NAT
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.stun_servers = config.get("stun_servers", [
            "stun.l.google.com:19302",
            "stun1.l.google.com:19302",
            "stun2.l.google.com:19302"
        ])
        self.turn_servers = config.get("turn_servers", [])
        self.nat_type = NATType.UNKNOWN
        self.public_ip = None
        self.public_port = None
        self.upnp = None
        self.ice_agent = None
        
    async def init(self):
        """Инициализирует модуль"""
        try:
            # Определяем тип NAT
            await self.detect_nat_type()
            
            # Настраиваем UPnP если нужно
            if self.nat_type != NATType.OPEN:
                await self.setup_upnp()
                
            # Настраиваем ICE если нужно
            if self.nat_type in [NATType.RESTRICTED, NATType.PORT_RESTRICTED, NATType.SYMMETRIC]:
                await self.setup_ice()
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации NAT traversal: {e}")
            raise
            
    async def detect_nat_type(self):
        """Определяет тип NAT через STUN"""
        for stun_server in self.stun_servers:
            try:
                host, port = stun_server.split(":")
                nat_type, external_ip, external_port = stun.get_nat_type(
                    host=host,
                    port=int(port),
                    source_ip="0.0.0.0",
                    source_port=0
                )
                
                if nat_type:
                    self.nat_type = nat_type
                    self.public_ip = external_ip
                    self.public_port = external_port
                    logger.info(f"Определен тип NAT: {nat_type}")
                    logger.info(f"Публичный адрес: {external_ip}:{external_port}")
                    return
                    
            except Exception as e:
                logger.warning(f"Ошибка при определении типа NAT через {stun_server}: {e}")
                continue
                
        logger.warning("Не удалось определить тип NAT")
        
    async def setup_upnp(self):
        """Настраивает UPnP для проброса портов"""
        try:
            self.upnp = miniupnpc.UPnP()
            self.upnp.discoverdelay = 200
            self.upnp.discover()
            self.upnp.selectigd()
            
            # Пробрасываем порт
            local_port = self.config.get("port", 8000)
            self.upnp.addportmapping(
                local_port, "TCP",
                self.upnp.lanaddr, local_port,
                "SecureTermChat", ""
            )
            
            logger.info(f"UPnP: проброшен порт {local_port}")
            
        except Exception as e:
            logger.error(f"Ошибка при настройке UPnP: {e}")
            
    async def setup_ice(self):
        """Настраивает ICE для обхода NAT"""
        try:
            # Создаем ICE агент
            self.ice_agent = {
                "stun_servers": self.stun_servers,
                "turn_servers": self.turn_servers,
                "candidates": []
            }
            
            # Собираем локальные кандидаты
            local_candidates = await self._gather_local_candidates()
            self.ice_agent["candidates"].extend(local_candidates)
            
            # Собираем STUN кандидаты
            stun_candidates = await self._gather_stun_candidates()
            self.ice_agent["candidates"].extend(stun_candidates)
            
            # Собираем TURN кандидаты если есть
            if self.turn_servers:
                turn_candidates = await self._gather_turn_candidates()
                self.ice_agent["candidates"].extend(turn_candidates)
                
            logger.info(f"ICE: собрано {len(self.ice_agent['candidates'])} кандидатов")
            
        except Exception as e:
            logger.error(f"Ошибка при настройке ICE: {e}")
            
    async def _gather_local_candidates(self) -> List[Dict]:
        """Собирает локальные ICE кандидаты"""
        candidates = []
        
        # Добавляем локальный адрес
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            candidates.append({
                "type": "host",
                "protocol": "udp",
                "ip": local_ip,
                "port": self.config.get("port", 8000),
                "priority": 2122260223  # Максимальный приоритет для хоста
            })
        except Exception as e:
            logger.warning(f"Ошибка при получении локального адреса: {e}")
            
        return candidates
        
    async def _gather_stun_candidates(self) -> List[Dict]:
        """Собирает STUN ICE кандидаты"""
        candidates = []
        
        for stun_server in self.stun_servers:
            try:
                host, port = stun_server.split(":")
                nat_type, external_ip, external_port = stun.get_nat_type(
                    host=host,
                    port=int(port),
                    source_ip="0.0.0.0",
                    source_port=0
                )
                
                if external_ip and external_port:
                    candidates.append({
                        "type": "srflx",
                        "protocol": "udp",
                        "ip": external_ip,
                        "port": external_port,
                        "priority": 16777215  # Приоритет для STUN
                    })
                    
            except Exception as e:
                logger.warning(f"Ошибка при получении STUN кандидата от {stun_server}: {e}")
                continue
                
        return candidates
        
    async def _gather_turn_candidates(self) -> List[Dict]:
        """Собирает TURN ICE кандидаты"""
        candidates = []
        
        for turn_server in self.turn_servers:
            try:
                # TODO: Реализовать получение TURN кандидатов
                pass
            except Exception as e:
                logger.warning(f"Ошибка при получении TURN кандидата от {turn_server}: {e}")
                continue
                
        return candidates
        
    async def get_connection_info(self) -> Dict:
        """Возвращает информацию о соединении"""
        return {
            "nat_type": self.nat_type,
            "public_ip": self.public_ip,
            "public_port": self.public_port,
            "ice_candidates": self.ice_agent["candidates"] if self.ice_agent else []
        }
        
    async def cleanup(self):
        """Очищает ресурсы"""
        if self.upnp:
            try:
                local_port = self.config.get("port", 8000)
                self.upnp.deleteportmapping(local_port, "TCP")
                logger.info(f"UPnP: удален проброс порта {local_port}")
            except Exception as e:
                logger.error(f"Ошибка при очистке UPnP: {e}") 