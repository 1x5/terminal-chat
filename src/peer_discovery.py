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
    
    def __init__(self, config, message_handler=None):
        """
        Инициализирует модуль обнаружения пиров
        
        Args:
            config: Объект конфигурации
            message_handler: Обработчик сообщений от пиров
        """
        self.config = config
        self.message_handler = message_handler
        
        # Хранение информации о пирах
        self.known_peers = {}  # id -> {'address': str, 'port': int, 'public_key': str, 'last_seen': float}
        self.active_connections = {}  # id -> NodeConnection
        
        # Метаданные для алгоритма обнаружения
        self.bootstrap_nodes = config.get_bootstrap_nodes()
        self.discovery_running = False
        self.max_peers = config.config.get("max_peers", 50)
        self.discovered_peers_count = 0
        
        # Кеш недоступных узлов, чтобы не пытаться подключаться к ним слишком часто
        self.unreachable_peers = {}  # address:port -> last_attempt_time
        
        # Интервалы обнаружения и обслуживания
        self.discovery_interval = config.config.get("discovery_interval", 300)  # 5 минут
        self.maintenance_interval = config.config.get("maintenance_interval", 60)  # 1 минута
        
        # Флаг работы
        self.is_running = False
        
        # HTTP-сессия для запросов к bootstrap-серверам
        self.session = None
        
    async def start(self):
        """Запускает процесс обнаружения пиров"""
        self.discovery_running = True
        self.is_running = True
        self.session = aiohttp.ClientSession()
        
        # Загружаем начальный список пиров
        await self.load_bootstrap_peers()
        
        # Запускаем основные задачи
        self.discovery_task = asyncio.create_task(self._peer_discovery_loop())
        self.maintenance_task = asyncio.create_task(self._connection_maintenance())
        self.periodic_task = asyncio.create_task(self._periodic_discovery())
        
        # Выполняем начальное обнаружение пиров
        await self._discover_initial_peers()
        
        # Устанавливаем running в True
        self.running = True
        
        logger.info("Система обнаружения пиров запущена")
        
    async def stop(self):
        """Останавливает процесс обнаружения пиров"""
        self.discovery_running = False
        self.is_running = False
        
        # Закрываем все активные соединения
        for conn in list(self.active_connections.values()):
            await conn.close()
        
        self.active_connections.clear()
        
        # Закрываем HTTP-сессию
        if self.session:
            await self.session.close()
            self.session = None
            
        # Отменяем все задачи
        tasks = []
        for task_name in ['discovery_task', 'maintenance_task', 'periodic_task']:
            if hasattr(self, task_name) and getattr(self, task_name):
                task = getattr(self, task_name)
                task.cancel()
                tasks.append(task)
                setattr(self, task_name, None)
                
        # Ждем завершения всех задач
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            
        # Устанавливаем running в False
        self.running = False
            
        logger.info("Система обнаружения пиров остановлена")
    
    async def _discover_initial_peers(self):
        """Выполняет начальное обнаружение пиров через bootstrap-узлы"""
        if not self.bootstrap_nodes:
            logger.warning("Нет доступных bootstrap-узлов для обнаружения пиров")
            return
        
        logger.info(f"Начинаю обнаружение пиров через {len(self.bootstrap_nodes)} bootstrap-узлов")
        
        # Перемешиваем bootstrap-узлы для равномерного распределения нагрузки
        bootstrap_nodes = self.bootstrap_nodes.copy()
        random.shuffle(bootstrap_nodes)
        
        for node_addr in bootstrap_nodes:
            if not self.discovery_running:
                break
                
            # Парсим адрес и порт
            try:
                if ':' in node_addr:
                    address, port_str = node_addr.split(':')
                    port = int(port_str)
                else:
                    address = node_addr
                    port = 8080  # Порт по умолчанию
            except ValueError:
                logger.warning(f"Некорректный адрес bootstrap-узла: {node_addr}")
                continue
            
            # Проверяем, не пытались ли мы недавно подключиться к этому узлу
            node_key = f"{address}:{port}"
            if node_key in self.unreachable_peers:
                last_attempt = self.unreachable_peers[node_key]
                if time.time() - last_attempt < 600:  # 10 минут между попытками
                    logger.debug(f"Пропускаю недоступный узел {node_key}")
                    continue
            
            # Подключаемся к bootstrap-узлу
            reader, writer = await connect_to_node(address, port)
            if not reader or not writer:
                # Запоминаем недоступный узел
                self.unreachable_peers[node_key] = time.time()
                continue
            
            # Создаем идентификатор узла
            node_id = os.urandom(16).hex()
            
            # Инициализируем соединение
            connection = NodeConnection(node_id, reader, writer, outgoing=True)
            connection.message_callback = self.message_handler
            
            # Запускаем чтение сообщений
            asyncio.create_task(connection.start_reading())
            
            # Сохраняем соединение
            self.active_connections[node_id] = connection
            
            # Отправляем запрос на получение списка пиров
            await self._request_peers(connection)
            
            # Ограничиваем количество подключений к bootstrap-узлам
            if len(self.active_connections) >= 3:
                break
        
        logger.info(f"Начальное обнаружение пиров завершено. Активных соединений: {len(self.active_connections)}")
    
    async def _periodic_discovery(self):
        """Периодически запускает процесс обнаружения новых пиров"""
        while self.discovery_running:
            # Ждем указанный интервал
            await asyncio.sleep(self.discovery_interval)
            
            # Проверяем, нужно ли обнаруживать новые пиры
            if len(self.active_connections) < self.max_peers:
                # Если у нас уже есть активные соединения, запрашиваем у них новые пиры
                if self.active_connections:
                    # Выбираем случайное соединение для запроса
                    peer_id = random.choice(list(self.active_connections.keys()))
                    connection = self.active_connections[peer_id]
                    
                    # Отправляем запрос на получение списка пиров
                    await self._request_peers(connection)
                else:
                    # Если нет активных соединений, пробуем bootstrap-узлы
                    await self._discover_initial_peers()
    
    async def _connection_maintenance(self):
        """Выполняет обслуживание соединений (проверка активности, обновление RTT)"""
        while self.discovery_running:
            # Ждем указанный интервал
            await asyncio.sleep(self.maintenance_interval)
            
            # Проверяем все активные соединения
            for peer_id, connection in list(self.active_connections.items()):
                # Если соединение больше не активно, удаляем его
                if not connection.connected:
                    logger.debug(f"Удаление неактивного соединения с {peer_id}")
                    self.active_connections.pop(peer_id, None)
                    continue
                
                # Проверяем время последней активности
                if time.time() - connection.last_active > 300:  # 5 минут неактивности
                    # Отправляем пинг для проверки соединения
                    try:
                        await connection.send_ping()
                    except Exception as e:
                        logger.warning(f"Ошибка при отправке пинга узлу {peer_id}: {e}")
                        # Закрываем соединение, если не удалось отправить пинг
                        await connection.close()
                        self.active_connections.pop(peer_id, None)
    
    async def _request_peers(self, connection):
        """
        Отправляет запрос на получение списка пиров
        
        Args:
            connection: Соединение с узлом
        """
        message = {
            "type": "get_peers",
            "id": os.urandom(8).hex(),
            "timestamp": time.time(),
            "max_count": 20  # Максимальное количество пиров для получения
        }
        
        await connection.send_message(message)
    
    async def handle_get_peers_request(self, message, connection):
        """
        Обрабатывает запрос на получение списка пиров
        
        Args:
            message: Сообщение с запросом
            connection: Соединение с отправителем
        """
        max_count = message.get("max_count", 10)
        
        # Собираем список известных пиров
        peers = []
        for peer_id, peer_info in self.known_peers.items():
            peers.append({
                "id": peer_id,
                "address": peer_info["address"],
                "port": peer_info["port"],
                "public_key": peer_info.get("public_key")
            })
            
            if len(peers) >= max_count:
                break
        
        # Отправляем ответ
        response = {
            "type": "peers_list",
            "id": message.get("id"),
            "timestamp": time.time(),
            "peers": peers
        }
        
        await connection.send_message(response)
    
    async def handle_peers_list(self, message, connection):
        """
        Обрабатывает полученный список пиров
        
        Args:
            message: Сообщение со списком пиров
            connection: Соединение с отправителем
        """
        peers = message.get("peers", [])
        
        logger.debug(f"Получен список из {len(peers)} пиров")
        
        # Обрабатываем полученные пиры
        for peer in peers:
            peer_id = peer.get("id")
            address = peer.get("address")
            port = peer.get("port")
            public_key = peer.get("public_key")
            
            if not peer_id or not address or not port:
                continue
            
            # Пропускаем уже известные пиры
            if peer_id in self.known_peers or peer_id in self.active_connections:
                continue
            
            # Сохраняем информацию о пире
            self.known_peers[peer_id] = {
                "address": address,
                "port": port,
                "public_key": public_key,
                "last_seen": time.time()
            }
            
            # Пытаемся подключиться к новому пиру, если нам нужны дополнительные соединения
            if len(self.active_connections) < self.max_peers:
                asyncio.create_task(self._connect_to_peer(peer_id, address, port))
    
    async def _connect_to_peer(self, peer_id, address, port):
        """
        Подключается к новому пиру
        
        Args:
            peer_id: Идентификатор пира
            address: Адрес пира
            port: Порт пира
        """
        # Проверяем, не превышен ли лимит соединений
        if len(self.active_connections) >= self.max_peers:
            return
        
        # Проверяем, не пытались ли мы недавно подключиться к этому узлу
        node_key = f"{address}:{port}"
        if node_key in self.unreachable_peers:
            last_attempt = self.unreachable_peers[node_key]
            if time.time() - last_attempt < 600:  # 10 минут между попытками
                return
        
        # Подключаемся к пиру
        reader, writer = await connect_to_node(address, port)
        if not reader or not writer:
            # Запоминаем недоступный узел
            self.unreachable_peers[node_key] = time.time()
            return
        
        # Инициализируем соединение
        connection = NodeConnection(peer_id, reader, writer, outgoing=True)
        connection.message_callback = self.message_handler
        
        # Запускаем чтение сообщений
        asyncio.create_task(connection.start_reading())
        
        # Сохраняем соединение
        self.active_connections[peer_id] = connection
        
        logger.info(f"Установлено новое соединение с пиром {peer_id} ({address}:{port})")
        
        # Увеличиваем счетчик обнаруженных пиров
        self.discovered_peers_count += 1
        
    def get_active_peers(self) -> List[str]:
        """
        Возвращает список активных пиров
        
        Returns:
            List[str]: Список идентификаторов активных пиров
        """
        return list(self.active_connections.keys())
    
    def get_active_connections_count(self) -> int:
        """
        Возвращает количество активных соединений
        
        Returns:
            int: Количество активных соединений
        """
        return len(self.active_connections)
    
    def get_known_peers_count(self) -> int:
        """
        Возвращает количество известных пиров
        
        Returns:
            int: Количество известных пиров
        """
        return len(self.known_peers)
    
    def select_random_peers(self, count: int) -> List[NodeConnection]:
        """
        Выбирает случайные активные соединения с пирами
        
        Args:
            count (int): Желаемое количество пиров
            
        Returns:
            List[NodeConnection]: Список соединений с выбранными пирами
        """
        if not self.active_connections:
            return []
        
        peer_ids = list(self.active_connections.keys())
        selected_count = min(count, len(peer_ids))
        
        if selected_count == 0:
            return []
            
        selected_ids = random.sample(peer_ids, selected_count)
        return [self.active_connections[peer_id] for peer_id in selected_ids]
    
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
                self.known_peers[f"bootstrap_{host}_{port}"] = {
                    "host": host,
                    "port": port,
                    "last_seen": time.time(),
                    "is_bootstrap": True
                }
                
            except Exception as e:
                logger.warning(f"Ошибка при загрузке пиров с {node_address}: {e}")
    
    async def _peer_discovery_loop(self):
        """Периодически обновляет список пиров"""
        while self.is_running:
            try:
                # Проверяем истечение времени жизни пиров
                current_time = time.time()
                for node_id, peer in list(self.known_peers.items()):
                    # Удаляем пиры, которые не видели более 24 часов
                    if current_time - peer["last_seen"] > 86400 and not peer.get("is_bootstrap", False):
                        logger.debug(f"Удаляем устаревший пир {node_id}")
                        del self.known_peers[node_id]
                
                # Обмениваемся списками пиров с другими узлами
                # В реальной реализации здесь должен быть обмен с подключенными пирами
                
                # Ждем перед следующим обновлением
                await asyncio.sleep(300)  # Каждые 5 минут
                
            except asyncio.CancelledError:
                logger.info("Задача обнаружения пиров отменена")
                break
            except Exception as e:
                logger.error(f"Ошибка в задаче обнаружения пиров: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повторной попыткой
    
    async def update_peers(self, active_peers: List[str]):
        """
        Обновляет информацию о пирах
        
        Args:
            active_peers (List[str]): Список ID активных пиров
        """
        current_time = time.time()
        
        for node_id in active_peers:
            if node_id in self.known_peers:
                self.known_peers[node_id]["last_seen"] = current_time
    
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
            [{"node_id": node_id, **peer} for node_id, peer in self.known_peers.items()],
            key=lambda x: x["last_seen"],
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
        # Преобразуем словарь пиров в список
        peers = list(self.known_peers.values())
        
        # Если у нас недостаточно пиров, возвращаем все имеющиеся
        if len(peers) <= count:
            return peers
            
        # Выбираем случайные узлы
        return random.sample(peers, count)
    
    def get_peer_count(self) -> int:
        """
        Возвращает количество известных пиров
        
        Returns:
            int: Количество пиров
        """
        return len(self.known_peers) 