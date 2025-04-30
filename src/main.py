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

logger = logging.getLogger("main")

class Application:
    """
    Основной класс приложения
    """
    
    def __init__(self):
        """Инициализация приложения"""
        self.config = Config()
        self.is_running = False
        
    async def initialize(self):
        """Инициализирует компоненты приложения"""
        # Загружаем конфигурацию
        await self.config.load()
        
        # Инициализируем компоненты
        self.network = Network(self.config)
        self.onion_manager = OnionRoutingManager(self.config)
        self.ui = TerminalUI(self.config, self.network, self.onion_manager)
        
    async def start(self):
        """Запускает приложение"""
        try:
            # Инициализируем компоненты
            await self.initialize()
            
            # Запускаем сеть
            await self.network.start()
            
            # Запускаем UI
            self.is_running = True
            await self.ui.start()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске: {e}")
            raise
        finally:
            await self.stop()
            
    async def stop(self):
        """Останавливает приложение"""
        if self.is_running:
            self.is_running = False
            await self.network.stop()
            
async def main():
    """Точка входа в приложение"""
    try:
        app = Application()
        await app.start()
    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 