"""
Управление конфигурацией SecureTermChat

Модуль реализует загрузку, сохранение и управление
конфигурационными параметрами приложения.
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from nacl.public import PrivateKey, PublicKey
import nacl.utils
import nacl.encoding

logger = logging.getLogger("securetermchat.config")

class Config:
    """
    Класс управления конфигурацией приложения
    """
    
    @property
    def port(self) -> int:
        """Возвращает порт для прослушивания"""
        return self.config["listen_port"]
        
    @property
    def data_dir(self) -> str:
        """Возвращает директорию для данных"""
        return self.config["data_dir"]
        
    def __init__(self, config_path: str = None):
        """
        Инициализация объекта конфигурации
        
        Args:
            config_path (str): Путь к файлу конфигурации
        """
        self.config_path = config_path or os.path.expanduser("~/.securetermchat/config.json")
        
        # Значения конфигурации по умолчанию
        self.config = {
            "node_id": None,  # Будет сгенерирован при первом запуске
            "listen_host": "127.0.0.1",  # Локальный хост для тестирования
            "listen_port": 8765,  # Фиксированный порт для тестирования
            "bootstrap_nodes": [
                "127.0.0.1:8765"  # Локальный узел для тестирования
            ],
            "min_hops": 3,
            "max_hops": 5,
            "circuit_max_age": 3600,  # 1 час
            "circuit_idle_timeout": 600,  # 10 минут
            "circuit_max_traffic": 1024 * 1024,  # 1 МБ
            "circuit_rotation_threshold": 0.8,  # 80% от максимума
            "message_expiry": 86400,  # 24 часа
            "dummy_traffic_interval": 60,  # 1 минута
            "max_peers": 50,
            "ui_refresh_rate": 0.1,  # Частота обновления UI в секундах
            "log_level": "INFO",
            "data_dir": None  # Будет установлен при загрузке
        }
        
        # Ключи для шифрования
        self.private_key = None
        self.public_key = None
        
        # Список контактов
        self.contacts = {}
        
    async def load(self):
        """Загружает конфигурацию и ключи из файлов"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
                logger.info("Конфигурация загружена")
            else:
                logger.info("Файл конфигурации не найден, используются значения по умолчанию")
            
            # Устанавливаем data_dir
            if not self.config.get("data_dir"):
                config_dir = os.path.dirname(self.config_path)
                if "securetermchat" not in config_dir:
                    config_dir = os.path.join(config_dir, "securetermchat")
                self.config["data_dir"] = os.path.join(config_dir, "data")
            
            # Создаем директории
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            os.makedirs(self.data_dir, exist_ok=True)
            
            # Устанавливаем пути к файлам
            self.keys_path = os.path.join(self.data_dir, "keys.json")
            self.contacts_path = os.path.join(self.data_dir, "contacts.json")
            
            # Валидируем конфигурацию
            self._validate_config()
            
            # Загружаем или генерируем ключи
            await self.load_or_generate_keys()
            
            # Загружаем контакты
            await self.load_contacts()
            
            # Если node_id не задан, генерируем его из публичного ключа
            if not self.config["node_id"]:
                self.config["node_id"] = self.public_key.encode(nacl.encoding.HexEncoder).decode()[:16]
                await self.save()
        except Exception as e:
            logger.error(f"Ошибка при загрузке конфигурации: {e}")
            raise
        
    def _validate_config(self):
        """Проверяет корректность конфигурации"""
        errors = []
        
        # Проверяем listen_host
        if not isinstance(self.config["listen_host"], str):
            errors.append("listen_host должен быть строкой")
            
        # Проверяем listen_port
        if not isinstance(self.config["listen_port"], int):
            errors.append("listen_port должен быть целым числом")
        elif self.config["listen_port"] != 0 and not (1024 <= self.config["listen_port"] <= 65535):
            errors.append("listen_port должен быть 0 (для автоматического выбора) или в диапазоне 1024-65535")
            
        # Проверяем bootstrap_nodes
        if not isinstance(self.config["bootstrap_nodes"], list):
            errors.append("bootstrap_nodes должен быть списком")
        else:
            for node in self.config["bootstrap_nodes"]:
                if not isinstance(node, str):
                    errors.append("bootstrap_nodes должны быть строками")
                elif ":" not in node:
                    errors.append(f"Неверный формат адреса узла: {node}")
                else:
                    host, port = node.split(":")
                    try:
                        port = int(port)
                        if not (1024 <= port <= 65535):
                            errors.append(f"Неверный порт узла {node}")
                    except ValueError:
                        errors.append(f"Неверный порт узла {node}")
                        
        # Проверяем log_level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.config["log_level"] not in valid_log_levels:
            errors.append(f"log_level должен быть одним из {valid_log_levels}")
            
        if errors:
            raise ValueError("\n".join(errors))
            
    async def save(self):
        """Сохраняет текущую конфигурацию в файл"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info("Конфигурация сохранена")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации: {e}")
            return False
        
    async def load_or_generate_keys(self):
        """Загружает существующие ключи или генерирует новые"""
        if os.path.exists(self.keys_path):
            try:
                with open(self.keys_path, 'r') as f:
                    keys_data = json.load(f)
                    
                private_key_hex = keys_data.get("private_key")
                public_key_hex = keys_data.get("public_key")
                
                if private_key_hex:
                    self.private_key = PrivateKey(nacl.encoding.HexEncoder.decode(private_key_hex))
                    self.public_key = self.private_key.public_key
                    logger.info("Криптографические ключи загружены")
                else:
                    raise ValueError("Файл ключей поврежден")
                    
            except Exception as e:
                logger.error(f"Ошибка загрузки ключей: {e}. Будут сгенерированы новые ключи.")
                await self.generate_and_save_keys()
        else:
            logger.info("Файл ключей не найден. Генерация новых ключей...")
            await self.generate_and_save_keys()
        
    async def generate_and_save_keys(self):
        """Генерирует новую пару ключей и сохраняет их"""
        self.private_key = PrivateKey.generate()
        self.public_key = self.private_key.public_key
        
        keys_data = {
            "private_key": nacl.encoding.HexEncoder.encode(bytes(self.private_key)).decode(),
            "public_key": nacl.encoding.HexEncoder.encode(bytes(self.public_key)).decode(),
            "generated_at": str(asyncio.get_event_loop().time())
        }
        
        try:
            with open(self.keys_path, 'w') as f:
                json.dump(keys_data, f)
            logger.info("Новые криптографические ключи сгенерированы и сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения ключей: {e}")
            
    async def load_contacts(self):
        """Загружает список контактов из файла"""
        if os.path.exists(self.contacts_path):
            try:
                with open(self.contacts_path, 'r') as f:
                    self.contacts = json.load(f)
                logger.info(f"Загружено {len(self.contacts)} контактов")
            except Exception as e:
                logger.error(f"Ошибка загрузки контактов: {e}")
                self.contacts = {}
        else:
            logger.info("Файл контактов не найден. Создан пустой список контактов.")
            self.contacts = {}
    
    async def save_contacts(self):
        """Сохраняет список контактов в файл"""
        try:
            with open(self.contacts_path, 'w') as f:
                json.dump(self.contacts, f, indent=2)
            logger.info(f"Список контактов сохранен ({len(self.contacts)} контактов)")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения контактов: {e}")
            return False
    
    async def add_contact(self, name: str, public_key: str):
        """
        Добавляет новый контакт в список
        
        Args:
            name (str): Имя контакта
            public_key (str): Публичный ключ контакта в шестнадцатеричном формате
        
        Returns:
            bool: True если контакт успешно добавлен, иначе False
        """
        try:
            # Проверяем корректность публичного ключа
            _ = PublicKey(nacl.encoding.HexEncoder.decode(public_key))
            
            # Добавляем контакт
            self.contacts[name] = {
                "public_key": public_key,
                "added_at": asyncio.get_event_loop().time(),
                "last_seen": None
            }
            
            # Сохраняем изменения
            await self.save_contacts()
            logger.info(f"Добавлен новый контакт: {name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления контакта {name}: {e}")
            return False
            
    async def remove_contact(self, name: str):
        """
        Удаляет контакт из списка
        
        Args:
            name (str): Имя контакта для удаления
            
        Returns:
            bool: True если контакт успешно удален, иначе False
        """
        if name in self.contacts:
            del self.contacts[name]
            await self.save_contacts()
            logger.info(f"Контакт удален: {name}")
            return True
        else:
            logger.warning(f"Попытка удаления несуществующего контакта: {name}")
            return False
            
    def get_node_id(self) -> str:
        """
        Возвращает идентификатор узла
        
        Returns:
            str: Идентификатор узла
        """
        return self.config["node_id"]
    
    def get_min_hops(self) -> int:
        """
        Возвращает минимальное количество хопов в цепочке
        
        Returns:
            int: Минимальное количество хопов
        """
        return self.config["min_hops"]
    
    def get_max_hops(self) -> int:
        """
        Возвращает максимальное количество хопов в цепочке
        
        Returns:
            int: Максимальное количество хопов
        """
        return self.config["max_hops"]
    
    def get_bootstrap_nodes(self) -> List[str]:
        """
        Возвращает список загрузочных узлов
        
        Returns:
            List[str]: Список адресов bootstrap-узлов
        """
        return self.config["bootstrap_nodes"]
    
    def get_listen_address(self) -> tuple:
        """
        Возвращает адрес для прослушивания
        
        Returns:
            tuple: (host, port) - адрес для прослушивания
        """
        return (self.config["listen_host"], self.config["listen_port"])
    
    def load_keys(self) -> Dict:
        """
        Возвращает загруженные ключи
        
        Returns:
            Dict: Словарь с ключами или None при ошибке
        """
        if self.private_key and self.public_key:
            return {
                "private_key": self.private_key,
                "public_key": self.public_key
            }
        return None
    
    async def add_peer(self, host: str, port: int):
        """
        Добавляет пир в список bootstrap_nodes
        
        Args:
            host (str): Хост пира
            port (int): Порт пира
        """
        peer = f"{host}:{port}"
        if peer not in self.config["bootstrap_nodes"]:
            self.config["bootstrap_nodes"].append(peer)
            await self.save()
            logger.info(f"Добавлен новый пир: {peer}")
            
    async def remove_peer(self, host: str, port: int):
        """
        Удаляет пир из списка bootstrap_nodes
        
        Args:
            host (str): Хост пира
            port (int): Порт пира
        """
        peer = f"{host}:{port}"
        if peer in self.config["bootstrap_nodes"]:
            self.config["bootstrap_nodes"].remove(peer)
            await self.save()
            logger.info(f"Удален пир: {peer}") 