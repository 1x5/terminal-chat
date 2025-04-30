"""
Основной модуль приложения

Запускает все компоненты и координирует их работу.
"""

import asyncio
import logging
import os
import sys
from typing import Optional

from src.config import Config
from src.network import Network
from src.ui import TerminalUI
from src.onion_manager import OnionRoutingManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

class Application:
    """
    Основной класс приложения
    """
    
    def __init__(self):
        """Инициализация приложения"""
        self.config = Config()
        self.is_running = False
        self.network = None
        self.onion_manager = None
        self.ui = None
        
    async def initialize(self):
        """Инициализирует компоненты приложения"""
        try:
            # Загружаем конфигурацию
            if not os.path.exists("config.json"):
                logger.info("Создаем конфигурацию по умолчанию...")
                await self.config.save()
            
            await self.config.load()
            logger.info("Конфигурация загружена")
            
            # Инициализируем компоненты
            self.network = Network(self.config)
            self.onion_manager = OnionRoutingManager(self.config)
            self.ui = TerminalUI(self.config, self.network, self.onion_manager)
            logger.info("Компоненты инициализированы")
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации: {e}")
            raise
        
    async def start(self):
        """Запускает приложение"""
        try:
            # Инициализируем компоненты
            await self.initialize()
            
            # Запускаем сеть
            logger.info("Запуск сетевого модуля...")
            await self.network.start()
            
            # Запускаем UI и ждем его завершения
            logger.info("Запуск пользовательского интерфейса...")
            self.is_running = True
            
            # Запускаем UI в отдельной задаче
            ui_task = asyncio.create_task(self.ui.start())
            
            # Ждем завершения UI
            await ui_task
            
        except Exception as e:
            logger.error(f"Ошибка при запуске: {e}")
            raise
        finally:
            await self.stop()
            
    async def stop(self):
        """Останавливает приложение"""
        if self.is_running:
            self.is_running = False
            if self.network:
                await self.network.stop()
            if self.ui:
                self.ui.stop()
            logger.info("Приложение остановлено")
            
async def main():
    """Точка входа в приложение"""
    try:
        app = Application()
        await app.start()
    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}")
        sys.exit(1) 