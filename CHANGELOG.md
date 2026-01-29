# История изменений MineBridge

Все важные изменения в проекте документируются в этом файле.

## [25.01] - 2026-01-29

### ✨ Добавлено

- 📝 Полная документация на русском языке
  - README.md с подробным описанием проекта
  - docs/architecture.md с архитектурной схемой
  - Docstrings на русском во всех модулях
- 🧪 Структура тестов (tests/)
- 📦 Переход на pyproject.toml для управления зависимостями
- 🔧 .env.example — шаблон конфигурации с комментариями
- 🗂️ Папка archive/ для устаревших файлов
- ⚙️ Настройки для инструментов разработки (black, ruff, pytest)

### ♻️ Изменено

- Рефакторинг utils модулей:
  - Удалено дублирование кода в `message.py` и `message_formatter.py`
  - Добавлены подробные docstrings с примерами во все utils файлы
  - Улучшена читаемость и структура кода
- Обновлён .gitignore (добавлены archive/, session файлы)
- Консолидированы зависимости в pyproject.toml

### 🗑️ Удалено

- requirements.txt (заменён на pyproject.toml)

### 📦 Перемещено

- old_kb/ → archive/old_kb/
- user_session.session → archive/user_session.session

---

## [24.12] - Предыдущая версия

### Основные возможности

- 🤖 AI интеграция (OpenAI + Google Gemini)
- 📚 RAG система с Jina embeddings
- 🎮 Интеграция с Minecraft API
- 🖼️ Обработка изображений и голоса
- 🎨 Управление стикерами
- 🎲 Игровые механики (freeze, guess)
- Clean Architecture структура проекта
