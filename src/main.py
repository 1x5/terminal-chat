"""
Основной модуль приложения

Запускает все компоненты и координирует их работу.
"""

import asyncio
import logging
import os
import sys
import argparse
from typing import Optional
from datetime import datetime

from src.config import Config
from src.crypto import CryptoManager
from src.security import SecurityManager
from src.network import Network
from src.onion_routing import OnionRoutingManager
from src.ui import TerminalUI

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Отключаем отладочные сообщения для websockets
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

logger = logging.getLogger("main")

class Application:
    """
    Основной класс приложения
    """
    
    def __init__(self, port: int = None):
        """Инициализация приложения"""
        self.config = None
        self.network = None
        self.onion_routing = None
        self.ui = None
        self.security = None
        self.crypto = None
        self.port = port or int(os.environ.get('PORT', 8765))
        
    async def initialize(self):
        """Инициализирует компоненты приложения"""
        try:
            # Загружаем конфигурацию
            self.config = Config()
            await self.config.load()
            logger.info("Конфигурация загружена")
            
            # Инициализируем компоненты
            self.crypto = CryptoManager(self.config)
            await self.crypto.init()
            logger.info("CryptoManager инициализирован")
            
            self.security = SecurityManager(self.config)
            await self.security.init()
            logger.info("SecurityManager инициализирован")
            
            # Инициализируем сеть
            self.network = Network(self.config, self.security, port=self.port)
            await self.network.start()
            logger.info("Network модуль запущен")
            
            # Инициализируем луковую маршрутизацию
            self.onion_routing = OnionRoutingManager(self.config, self.crypto, self.network)
            await self.onion_routing.init()
            logger.info("OnionRouting инициализирован")
            
            self.ui = TerminalUI(self.config, self.network, self.onion_routing)
            logger.info("TerminalUI инициализирован")
            
        except Exception as e:
            logger.critical(f"Ошибка при инициализации: {e}")
            raise
            
    async def start(self):
        """Запускает приложение"""
        try:
            await self.ui.start()
        except Exception as e:
            logger.critical(f"Критическая ошибка: {e}")
            raise
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Очищает ресурсы"""
        if self.ui:
            await self.ui.cleanup()
        if self.onion_routing:
            await self.onion_routing.cleanup()
        if self.network:
            await self.network.stop()
        if self.security:
            await self.security.cleanup()
        if self.crypto:
            await self.crypto.cleanup()

def main():
    """Точка входа"""
    try:
        # Парсим аргументы командной строки
        parser = argparse.ArgumentParser(description="SecureTermChat")
        parser.add_argument("--port", type=int, help="Port to listen on", default=None)
        args = parser.parse_args()
        
        # Создаем и запускаем приложение
        app = Application(port=args.port)
        
        async def run_app():
            await app.initialize()
            await app.start()
            
        asyncio.run(run_app())
        
    except KeyboardInterrupt:
        logger.info("Завершение работы по Ctrl+C")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Необработанная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 