# MineBridge Bot

Это отрефакторенная версия MineBridge Telegram бота с чистой архитектурой и модульной структурой.

## Структура проекта

```
minebridge/
├── core/               # Ядро: конфигурация, DI, исключения
├── domain/             # Доменный слой: сущности, интерфейсы
├── infrastructure/     # Инфраструктура: репозитории, внешние API
├── application/        # Приложение: сервисы, middleware
├── presentation/       # Представление: handlers, keyboards, formatters
└── utils/              # Утилиты
```

## Основные улучшения

### 1. Устранение дублирования кода

- ✅ **Проверка подписки** - вынесена в `SubscriptionService`
- ✅ **Получение имени пользователя** - `UserService.get_display_name()`
- ✅ **Обработка ошибок** - декоратор `@handle_errors`
- ✅ **Клавиатуры** - `KeyboardBuilder` с методами для разных типов
- ✅ **Форматирование** - `Formatter` для единообразного вывода

### 2. Разделение ответственности

- **Handlers** (presentation) - только получение данных из Telegram
- **Services** (application) - бизнес-логика
- **Repositories** (infrastructure) - работа с данными (JSON)
- **External APIs** (infrastructure) - внешние API (MC, MB, Gemini)

### 3. Dependency Injection

Все зависимости создаются в `Container` и передаются через DI:

```python
container = Container()
# Автоматическое внедрение зависимостей в handlers
```

### 4. Совместимость с данными

Все JSON файлы остаются совместимыми со старой версией:
- `data/history.json`
- `data/psevdos.json`
- `data/freezes.json`
- `data/guesses.json`
- `data/chat_logs.json`

### 5. Обработка медиа-файлов (WebP стикеры и GIF анимации)

Добавлена автоматическая конвертация несовместимых форматов:
- ✅ **WebP стикеры** → PNG для совместимости с AI APIs (OpenAI, xAI)
- ✅ **Видео-стикеры** → первый кадр в PNG (требует ffmpeg)
- ✅ **TGS анимированные стикеры** → PNG первый кадр (требует rlottie)
- ✅ **GIF анимации** → первый кадр в PNG для анализа (требует ffmpeg для видеофайлов)
- ✅ **Улучшена обработка ошибок** - система продолжает работать даже при ошибке скачивания медиа

## Запуск

### Предварительные требования

#### 1. Установка Python пакетов

```bash
pip install -r requirements.txt
```

#### 2. Установка ffmpeg (для поддержки видео-стикеров и гифок)

**Windows:**
```bash
# Через chocolatey (если установлен)
choco install ffmpeg

# Или скачайте вручную с https://ffmpeg.org/download.html
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

#### 3. Опционально: Установка rlottie (для поддержки TGS анимированных стикеров)

```bash
pip install rlottie-python
```

### Из папки newbot:

```bash
python -m newbot
```

### Из корня проекта:

```bash
python -m newbot
```

## Миграция со старой версии

### Шаг 1: Проверка .env

Убедитесь, что все переменные окружения настроены:

```env
BOT_TOKEN=your_token
OPENAI_API_KEY=your_key
GOOGLE_API_KEY=your_key
JINA_API_KEY=your_key
PIXABAY_API_KEY=your_key
MC_SERVER_HOST=your_server
CHANNEL=@YourChannel
SUPPORT_URL=https://...
DONATE_URL=https://...
```

### Шаг 2: Тестирование

1. Запустите новую версию параллельно со старой (на тестовом боте)
2. Проверьте основные команды: /start, /status, /player, /game
3. Проверьте автоответы в личке и группе
4. Проверьте заморозку и разморозку

### Шаг 3: Полная замена

Когда убедитесь, что все работает:

1. Остановите старую версию (main.py)
2. Скопируйте файлы из newbot/ в корень:
   ```bash
   # Создайте бэкап старых файлов
   mkdir backup_old
   cp *.py backup_old/
   
   # Замените файлы
   cp -r newbot/* .
   ```
3. Запустите новую версию

### Дополнительные улучшения:

- [ ] Добавить unit тесты для сервисов
- [ ] Добавить интеграционные тесты для handlers
- [ ] Настроить CI/CD
- [ ] Добавить мониторинг и метрики
- [ ] Добавить rate limiting
- [ ] Документация API для сервисов

## Архитектура

### Clean Architecture Layers

```
Presentation → Application → Domain ← Infrastructure
     ↓              ↓           ↓           ↓
  Handlers      Services    Entities    Repositories
  Keyboards                Interfaces   External APIs
  Formatters
```

### Пример создания нового handler

```python
# newbot/presentation/handlers/commands/mycommand.py
from aiogram import types, Router
from aiogram.filters import Command

router = Router()

@router.message(Command("mycommand"))
async def cmd_mycommand(
    message: types.Message,
    my_service: MyService  # Автоматически внедряется из Container
):
    result = await my_service.do_something()
    await message.reply(result)
```

### Пример создания нового сервиса

```python
# newbot/application/services/my_service.py
class MyService:
    def __init__(self, repository: IMyRepository):
        self.repo = repository
    
    async def do_something(self) -> str:
        data = self.repo.get_data()
        return f"Result: {data}"
```

## Поддержка

Если возникли вопросы или проблемы:

1. Проверьте логи - они более подробные в новой версии
2. Убедитесь, что все зависимости установлены: `pip install -r requirements.txt`
3. Проверьте .env файл
4. Создайте issue в репозитории

## Преимущества новой архитектуры

1. **Легче тестировать** - каждый компонент изолирован
2. **Легче расширять** - добавление новых функций не ломает старые
3. **Легче понять** - четкое разделение ответственности
4. **Легче поддерживать** - нет дублирования кода
5. **Легче рефакторить** - изменения локализованы в одном месте

---

**Дата рефакторинга:** 2025-10-20

