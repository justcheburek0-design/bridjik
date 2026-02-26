"""Configuration management."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from pydantic import field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

from __init__ import __version__
from core.exceptions import ConfigurationError

_BASE_DIR = Path(__file__).resolve().parent.parent


class Config(BaseSettings):
    """Bot configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram bot
    BOT_TOKEN: str = ""
    BOT_USERNAME: str = "minebridge52bot"
    VERSION: str = __version__
    ADMIN_IDS: list[int] = []

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return list(v) if v else []

    # Channels and URLs
    CHANNEL: str = "@MineBridgeOfficial"
    SUPPORT_URL: str = "https://t.me/HelpSupportMineBridgeBot"
    DONATE_URL: str = "https://m-br.ru/shop/buy"

    # API Keys
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"
    GOOGLE_API_KEY: str = ""
    PIXABAY_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # MineBridge API
    MB_HOST: str = "майнбридж.рф"

    # Minecraft server
    MC_SERVER_HOST: str = ""
    MC_CACHE_TTL: int = 20

    # Memory limits
    GROUP_MAX_MESSAGES: int = 25
    DM_MAX_MESSAGES: int = 15

    # AI Models
    AI_MODEL: str = "x-ai/grok-4.1-fast"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    IMAGE_MODEL: str = "black-forest-labs/flux.2-klein-4b"
    TTS_URL: str = "http://127.0.0.1:8005/tts"
    ENABLE_TTS: bool = True
    MAX_OUTPUT_LENGTH: int = 4000

    # Context settings
    AI_MULTIMODAL_CONTEXT: bool = True

    # Freeze options (hours)
    FREEZE_OPTIONS: Tuple[int, ...] = (1, 4, 12, 24)

    # Computed paths (set in model_validator)
    BASE_DIR: Path = _BASE_DIR
    DATA_DIR: Path = _BASE_DIR / "data"
    PROMPTS_DIR: Path = _BASE_DIR / "prompts"
    HISTORY_FILE: Path = _BASE_DIR / "data" / "chat_logs.json"
    CHAT_LOGS_FILE: Path = _BASE_DIR / "data" / "chat_logs.json"
    FREEZES_FILE: Path = _BASE_DIR / "data" / "freezes.json"
    STICKERS_FILE: Path = _BASE_DIR / "data" / "stickers.json"
    MEMORIES_FILE: Path = _BASE_DIR / "data" / "memories.json"
    VOICES_DIR: Path = _BASE_DIR / "voices"
    TOOLS_FILE: Path = _BASE_DIR / "application" / "resources" / "tools.json"

    @model_validator(mode="after")
    def _ensure_dirs(self) -> "Config":
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.VOICES_DIR.mkdir(parents=True, exist_ok=True)
        return self

    def validate(self) -> None:
        """Validate required configuration."""
        checks = [
            (self.BOT_TOKEN, "BOT_TOKEN is required in .env"),
            (self.OPENAI_API_KEY, "OPENAI_API_KEY is required in .env"),
            (self.MC_SERVER_HOST, "MC_SERVER_HOST is required in .env"),
            (self.GOOGLE_API_KEY, "GOOGLE_API_KEY is required in .env"),
            (self.PIXABAY_API_KEY, "PIXABAY_API_KEY is required in .env"),
        ]
        for value, msg in checks:
            if not value:
                raise ConfigurationError(msg)

        if not self.DONATE_URL.startswith("http"):
            raise ConfigurationError("DONATE_URL must be a valid URL")
        if not self.SUPPORT_URL.startswith("http"):
            raise ConfigurationError("SUPPORT_URL must be a valid URL")
