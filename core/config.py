"""Configuration management."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from __init__ import __version__

load_dotenv()


@dataclass
class Config:
    """Bot configuration."""

    # Telegram bot
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    BOT_USERNAME: str = "minebridge52bot"
    VERSION: str = __version__
    ADMIN_IDS: list[int] = field(
        default_factory=lambda: [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    )

    # Channels and URLs
    CHANNEL: str = field(default_factory=lambda: os.getenv("CHANNEL", "@MineBridgeOfficial"))
    SUPPORT_URL: str = field(
        default_factory=lambda: os.getenv("SUPPORT_URL", "https://t.me/HelpSupportMineBridgeBot")
    )
    DONATE_URL: str = field(
        default_factory=lambda: os.getenv("DONATE_URL", "https://m-br.ru/shop/buy")
    )

    # API Keys
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    OPENAI_BASE_URL: str = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    )
    GOOGLE_API_KEY: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    JINA_API_KEY: str = field(default_factory=lambda: os.getenv("JINA_API_KEY", ""))
    PIXABAY_API_KEY: str = field(default_factory=lambda: os.getenv("PIXABAY_API_KEY", ""))
    TAVILY_API_KEY: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))

    # MineBridge API
    MB_HOST: str = "майнбридж.рф"

    # Minecraft server
    MC_SERVER_HOST: str = field(default_factory=lambda: os.getenv("MC_SERVER_HOST", ""))
    MC_CACHE_TTL: int = 20

    # Paths
    BASE_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    KB_DIR: Path = field(init=False)
    DATA_DIR: Path = field(init=False)
    RAG_INDEX_DIR: Path = field(init=False)
    PROMPTS_DIR: Path = field(init=False)
    PSEVDO_FILE: Path = field(init=False)
    HISTORY_FILE: Path = field(init=False)
    CHAT_LOGS_FILE: Path = field(init=False)
    FREEZES_FILE: Path = field(init=False)
    GUESSES_FILE: Path = field(init=False)
    TOOLS_FILE: Path = field(init=False)
    VOICES_DIR: Path = field(init=False)

    # Memory limits
    GROUP_MAX_MESSAGES: int = 50
    DM_MAX_MESSAGES: int = 20

    # RAG settings
    RAG_CHUNK_SIZE: int = 1500
    RAG_CHUNK_OVERLAP: int = 150
    RAG_MIN_CHUNKS: int = 1  # Minimum number of chunks to return
    RAG_MAX_CHUNKS: int = 12  # Maximum number of chunks to return
    RAG_SIMILARITY_THRESHOLD: float = 0.75  # Minimum relative score (0.0-1.0) compared to top chunk
    RAG_EMB_MODEL: str = "jina-embeddings-v3"
    RAG_EMB_BATCH: int = 64

    # AI Models
    AI_MODEL: str = field(default_factory=lambda: os.getenv("AI_MODEL", "x-ai/grok-4.1-fast"))
    GEMINI_MODEL: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    IMAGE_MODEL: str = field(
        default_factory=lambda: os.getenv("IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")
    )
    TTS_URL: str = field(default_factory=lambda: os.getenv("TTS_URL", "http://127.0.0.1:8005/tts"))
    ENABLE_TTS: bool = field(
        default_factory=lambda: os.getenv("ENABLE_TTS", "True").lower() == "true"
    )
    MAX_OUTPUT_LENGTH: int = field(
        default_factory=lambda: int(os.getenv("MAX_OUTPUT_LENGTH", "4000"))
    )

    # Freeze options (hours)
    FREEZE_OPTIONS: tuple = (1, 4, 12, 24)

    # Stickers
    STICKERS_FILE: Path = field(init=False)

    def __post_init__(self):
        """Initialize computed paths."""
        self.KB_DIR = self.BASE_DIR / "kb"
        self.DATA_DIR = self.BASE_DIR / "data"
        self.RAG_INDEX_DIR = self.BASE_DIR / ".rag_cache"
        self.PROMPTS_DIR = self.BASE_DIR / "prompts"
        self.PSEVDO_FILE = self.DATA_DIR / "psevdos.json"
        self.HISTORY_FILE = self.DATA_DIR / "chat_logs.json"
        self.CHAT_LOGS_FILE = self.DATA_DIR / "chat_logs.json"
        self.FREEZES_FILE = self.DATA_DIR / "freezes.json"
        self.GUESSES_FILE = self.DATA_DIR / "guesses.json"
        self.STICKERS_FILE = self.DATA_DIR / "stickers.json"
        self.VOICES_DIR = self.BASE_DIR / "voices"
        self.TOOLS_FILE = self.BASE_DIR / "application" / "resources" / "tools.json"

        # Ensure data directory exists
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.VOICES_DIR.mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        """Validate required configuration."""
        from core.exceptions import ConfigurationError

        if not self.BOT_TOKEN:
            raise ConfigurationError("BOT_TOKEN is required in .env")
        if not self.OPENAI_API_KEY:
            raise ConfigurationError("OPENAI_API_KEY is required in .env")
        if not self.MC_SERVER_HOST:
            raise ConfigurationError("MC_SERVER_HOST is required in .env")
        if not self.JINA_API_KEY:
            raise ConfigurationError("JINA_API_KEY is required in .env")
        if not self.GOOGLE_API_KEY:
            raise ConfigurationError("GOOGLE_API_KEY is required in .env")
        if not self.PIXABAY_API_KEY:
            raise ConfigurationError("PIXABAY_API_KEY is required in .env")
        if not self.DONATE_URL.startswith("http"):
            raise ConfigurationError("DONATE_URL must be a valid URL")
        if not self.SUPPORT_URL.startswith("http"):
            raise ConfigurationError("SUPPORT_URL must be a valid URL")
