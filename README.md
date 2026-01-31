# MineBridge Project Map

## 1. Entry Points

- **Entry Script**: `main.py` (Initializes `Container`, `Bot`, `Dispatcher`, and starts polling).
- **Handlers**: `presentation/handlers/`
  - `messages.py`: Main text/media handling.
  - `commands/`: Specific commands (`/start`, `/user`, etc.).
  - `callbacks.py`: UI interactions.

## 2. Data Flow

```mermaid
graph TD
    User[User] -->|Message| TG[Telegram API]
    TG -->|Update| DP[Dispatcher (aiogram)]
    DP -->|Router| Handler[Handlers (presentation)]
    Handler -->|Use| Service[Services (application)]
    Service -->|Use| Repo[Repositories (infrastructure)]
    Service -->|Use| ExtAPI[External APIs (OpenAI, Gemini, web)]
    Repo -->|Read/Write| JSON[JSON Files (data)]
```

## 3. Key Components

### Core (`core/`)

- `Container`: Dependency Injection container. Wires everything together.
- `Config`: Configuration management.

### Application Services (`application/services/`)

- `AIService`: Orchestrates LLM interactions.
- `MediaService`: Handles images, animation, voice.
- `GameService`: Guessing game logic.
- `UserService`: User management.

### Infrastructure (`infrastructure/`)

- **Repositories**: `HistoryRepository`, `ChatLogsRepository` (Storage: JSON).
- **External**: `MinecraftAPI`, `MineBridgeAPI`, `GeminiAPI`, `TavilyAPI`.

## 4. Dependencies

- **Web/Async**: `aiohttp`, `httpx`
- **Telegram**: `aiogram`
- **AI/LLM**: `openai`, `google-generativeai`
- **Data**: `numpy` (usage needs checking), `Pillow` (images).
