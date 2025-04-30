"""
Точка входа для запуска SecureTermChat
"""

import sys
import os
import asyncio
import logging

# Добавляем родительскую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import SecureTermChat

def main():
    """Основная функция запуска приложения"""
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('securetermchat.log'),
            logging.StreamHandler()
        ]
    )
    
    # Создаем и запускаем приложение
    app = SecureTermChat()
    
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 