"""System prompt builder mixin for AIService."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog

if TYPE_CHECKING:
    from domain.entities import MessageContext

log = structlog.get_logger(__name__)


class AIPromptBuilderMixin:
    """Mixin for building the system prompt injected into every agent run."""

    # Provided by AIService
    config: Any
    stickers_repo: Any
    memory_repo: Any
    _stickers_cache: Any

    def _build_system_prompt(self, system_prompt: str, context: "MessageContext") -> str:
        """Assemble full system prompt: base + stickers + chat info + memories + date."""
        system_prompt += self._section_stickers()
        system_prompt += self._section_chat_info(context)
        system_prompt += self._section_memories(context)
        system_prompt += (
            f"\n\nТекущая дата: {datetime.now(tz=ZoneInfo('Europe/Moscow')).strftime('%Y-%m-%d')}"
        )
        return system_prompt

    def _section_stickers(self) -> str:
        if "stickers" not in self._stickers_cache:
            self._stickers_cache["stickers"] = list(self.stickers_repo.get_all_stickers().keys())
        stickers = self._stickers_cache["stickers"]
        return f"\n\n## Доступные стикеры:\n{', '.join(sorted(stickers))}" if stickers else ""

    def _section_chat_info(self, context: "MessageContext") -> str:
        chat_info: dict = {"title": context.chat.title, "type": context.chat.type}
        with suppress(Exception):
            if cached := self.memory_repo.get_chat_metadata(context.chat.id):
                if not chat_info["title"] and cached.get("title"):
                    chat_info["title"] = cached["title"]
                for key in ("description", "invite_link"):
                    if cached.get(key):
                        chat_info[key] = cached[key]

        labels = [
            ("title", "Название"),
            ("type", "Тип"),
            ("description", "Описание"),
            ("invite_link", "Ссылка"),
        ]
        parts = [f"{label}: {chat_info[key]}" for key, label in labels if chat_info.get(key)]
        return ("\n\n# Информация о чате:\n" + "\n".join(parts) + "\n") if parts else ""

    def _section_memories(self, context: "MessageContext") -> str:
        mem_parts: list[str] = []
        with suppress(Exception):
            if context.chat.id:
                mem_parts.extend(
                    self._format_memories_block(
                        "## Память чата:",
                        self.memory_repo.get_chat_memories(context.chat.id),
                    )
                )
            if context.user and context.user.id:
                uname = context.user.username or context.user.first_name
                mem_parts.extend(
                    self._format_memories_block(
                        f"## Память о пользователе {uname}:",
                        self.memory_repo.get_user_memories(context.user.id),
                    )
                )
        return ("\n\n# Память:\n" + "\n\n".join(mem_parts)) if mem_parts else ""

    @staticmethod
    def _format_memories_block(header: str, memories: list[dict]) -> list[str]:
        items = [
            f"- {m['content'].strip()}"
            for m in sorted(memories, key=lambda m: m.get("timestamp", ""), reverse=True)
            if m.get("content", "").strip()
        ]
        return [header + "\n" + "\n".join(items)] if items else []
