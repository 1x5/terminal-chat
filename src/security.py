"""
Модуль безопасности для проверки подлинности узлов, защиты от атак и валидации сообщений
"""

import time
import logging
import hashlib
import asyncio
from typing import Dict, Optional, Tuple, Set, List
from dataclasses import dataclass
from src.crypto import CryptoManager

logger = logging.getLogger("securetermchat.security")

@dataclass
class SecurityConfig:
    """Конфигурация безопасности"""
    max_connections_per_ip: int = 5
    connection_timeout: float = 60.0
    max_message_size: int = 1024 * 1024  # 1MB
    rate_limit_window: float = 60.0  # 1 минута
    max_messages_per_window: int = 100
    challenge_timeout: float = 30.0
    min_reputation: float = 0.5
    reputation_decay: float = 0.1
    sybil_threshold: int = 3

class SecurityManager:
    """Менеджер безопасности"""
    
    def __init__(self, crypto: CryptoManager, config: SecurityConfig):
        self.crypto = crypto
        self.config = config
        self.challenges: Dict[str, str] = {}
        self.authenticated_nodes: Set[str] = set()
        self.connections: Dict[str, List[float]] = {}  # Changed to List[float] to track multiple connections
        self.message_counts: Dict[str, int] = {}
        self.last_message_time: Dict[str, float] = {}
        self.node_reputation: Dict[str, float] = {}
        self.last_reputation_update: Dict[str, float] = {}
        self.blocked_nodes: Set[str] = set()
        self.sybil_nodes: Set[str] = set()
        self.cleanup_task = None
        
    async def init(self):
        """Инициализирует асинхронные ресурсы"""
        self._start_cleanup()
        
    def _start_cleanup(self):
        """Запускает задачу очистки"""
        try:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        except RuntimeError:
            # Если нет event loop, пропускаем создание задачи
            pass
        
    async def _cleanup_loop(self):
        """Цикл очистки устаревших данных"""
        while True:
            try:
                await self.cleanup()
                await asyncio.sleep(60)  # Проверка каждую минуту
            except Exception as e:
                logger.error(f"Ошибка в цикле очистки: {e}")
        
    async def generate_challenge(self, node_id: str) -> str:
        """Генерирует вызов для аутентификации узла"""
        challenge = self.crypto.generate_random_bytes(32).hex()
        self.challenges[node_id] = challenge
        self.last_reputation_update[node_id] = time.time()
        return challenge
        
    async def verify_challenge(self, node_id: str, response: str) -> bool:
        """Проверяет ответ на вызов"""
        if node_id not in self.challenges:
            return False
            
        current_time = time.time()
        challenge = self.challenges[node_id]
        
        # Проверяем таймаут
        if current_time - self.last_reputation_update.get(node_id, 0) > self.config.challenge_timeout:
            del self.challenges[node_id]
            return False
            
        expected = hashlib.sha256(challenge.encode()).hexdigest()
        
        if response == expected:
            self.authenticated_nodes.add(node_id)
            self.last_reputation_update[node_id] = current_time
            del self.challenges[node_id]
            return True
            
        return False
        
    async def is_node_authenticated(self, node_id: str) -> bool:
        """Проверяет аутентификацию узла"""
        if node_id not in self.authenticated_nodes:
            return False
            
        # Проверяем таймаут аутентификации
        current_time = time.time()
        if current_time - self.last_reputation_update.get(node_id, 0) > self.config.connection_timeout:
            self.authenticated_nodes.discard(node_id)
            return False
            
        return True
        
    async def check_connection_limit(self, ip: str) -> bool:
        """Проверяет лимит подключений для IP"""
        if ip in self.blocked_nodes:
            return False
            
        current_time = time.time()
        
        # Очищаем устаревшие подключения
        if ip in self.connections:
            self.connections[ip] = [
                timestamp for timestamp in self.connections[ip]
                if current_time - timestamp < self.config.connection_timeout
            ]
        
        # Считаем текущие подключения для IP
        current_connections = len(self.connections.get(ip, []))
        
        # Проверяем лимит
        if current_connections >= self.config.max_connections_per_ip:
            logger.warning(f"Превышен лимит подключений для {ip}")
            self.sybil_nodes.add(ip)
            self.last_reputation_update[ip] = current_time
            return False
            
        # Добавляем новое подключение
        if ip not in self.connections:
            self.connections[ip] = []
        self.connections[ip].append(current_time)
        return True

    async def remove_connection(self, ip: str):
        """Удаляет подключение"""
        if ip in self.connections and self.connections[ip]:
            self.connections[ip].pop()

    def is_sybil_node(self, ip: str) -> bool:
        """Проверяет, является ли узел потенциальным Sybil"""
        current_time = time.time()
        if ip not in self.sybil_nodes:
            return False
            
        # Проверяем, не устарел ли статус Sybil
        if current_time - self.last_reputation_update.get(ip, 0) > self.config.connection_timeout:
            self.sybil_nodes.discard(ip)
            return False
            
        return True

    def get_node_reputation(self, node_id: str) -> float:
        """Получает репутацию узла"""
        if node_id not in self.node_reputation:
            self.node_reputation[node_id] = 1.0
            self.last_reputation_update[node_id] = time.time()
            return 1.0
            
        # Применяем затухание репутации
        current_time = time.time()
        time_diff = current_time - self.last_reputation_update[node_id]
        decay = self.config.reputation_decay * time_diff
        
        reputation = max(
            self.config.min_reputation,
            self.node_reputation[node_id] - decay
        )
        
        self.node_reputation[node_id] = reputation
        self.last_reputation_update[node_id] = current_time
        
        # Округляем до 1.0 если очень близко к 1.0
        return 1.0 if reputation > 0.9999 else reputation

    async def update_reputation(self, node_id: str, success: bool):
        """Обновляет репутацию узла"""
        delta = 0.1 if success else -0.2
        current_reputation = self.get_node_reputation(node_id)
        new_reputation = max(
            self.config.min_reputation,
            min(1.0, current_reputation + delta)  # Ограничиваем максимальную репутацию
        )
        self.node_reputation[node_id] = new_reputation
        self.last_reputation_update[node_id] = time.time()
        
        logger.debug(f"Updating reputation for {node_id}: {current_reputation} -> {new_reputation} (success={success})")
        
        # Если репутация улучшилась и стала выше минимальной, убираем из Sybil-узлов
        if success and new_reputation > self.config.min_reputation and node_id in self.sybil_nodes:
            logger.debug(f"Removing {node_id} from Sybil nodes due to improved reputation")
            self.sybil_nodes.remove(node_id)
            if node_id in self.connections:
                self.connections[node_id] = []

    async def block_node(self, node_id: str):
        """Блокирует узел"""
        self.blocked_nodes.add(node_id)

    async def unblock_node(self, node_id: str):
        """Разблокирует узел"""
        self.blocked_nodes.discard(node_id)

    def is_node_blocked(self, node_id: str) -> bool:
        """Проверяет, заблокирован ли узел"""
        return node_id in self.blocked_nodes

    async def check_rate_limit(self, ip: str) -> bool:
        """Проверяет лимит сообщений"""
        current_time = time.time()
        
        # Очищаем старые счетчики
        if ip in self.last_message_time:
            if current_time - self.last_message_time[ip] > self.config.rate_limit_window:
                self.message_counts[ip] = 0
                self.last_message_time[ip] = current_time
        
        # Проверяем лимит
        if ip not in self.message_counts:
            self.message_counts[ip] = 0
            self.last_message_time[ip] = current_time
        
        if self.message_counts[ip] >= self.config.max_messages_per_window:
            return False
        
        self.message_counts[ip] += 1
        return True

    async def validate_message(self, message: bytes) -> bool:
        """Проверяет валидность сообщения"""
        return len(message) <= self.config.max_message_size

    async def cleanup(self):
        """Очищает устаревшие данные"""
        current_time = time.time()
        
        # Очищаем устаревшие вызовы
        self.challenges = {
            node_id: challenge for node_id, challenge in self.challenges.items()
            if current_time - self.last_reputation_update.get(node_id, 0) < self.config.challenge_timeout
        }
        
        # Очищаем устаревшие подключения
        for ip in list(self.connections.keys()):
            old_len = len(self.connections[ip])
            self.connections[ip] = [
                timestamp for timestamp in self.connections[ip]
                if current_time - timestamp < self.config.connection_timeout
            ]
            # Если количество подключений уменьшилось, обновляем репутацию
            if len(self.connections[ip]) < old_len:
                self.last_reputation_update[ip] = current_time
            
            if not self.connections[ip]:
                del self.connections[ip]
                # Если нет активных подключений, убираем из Sybil-узлов
                if ip in self.sybil_nodes:
                    self.sybil_nodes.remove(ip)
        
        # Очищаем устаревшие счетчики сообщений
        self.message_counts = {
            ip: count for ip, count in self.message_counts.items()
            if current_time - self.last_message_time.get(ip, 0) < self.config.rate_limit_window
        }
        
        # Очищаем устаревшие Sybil-узлы и их подключения
        for node_id in list(self.sybil_nodes):
            if current_time - self.last_reputation_update.get(node_id, 0) >= self.config.connection_timeout:
                self.sybil_nodes.remove(node_id)
                if node_id in self.connections:
                    self.connections[node_id] = []
        
        # Очищаем устаревшие аутентифицированные узлы
        self.authenticated_nodes = {
            node_id for node_id in self.authenticated_nodes
            if current_time - self.last_reputation_update.get(node_id, 0) < self.config.connection_timeout
        }

    async def check_sybil_attack(self, node_id: str) -> bool:
        """Проверяет наличие Sybil-атаки"""
        # Проверяем, не заблокирован ли узел
        if node_id in self.blocked_nodes:
            logger.debug(f"{node_id} is blocked")
            return False
            
        # Проверяем таймаут для Sybil-узлов
        current_time = time.time()
        if node_id in self.sybil_nodes:
            if current_time - self.last_reputation_update.get(node_id, 0) >= self.config.connection_timeout:
                logger.debug(f"Removing {node_id} from Sybil nodes due to timeout")
                self.sybil_nodes.remove(node_id)
                if node_id in self.connections:
                    self.connections[node_id] = []
            else:
                logger.debug(f"{node_id} is still marked as Sybil")
                return False
            
        # Проверяем репутацию
        reputation = self.get_node_reputation(node_id)
        logger.debug(f"Current reputation for {node_id}: {reputation}")
        if reputation <= self.config.min_reputation:  # Изменено с < на <=
            # Если репутация слишком низкая, помечаем как Sybil
            logger.debug(f"Marking {node_id} as Sybil due to low reputation")
            self.sybil_nodes.add(node_id)
            self.last_reputation_update[node_id] = current_time
            return False
            
        # Проверяем количество подключений
        connections = len([
            timestamp for timestamp in self.connections.get(node_id, [])
            if current_time - timestamp < self.config.connection_timeout
        ])
        logger.debug(f"Active connections for {node_id}: {connections}")
                         
        if connections >= self.config.sybil_threshold:
            logger.debug(f"Marking {node_id} as Sybil due to too many connections")
            self.sybil_nodes.add(node_id)
            # Снижаем репутацию при обнаружении Sybil-атаки
            await self.update_reputation(node_id, False)
            self.last_reputation_update[node_id] = current_time
            return False
            
        return True 