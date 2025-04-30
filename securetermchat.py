#!/usr/bin/env python3
"""
SecureTermChat - Анонимный защищенный P2P мессенджер для терминала
"""

import asyncio
import argparse
import logging
import os
import sys
from src.config import Config
from src.ui import TerminalUI
from src.network import P2PNetwork
from src.peer_discovery import PeerDiscovery
from src.onion_routing import OnionRoutingManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("securetermchat.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("securetermchat")

async def main():
    """Основная функция приложения"""
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="SecureTermChat - Анонимный защищенный P2P мессенджер")
    parser.add_argument("--config", help="Путь к файлу конфигурации")
    parser.add_argument("--debug", action="store_true", help="Включить режим отладки")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Включен режим отладки")

    try:
        # Загрузка конфигурации
        config_path = args.config if args.config else os.path.expanduser("~/.securetermchat/config.json")
        config = Config(config_path)
        await config.load()
        
        # Инициализация сетевых компонентов
        peer_discovery = PeerDiscovery(config)
        network = P2PNetwork(config, peer_discovery)
        
        # Инициализация менеджера луковой маршрутизации
        onion_manager = OnionRoutingManager(config, peer_discovery)
        
        # Привязка сетевого обработчика к менеджеру луковой маршрутизации
        network.set_message_handler(onion_manager.handle_incoming_message)
        
        # Инициализируем UI
        ui = TerminalUI(config, network, onion_manager)
        
        # Устанавливаем обработчики событий
        ui.on_message_send = network.send_message
        ui.on_contact_add = network.add_contact
        ui.on_contact_remove = network.remove_contact
        ui.on_quit = lambda: asyncio.create_task(stop_components())
        
        # Запуск всех компонентов
        logger.info("Запуск сетевого модуля...")
        await network.start()
        
        logger.info("Запуск менеджера луковой маршрутизации...")
        await onion_manager.start()
        
        logger.info("Запуск пользовательского интерфейса...")
        await ui.start()
        
        # Запуск основного цикла программы
        await ui.run()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания. Завершение работы...")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        # Корректное завершение работы всех компонентов
        logger.info("Завершение работы приложения...")
        
        if 'ui' in locals():
            await ui.stop()
        
        if 'onion_manager' in locals():
            await onion_manager.stop()
            
        if 'network' in locals():
            await network.stop()
            
        logger.info("Приложение успешно завершило работу.")

if __name__ == "__main__":
    # Запуск асинхронного главного цикла
    asyncio.run(main()) 