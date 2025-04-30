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

logger = logging.getLogger("main")

class Application:
    """
    Основной класс приложения
    """
    
    def __init__(self):
        """Инициализирует приложение"""
        self.config = Config()
        self.network = Network(self.config)
        self.ui = TerminalUI(self.config.data_dir)
        self.running = False
        
    async def start(self):
        """Запускает приложение"""
        try:
            # Загружаем конфигурацию
            self.config.load()
            
            # Запускаем сеть
            await self.network.start()
            
            # Запускаем UI
            self.running = True
            await self.ui.start()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске: {e}")
            raise
        finally:
            await self.stop()
            
    async def stop(self):
        """Останавливает приложение"""
        if self.running:
            self.running = False
            await self.network.stop()
            
def main():
    """Точка входа в приложение"""
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(os.path.expanduser("~/.securetermchat"), "app.log"))
        ]
    )
    
    # Создаем и запускаем приложение
    app = Application()
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    main() 