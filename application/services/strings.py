"""Strings and system prompts service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from aiogram import types
from aiogram.enums import ChatType

from core.config import Config

logger = logging.getLogger(__name__)


class StringsService:
    """Service for loading system prompts and strings."""

    def __init__(self, config: Config):
        self.config = config
        self._prompt_cache: Dict[str, tuple[float, str]] = {}

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

    def load_system_prompt_for_chat(self, chat: types.Chat) -> str:
        """Load chat-specific system prompt text, falling back to default."""
        try:
            # 1. Load the template
            template_path = self.config.PROMPTS_DIR / "template.md"
            template_text = "{prompt}"  # Default fallback if template is missing
            if template_path.exists():
                loaded_template = self._read_txt_prompt(template_path)
                if loaded_template:
                    template_text = loaded_template

            # 2. Determine raw prompt text (specific to chat or default)
            raw_prompt_text = ""

            # Try finding group-specific prompt first
            if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                default_path = self.config.PROMPTS_DIR / "default.md"
                if default_path.exists():
                    raw_prompt_text = self._read_txt_prompt(default_path)
                    if raw_prompt_text:
                        logger.debug("Loaded default prompt from %s", default_path)

                group_path = self.config.PROMPTS_DIR / f"{chat.id}.txt"
                if group_path.exists():
                    raw_prompt_text = self._read_txt_prompt(group_path)
                    if raw_prompt_text:
                        logger.debug("Loaded group prompt from %s", group_path)

            # Final fallback if files are completely missing
            if not raw_prompt_text:
                logger.warning("No prompt .txt files found; using builtin fallback")
                raw_prompt_text = ""

            # 3. Apply template
            final_text = template_text.replace("{prompt}", raw_prompt_text)

            return final_text

        except Exception:
            logger.exception("Failed to load .txt prompt")
            return "Ты — бот MineBridge. Произошла ошибка загрузки промта."
