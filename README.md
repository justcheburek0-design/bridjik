# MineBridge Telegram Bot

**Интеллектуальный Telegram бот-ассистент для Minecraft сервера с AI и базой знаний.**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-25.01-green)](./CHANGELOG.md)

## 🌟 Возможности

- 🤖 **AI-ассистент** — умные ответы через OpenAI (OpenRouter) и Google Gemini
- 📚 **RAG система** — контекстные ответы на основе базы знаний о сервере
- 🎮 **Интеграция с Minecraft** — информация о сервере, игроках и статистике
- 🖼️ **Обработка медиа** — поддержка изображений, голосовых сообщений, стикеров
- 🎤 **Text-to-Speech** — озвучивание ответов бота
- 📰 **Новости** — интеграция с новостными API
- 🎨 **Управление стикерами** — кастомные стикеры для сервера
- 🎲 **Игровые механики** — угадайки, заморозки и другие интерактивные функции

## 🏗️ Архитектура

Проект реализован с использованием **Clean Architecture** для чистого разделения ответственности:

```
minebridge/
├── domain/          # Сущности и интерфейсы (независимый слой)
├── application/     # Бизнес-логика и сервисы
├── infrastructure/  # Внешние зависимости (API, репозитории)
├── presentation/    # Обработчики Telegram команд и сообщений
├── core/            # Конфигурация и DI контейнер
└── utils/           # Вспомогательные утилиты
```

Подробнее об архитектуре см. [docs/architecture.md](./docs/architecture.md)

## 📋 Требования

- **Python** ≥ 3.10
- **Telegram Bot Token** от [@BotFather](https://t.me/BotFather)
- **API ключи**:
  - OpenAI API (через [OpenRouter](https://openrouter.ai/))
  - Google Gemini API
  - Jina AI API (для embeddings)

## 🚀 Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/JustCheburek/AI_TGBot.git
cd minebridge
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -e .

# Для разработки (включая black, pytest, ruff)
pip install -e ".[dev]"
```

### 4. Конфигурация

Скопируйте `.env.example` в `.env` и заполните все необходимые значения:

```bash
cp .env.example .env
```

Откройте `.env` в редакторе и заполните:

```env
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
JINA_API_KEY=your_jina_key
MC_SERVER_HOST=your.minecraft.server:25565
# ... и другие параметры
```

## ▶️ Запуск

### Локальный запуск

```bash
python main.py
```

### Production deployment

Проект настроен для развертывания через **Nixpacks**. Конфигурация находится в `nixpacks.toml`.

## 🧪 Тестирование

Запуск unit-тестов:

```bash
pytest tests/ -v
```

С покрытием кода:

```bash
pytest tests/ --cov=. --cov-report=html
```

## 🛠️ Разработка

### Структура проекта

- **`domain/`** — независимые сущности и интерфейсы
  - `entities.py` — User, Chat, MessageContext
  - `interfaces.py` — абстракции репозиториев
- **`application/`** — бизнес-логика
  - `services/ai.py` — AI сервис (OpenAI + Gemini)
  - `services/rag.py` — RAG система для контекста
  - `services/media.py` — обработка медиа
- **`infrastructure/`** — внешние зависимости
  - `external/` — клиенты для внешних API
  - `repositories/` — хранилища данных (JSON файлы)
- **`presentation/`** — слой Telegram бота
  - `handlers/` — обработчики команд и сообщений
  - `keyboards.py` — inline клавиатуры
- **`core/`** — ядро приложения
  - `config.py` — конфигурация из .env
  - `dependencies.py` — DI контейнер

### Код-стайл

Проект использует:

- **black** для форматирования (line-length = 100)
- **ruff** для линтинга
- **isort** для сортировки импортов

Проверка форматирования:

```bash
black --check .
ruff check .
isort --check-only .
```

Автоисправление:

```bash
black .
isort .
```

## 📖 Документация

- [Architecture](./docs/architecture.md) — детальное описание архитектуры
- [CHANGELOG](./CHANGELOG.md) — история изменений
- Docstrings на русском языке во всех модулях

## 📝 Лицензия

Этот проект создан для MineBridge Minecraft сервера.

## 👤 Автор

**JustCheburek**

- GitHub: [@JustCheburek](https://github.com/JustCheburek)
- Telegram: [@MineBridgeOfficial](https://t.me/MineBridgeOfficial)

