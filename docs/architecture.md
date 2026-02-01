# Архитектура MineBridge Telegram Bot

## Обзор

MineBridge построен на принципах **Clean Architecture** (Чистая Архитектура), что обеспечивает:

- ✅ Независимость от фреймворков
- ✅ Тестируемость
- ✅ Независимость от UI
- ✅ Независимость от базы данных
- ✅ Независимость от внешних сервисов

## Диаграмма слоёв

```
┌─────────────────────────────────────────────────────────┐
│                     Presentation                        │
│  (Telegram handlers, keyboards, formatters)             │
│  ↓ использует                                           │
│                  Application                            │
│  (Services: AI, RAG, Media, Subscription, Game, User)   │
│  ↓ использует                                           │
│                  Infrastructure                         │
│  (External API, Repositories, Bot, OpenAI Client)       │
│  ↓ реализует                                            │
│                      Domain                             │
│  (Entities, Interfaces - независимый слой)              │
└─────────────────────────────────────────────────────────┘
              ↑
              Core (Config, Dependencies, Exceptions)
              Utils (вспомогательные функции)
```

## Слои архитектуры

### 1. Domain (Домен) 🎯

**Расположение**: `domain/`

**Ответственность**: Независимые бизнес-сущности и интерфейсы

**Файлы**:

- `entities.py` — сущности (User, Chat, MessageContext)
- `interfaces.py` — интерфейсы репозиториев

**Принципы**:

- ❌ Нет зависимостей от других слоёв
- ✅ Чистые Python классы (dataclasses)
- ✅ Бизнес-правила в методах сущностей

**Пример**:

```python
@dataclass
class User:
    """Сущность пользователя."""
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    psevdo: Optional[str] = None

    def get_display_name(self) -> str:
        """Получить лучшее отображаемое имя."""
        return self.psevdo or self.first_name or self.username or "Пользователь"
```

---

### 2. Application (Приложение) 🔧

**Расположение**: `application/`

**Ответственность**: Бизнес-логика и сервисы

**Структура**:

```
application/
├── services/
│   ├── ai.py          # AI completion (OpenAI + Gemini)
│   ├── rag.py         # RAG система для контекста
│   ├── media.py       # Обработка медиа (фото, генерация через AI, голос, стикеры)
│   ├── game.py        # Игровые механики
│   ├── subscription.py # Проверка подписок
│   ├── user.py        # Управление пользователями
│   └── strings.py     # Текстовые строки
└── middleware/
    ├── logging.py     # Логирование запросов
    └── subscription.py # Middleware для проверки подписки
```

**Принципы**:

- ✅ Использует интерфейсы из Domain
- ✅ Не зависит от деталей Infrastructure
- ✅ Содержит всю бизнес-логику

**Пример**:

```python
class AIService:
    """Сервис для AI completion."""

    def __init__(self, openai_client, gemini_client, config, ...):
        self.openai_client = openai_client
        # ...

    async def complete(self, context: MessageContext, history: list) -> str:
        """Генерация ответа AI на основе контекста."""
        # Бизнес-логика выбора модели и генерации ответа
```

---

### 3. Infrastructure (Инфраструктура) 🏗️

**Расположение**: `infrastructure/`

**Ответственность**: Реализация внешних зависимостей

**Структура**:

```
infrastructure/
├── external/          # Клиенты внешних API
│   ├── gemini.py     # Google Gemini API
│   ├── mb_api.py     # MineBridge API
│   ├── mc_api.py     # Minecraft сервер API
│   ├── news_api.py   # Новостные API
│   └── tavily_api.py # Tavily поиск
├── repositories/      # Реализация репозиториев
│   ├── base.py       # Базовый репозиторий (JSON)
│   ├── chat_logs.py  # Логи чатов
│   ├── freezes.py    # Заморозки
│   ├── guesses.py    # Угадайки
│   ├── history.py    # История сообщений
│   ├── psevdos.py    # Псевдонимы
│   └── stickers.py   # Стикеры
├── bot.py            # Telegram Bot instance
└── openai_client.py  # OpenAI клиент
```

**Принципы**:

- ✅ Реализует интерфейсы из Domain
- ✅ Работает с внешними API и файлами
- ✅ Изолирует детали от Application

**Пример**:

```python
class HistoryRepository(BaseRepository):
    """Репозиторий истории чата - реализация интерфейса."""

    def get_history(self, chat_id: int, limit: int) -> list:
        """Получить историю чата."""
        # Работа с JSON файлом
```

---

### 4. Presentation (Представление) 📱

**Расположение**: `presentation/`

**Ответственность**: Обработка Telegram событий

**Структура**:

```
presentation/
├── handlers/
│   ├── commands/     # Команды бота
│   │   ├── start.py  # /start
│   │   ├── user.py   # /me, /nick, /clear
│   │   ├── info.py   # /help, /info, /news
│   │   ├── server.py # /server, /online
│   │   ├── game.py   # /freeze, /guess
│   │   └── admin.py  # Админские команды
│   ├── messages.py   # Обработка текстовых сообщений
│   ├── callbacks.py  # Inline кнопки
│   └── admin_stickers.py # Управление стикерами
├── keyboards.py      # Inline клавиатуры
├── formatters.py     # Форматирование ответов
└── decorators.py     # Декораторы для handlers
```

**Принципы**:

- ✅ Зависит только от Application
- ✅ Конвертирует Telegram типы в Domain entities
- ✅ Использует aiogram роутеры

**Пример**:

```python
@router.message(Command("start"))
async def cmd_start(
    message: types.Message,
    ai_service: AIService
):
    """Обработчик команды /start."""
    # Извлечение данных из Telegram
    user = User(
        id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

    # Вызов бизнес-логики
    response = await ai_service.complete(...)
    await message.answer(response)
```

---

### 5. Core (Ядро) ⚙️

**Расположение**: `core/`

**Ответственность**: Конфигурация и связывание

**Файлы**:

- `config.py` — загрузка конфигурации из .env
- `dependencies.py` — DI контейнер (создание и связывание сервисов)
- `exceptions.py` — кастомные исключения

**Принципы**:

- ✅ Создаёт инстансы всех сервисов
- ✅ Инжектит зависимости в handlers
- ✅ Управляет жизненным циклом

**Пример**:

```python
class Container:
    """Dependency Injection контейнер."""

    def __init__(self):
        self.config = Config()
        self.bot = create_bot(self.config)
        self.openai_client = create_openai_client(self.config)

        # Repositories
        self.history_repo = HistoryRepository(self.config.HISTORY_FILE)

        # Services
        self.ai_service = AIService(
            openai_client=self.openai_client,
            config=self.config,
            history_repo=self.history_repo
        )
```

---

### 6. Utils (Утилиты) 🛠️

**Расположение**: `utils/`

**Ответственность**: Вспомогательные функции

**Файлы**:

- `message.py` — работа с Telegram сообщениями
- `message_formatter.py` — форматирование сообщений
- `text.py` — обработка текста (truncate, hash)
- `validation.py` — валидация данных
- `chat_helpers.py` — помощники для чатов
- `error_handlers.py` — обработка ошибок
- `html_edit.py` — очистка HTML
- `markdown_to_html.py` — конвертация Markdown → HTML

**Принципы**:

- ✅ Чистые функции без состояния
- ✅ Могут использоваться в любом слое
- ✅ Не имеют бизнес-логики

---

## Поток данных

### Обработка текстового сообщения

```
1. User → Telegram → Presentation (messages.py)
   ↓
2. Presentation создаёт MessageContext (Domain entity)
   ↓
3. Presentation вызывает AIService.complete() (Application)
   ↓
4. AIService получает историю из HistoryRepository (Infrastructure)
   ↓
5. AIService получает RAG контекст из RAGService (Application)
   ↓
6. AIService вызывает OpenAI API (Infrastructure)
   ↓
7. AIService сохраняет ответ в HistoryRepository (Infrastructure)
   ↓
8. Presentation отправляет ответ в Telegram
```

### Обработка изображения

```
1. User отправляет фото → Presentation
   ↓
2. Presentation вызывает MediaService.download_photo() (Application)
   ↓
3. MediaService скачивает через Bot API (Infrastructure)
   ↓
4. Presentation создаёт MessageContext с image_bytes
   ↓
5. AIService обрабатывает через Gemini (поддержка vision)
```

### Генерация изображения через AI

```
1. AI генерирует ответ с placeholder [gen_photo:описание]
   ↓
2. MediaService.long_text() обнаруживает placeholder
   ↓
3. MediaService.generate_image_via_ai() вызывает OpenAI API
   ↓
4. Скачивает сгенерированное изображение
   ↓
5. Отправляет изображение пользователю через Telegram
```

### Поиск изображения из интернета

```
1. AI генерирует ответ с placeholder [find_photo:запрос]
   ↓
2. MediaService.long_text() обнаруживает placeholder
   ↓
3. MediaService._resolve_photo_payload() проверяет:
   - Локальные файлы в photos/
   - Поиск через Pixabay API
   ↓
4. Скачивает найденное изображение
   ↓
5. Отправляет пользователю через Telegram
```

## Зависимости между слоями

```
Presentation → Application → Infrastructure ↔ Domain
     ↓              ↓              ↓
   Core ←────────────┴──────────────┘
     ↑
   Utils (используется всеми)
```

## Преимущества архитектуры

✅ **Тестируемость** — можно тестировать каждый слой изолированно  
✅ **Гибкость** — легко менять реализации (например, JSON → PostgreSQL)  
✅ **Понятность** — чёткое разделение ответственности  
✅ **Масштабируемость** — легко добавлять новые фичи  
✅ **Независимость** — Domain не зависит от фреймворков

## Паттерны проектирования

- **Dependency Injection** — через Container
- **Repository** — абстракция хранилищ данных
- **Service Layer** — бизнес-логика в сервисах
- **Strategy** — выбор AI модели (OpenAI vs Gemini)
