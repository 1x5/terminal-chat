"""
Модуль маршрутизации сообщений
"""

import asyncio
from typing import Dict, List, Optional, Set
from collections import defaultdict
import time

class MessageRouter:
    """Класс для маршрутизации сообщений между узлами"""
    
    def __init__(self, config, crypto_manager):
        self.config = config
        self.crypto = crypto_manager
        self.messages = defaultdict(list)  # Очереди сообщений для узлов
        self.groups = defaultdict(set)  # Группы узлов
        self.retry_counts = defaultdict(int)  # Счетчики повторных отправок
        self.acks = defaultdict(list)  # Подтверждения доставки
        self.is_running = False
        self.cleanup_task = None
        self._message_buffers = defaultdict(list)  # Буферы для групповых операций
        self._buffer_size = 100  # Размер буфера для групповых операций
        self._buffer_timeout = 0.1  # Таймаут сброса буфера в секундах
        self._last_buffer_flush = time.time()
        
    async def start(self):
        """Запуск маршрутизатора"""
        self.is_running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
    async def stop(self):
        """Остановка маршрутизатора"""
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        await self._flush_all_buffers()
        
    def _validate_node_id(self, node_id: str) -> bool:
        """Проверка идентификатора узла"""
        return (
            isinstance(node_id, str) and
            len(node_id.strip()) > 0 and
            not node_id.isspace()
        )
        
    def _validate_message(self, message: dict) -> bool:
        """Проверка сообщения"""
        return (
            isinstance(message, dict) and
            isinstance(message.get("type"), str) and
            len(message.get("type", "").strip()) > 0 and
            "data" in message
        )
        
    def _validate_group(self, group: str) -> bool:
        """Проверка идентификатора группы"""
        return (
            isinstance(group, str) and
            len(group.strip()) > 0 and
            not group.isspace()
        )

    async def _flush_buffer(self, target: str):
        """Сброс буфера сообщений для узла"""
        if target in self._message_buffers:
            messages = self._message_buffers[target]
            if messages:
                self.messages[target].extend(messages)
                self._message_buffers[target] = []
                # Сортируем только новые сообщения
                self.messages[target].sort(key=lambda x: (-x.get("priority", 0), x["timestamp"]))

    async def _flush_all_buffers(self):
        """Сброс всех буферов сообщений"""
        for target in list(self._message_buffers.keys()):
            await self._flush_buffer(target)

    async def _check_buffer_flush(self):
        """Проверка необходимости сброса буферов"""
        now = time.time()
        if now - self._last_buffer_flush >= self._buffer_timeout:
            await self._flush_all_buffers()
            self._last_buffer_flush = now
        
    async def route_message(self, source: str, target: str, message: dict) -> bool:
        """Маршрутизация сообщения от источника к получателю"""
        if not self.is_running:
            return False
            
        # Проверяем входные данные
        if not (
            self._validate_node_id(source) and
            self._validate_node_id(target) and
            self._validate_message(message)
        ):
            return False
            
        # Добавляем метаданные
        message["source"] = source
        message["timestamp"] = time.time()
        
        # Добавляем сообщение в буфер
        self._message_buffers[target].append(message)
        
        # Проверяем необходимость сброса буфера
        if len(self._message_buffers[target]) >= self._buffer_size:
            await self._flush_buffer(target)
        else:
            await self._check_buffer_flush()
            
        # Обрабатываем повторные отправки
        if retry := message.get("retry"):
            self.retry_counts[target] += retry
            
        # Обрабатываем подтверждения
        if message.get("require_ack"):
            ack = {
                "target": target,
                "message_type": message["type"],
                "timestamp": time.time()
            }
            self.acks[source].append(ack)
            
        return True
        
    async def broadcast_message(self, source: str, targets: List[str], message: dict) -> bool:
        """Широковещательная рассылка сообщения"""
        if not (
            self._validate_node_id(source) and
            self._validate_message(message) and
            isinstance(targets, list) and
            all(self._validate_node_id(target) for target in targets)
        ):
            return False
            
        # Оптимизация: добавляем сообщение в буферы всех получателей
        message["source"] = source
        message["timestamp"] = time.time()
        
        for target in targets:
            self._message_buffers[target].append(message)
            if len(self._message_buffers[target]) >= self._buffer_size:
                await self._flush_buffer(target)
                
        await self._check_buffer_flush()
        return True
        
    async def multicast_message(self, source: str, groups: List[str], message: dict) -> bool:
        """Групповая рассылка сообщения"""
        if not (
            self._validate_node_id(source) and
            self._validate_message(message) and
            isinstance(groups, list) and
            all(self._validate_group(group) for group in groups)
        ):
            return False
            
        # Собираем все целевые узлы
        targets = set()
        for group in groups:
            targets.update(self.groups[group])
            
        return await self.broadcast_message(source, list(targets), message)
        
    async def add_to_group(self, node_id: str, group: str):
        """Добавление узла в группу"""
        if not (
            self._validate_node_id(node_id) and
            self._validate_group(group)
        ):
            return False
            
        self.groups[group].add(node_id)
        return True
        
    async def get_message(self, target: str) -> Optional[dict]:
        """Получение следующего сообщения для узла"""
        if not self._validate_node_id(target):
            return None
            
        # Сбрасываем буфер перед получением сообщения
        await self._flush_buffer(target)
            
        messages = self.messages[target]
        return messages.pop(0) if messages else None
        
    async def get_retry_count(self, target: str) -> int:
        """Получение счетчика повторных отправок"""
        if not self._validate_node_id(target):
            return 0
            
        return self.retry_counts[target]
        
    async def get_ack(self, source: str) -> Optional[dict]:
        """Получение подтверждения доставки"""
        if not self._validate_node_id(source):
            return None
            
        acks = self.acks[source]
        return acks.pop(0) if acks else None
        
    async def _cleanup_loop(self):
        """Цикл очистки устаревших сообщений"""
        while self.is_running:
            now = time.time()
            
            # Сбрасываем буферы
            await self._flush_all_buffers()
            
            # Очищаем сообщения с истекшим TTL
            for target, messages in self.messages.items():
                self.messages[target] = [
                    msg for msg in messages
                    if not msg.get("ttl") or 
                    (now - msg["timestamp"]) < msg["ttl"]
                ]
                
            # Очищаем устаревшие подтверждения
            for source, acks in self.acks.items():
                self.acks[source] = [
                    ack for ack in acks
                    if (now - ack["timestamp"]) < self.config.ack_ttl
                ]
                
            await asyncio.sleep(1) 