import asyncio
import logging
import time
import hashlib
from typing import Dict, Set, Optional
from websockets.server import WebSocketServerProtocol

"""
Модуль безопасности для проверки подлинности узлов, защиты от атак и валидации сообщений
"""

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
    initial_reputation: float = 0.5
    max_reputation: float = 1.0

class SecurityManager:
    """Менеджер безопасности"""
    
    def __init__(self, config):
        """
        Инициализирует менеджер безопасности
        
        Args:
            config: Конфигурация приложения
        """
        self.config = config
        self.crypto = CryptoManager(config)
        self.security_config = SecurityConfig()
        self.challenges: Dict[str, str] = {}
        self.authenticated_nodes: Set[str] = set()
        self.connections: Dict[str, List[float]] = {}
        self.message_counts: Dict[str, int] = {}
        self.last_message_time: Dict[str, float] = {}
        self.node_reputation: Dict[str, float] = {}
        self.last_reputation_update: Dict[str, float] = {}
        self.blocked_nodes: Set[str] = set()
        self.sybil_nodes: Set[str] = set()
        self.cleanup_task = None
        self.logger = logging.getLogger(__name__)
        self._known_peers: Set[str] = set()
        self._active_challenges: Dict[str, float] = {}
        self._reputation: Dict[str, float] = {}
        self._last_reputation_update: Dict[str, float] = {}
        self.reputations: Dict[str, float] = {}
        self.blocked_peers: Set[str] = set()
        
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

    async def update_reputation(self, peer_id: str, success: bool):
        """Обновляет репутацию пира
        
        Args:
            peer_id: Идентификатор пира
            success: Успешность взаимодействия
        """
        try:
            current = self.reputations.get(peer_id, self.config.initial_reputation)
            
            if success:
                # Увеличиваем репутацию при успешном взаимодействии
                new_reputation = min(current + 0.1, self.config.max_reputation)
            else:
                # Уменьшаем репутацию при неудачном взаимодействии
                new_reputation = max(current - self.config.reputation_decay, 0)
                
            self.reputations[peer_id] = new_reputation
            
            # Если репутация упала ниже минимума, блокируем пира
            if new_reputation < self.config.min_reputation:
                self.blocked_peers.add(peer_id)
                logger.warning(f"Пир {peer_id} заблокирован из-за низкой репутации")
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении репутации для {peer_id}: {e}")
            # При ошибке не меняем репутацию

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

    async def validate_connection(self, websocket: WebSocketServerProtocol) -> Optional[str]:
        """Валидация входящего соединения."""
        try:
            # Получаем вызов от инициатора
            challenge = await websocket.recv()
            self.logger.debug(f"Получен вызов: {challenge}")
            
            # Генерируем ответ
            response = hashlib.sha256(challenge.encode()).hexdigest()
            self.logger.debug(f"Сгенерирован ответ: {response}")
            
            # Отправляем ответ
            await websocket.send(response)
            self.logger.debug("Ответ отправлен")
            
            # Получаем подтверждение
            confirmation = await websocket.recv()
            self.logger.debug(f"Получено подтверждение: {confirmation}")
            
            # Проверяем подтверждение
            expected_confirmation = hashlib.sha256((challenge + "_confirmed").encode()).hexdigest()
            if confirmation != expected_confirmation:
                self.logger.warning("Неверное подтверждение вызова")
                return None
                
            # Генерируем peer_id для нового соединения
            peer_id = self._generate_peer_id()
            self.logger.debug(f"Сгенерирован peer_id: {peer_id}")
            
            # Добавляем peer в список известных
            self._known_peers.add(peer_id)
            
            # Обновляем репутацию
            await self.update_reputation(peer_id, True)
            
            return peer_id
            
        except Exception as e:
            self.logger.error(f"Ошибка при валидации соединения: {str(e)}", exc_info=True)
            return None

    async def validate_outgoing_connection(self, websocket) -> Optional[str]:
        """Валидация исходящего соединения."""
        try:
            # Генерируем временный peer_id
            temp_peer_id = self._generate_peer_id()
            self.logger.debug(f"Сгенерирован временный peer_id: {temp_peer_id}")
            
            # Генерируем вызов
            challenge = self._generate_challenge()
            self.logger.debug(f"Сгенерирован вызов: {challenge}")
            
            # Отправляем вызов
            await websocket.send(challenge)
            self.logger.debug("Вызов отправлен")
            
            # Получаем ответ
            self.logger.debug("Ожидание ответа на вызов...")
            response = await websocket.recv()
            self.logger.debug(f"Получен ответ: {response}")
            
            # Проверяем ответ
            expected_response = hashlib.sha256(challenge.encode()).hexdigest()
            if response != expected_response:
                self.logger.warning("Неверный ответ на вызов")
                return None
                
            # Отправляем подтверждение
            confirmation = hashlib.sha256((challenge + "_confirmed").encode()).hexdigest()
            await websocket.send(confirmation)
            self.logger.debug("Подтверждение отправлено")
            
            # Добавляем peer в список известных
            self._known_peers.add(temp_peer_id)
            
            # Обновляем репутацию
            await self.update_reputation(temp_peer_id, True)
            
            return temp_peer_id
            
        except Exception as e:
            self.logger.error(f"Ошибка при валидации соединения: {str(e)}", exc_info=True)
            return None

    def _generate_peer_id(self) -> str:
        """Генерирует уникальный ID для пира."""
        return hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]

    def _generate_challenge(self) -> str:
        """Генерирует вызов для проверки соединения."""
        challenge = hashlib.sha256(str(time.time()).encode()).hexdigest()
        self._active_challenges[challenge] = time.time()
        return challenge

    def _verify_challenge_response(self, challenge: str, response: str) -> bool:
        """Проверяет ответ на вызов."""
        if challenge not in self._active_challenges:
            return False
            
        # Проверяем, что вызов не устарел (5 секунд)
        if time.time() - self._active_challenges[challenge] > 5:
            del self._active_challenges[challenge]
            return False
            
        # Проверяем, что ответ - это хеш вызова
        expected_response = hashlib.sha256(challenge.encode()).hexdigest()
        is_valid = response == expected_response
        
        # Удаляем использованный вызов
        del self._active_challenges[challenge]
        
        return is_valid

    def _generate_challenge_confirmation(self, challenge: str) -> str:
        """Генерирует подтверждение успешной проверки вызова."""
        return hashlib.sha256((challenge + "_confirmed").encode()).hexdigest() 