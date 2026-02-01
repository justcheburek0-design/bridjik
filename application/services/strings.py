"""Strings and system prompts service."""

import logging
from pathlib import Path
from typing import Dict, Tuple

from aiogram import types
from aiogram.enums import ChatType

from core.config import Config

logger = logging.getLogger(__name__)


class StringsService:
    """Service for loading system prompts and strings."""

    def __init__(self, config: Config):
        self.config = config
        self._prompt_cache: Dict[str, Tuple[float, str]] = {}

    def _read_txt_prompt(self, path: Path) -> str:
        """Cache-aware reader for prompt override files stored on disk."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return ""

        cache_key = str(path)
        cached = self._prompt_cache.get(cache_key)
        if cached and cached[0] == mtime:
            return cached[1]

        try:
            raw = path.read_text(encoding="utf-8")
            if raw.startswith("\ufeff"):
                raw = raw.lstrip("\ufeff")
            text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
            self._prompt_cache[cache_key] = (mtime, text)
            return text
        except Exception:
            logger.exception("Failed to read prompt from %s", path)
            return ""

    def load_system_prompt_for_chat(self, chat: types.Chat, guesses_repo=None) -> str:
        """Load chat-specific system prompt text, falling back to default."""
        try:
            if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                group_path = self.config.PROMPTS_DIR / f"{chat.id}.txt"
                if group_path.exists():
                    text = self._read_txt_prompt(group_path)
                    if text:
                        logger.debug("Loaded group prompt from %s", group_path)
                        # Check if game is active and add to prompt
                        if guesses_repo:
                            guessed_obj = guesses_repo.get_guess(chat.id)
                            if guessed_obj:
                                text += f"\n\n# Текущая игра 'Кто я?'\nТы загадал(а) для пользователя: {guessed_obj}\nНе раскрывай это слово напрямую. Отвечай на воп росы пользователя о загаданном предмете, помогая ему угадать."
                        return text

            default_path = self.config.PROMPTS_DIR / "default.txt"
            if default_path.exists():
                text = self._read_txt_prompt(default_path)
                if text:
                    logger.debug("Loaded default prompt")
                    # Check if game is active and add to prompt
                    if guesses_repo:
                        guessed_obj = guesses_repo.get_guess(chat.id)
                        if guessed_obj:
                            text += f"\n\n# Текущая игра 'Кто я?'\nТы загадал(а) для пользователя: {guessed_obj}\nНе раскрывай это слово напрямую. Отвечай на вопросы пользователя о загаданном предмете, помогая ему угадать."
                    return text
        except FileNotFoundError:
            logger.warning("Prompt .txt file not found; using builtin fallback")
        except Exception:
            logger.exception("Failed to load .txt prompt")

        base_text = "Ты — бот MineBridge, помощник игроков Minecraft-сервера. Отвечай кратко, дружелюбно и по делу."

        # Check if game is active and add to prompt
        if guesses_repo:
            guessed_obj = guesses_repo.get_guess(chat.id)
            if guessed_obj:
                base_text += f"\n\n# Текущая игра 'Кто я?'\nТы загадал(а) для пользователя: {guessed_obj}\nНе раскрывай это слово напрямую. Отвечай на вопросы пользователя о загаданном предмете, помогая ему угадать."

        return base_text
