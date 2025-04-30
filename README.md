# TerminalChat

## Статус разработки

### Реализовано
- ✅ Базовая структура проекта
- ✅ Конфигурация и логирование
- ✅ Безопасность и криптография
- ✅ P2P сеть
- ✅ Обработка сообщений
- ✅ Тесты
- ✅ CLI интерфейс

### В процессе
- 🔄 Оптимизация производительности
- 🔄 Улучшение обработки ошибок
- 🔄 Документация

### Планируется
- ⏳ Расширенная функциональность
- ⏳ Улучшение UI/UX
- ⏳ Дополнительные тесты
- ⏳ Интеграционные тесты
- ⏳ CI/CD пайплайн

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/yourusername/terminalchat.git
cd terminalchat

# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # для Linux/Mac
# или
.\venv\Scripts\activate  # для Windows

# Установить зависимости
pip install -r requirements.txt
```

## Запуск

```bash
# Запуск в режиме разработки
python src/main.py

# Запуск тестов
pytest tests/
```

## Структура проекта

```
terminalchat/
├── src/
│   ├── __init__.py
│   ├── main.py          # Точка входа
│   ├── config.py        # Конфигурация
│   ├── logger.py        # Логирование
│   ├── security.py      # Безопасность
│   ├── network.py       # P2P сеть
│   ├── message.py       # Обработка сообщений
│   └── cli.py           # CLI интерфейс
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Фикстуры
│   ├── test_security.py # Тесты безопасности
│   ├── test_network.py  # Тесты сети
│   └── test_message.py  # Тесты сообщений
├── requirements.txt     # Зависимости
└── README.md           # Документация
```

## Тестирование

```bash
# Запуск всех тестов
pytest

# Запуск с отчетом о покрытии
pytest --cov=src tests/

# Запуск конкретного теста
pytest tests/test_security.py -v
```

## Безопасность

- Аутентификация узлов
- Защита от атак
- Валидация сообщений
- Шифрование данных

## Лицензия

MIT 