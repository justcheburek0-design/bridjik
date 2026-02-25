"""Prompt and message building mixin for AIService."""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import msgspec.json as mjson
import structlog
from aiogram import types

from utils.chat_helpers import get_author_name, get_message_id, is_bot_message
from utils.media import make_data_url
from utils.message import get_message_text, get_reply_quote

if TYPE_CHECKING:
    from domain.entities import MessageContext

log = structlog.get_logger(__name__)


class AIPromptBuilderMixin:
    """Mixin for building OpenAI messages and system prompts."""

    # Provided by AIService
    config: Any
    chat_logs_repo: Any
    stickers_repo: Any
    memory_repo: Any
    _stickers_cache: Any

    def _build_messages(
        self,
        system_prompt: str,
        context: MessageContext,
        message: types.Message | None = None,
    ) -> list[dict]:
        """Build messages list for OpenAI API."""
        system_prompt = self._build_system_prompt(system_prompt, context)
        messages = [{"role": "system", "content": system_prompt}]

        recent_messages = []
        if message:
            chat_context = self._build_chat_context_from_logs(context, message)
            recent_messages = chat_context.get("recent_messages", [])

        first_user_found = False
        for msg in recent_messages:
            author = msg.get("author", "Unknown")
            is_bot = msg.get("is_bot", False)
            text = msg.get("text", "")
            image_bytes = msg.get("image_bytes")
            mime_type = msg.get("mime_type")

            if not text and not image_bytes:
                continue
            if text and text.startswith("🔄 Бот перезагружен"):
                is_bot = True

            if not first_user_found:
                if is_bot:
                    continue
                first_user_found = True

            role = "assistant" if is_bot else "user"
            content = self._format_multimodal_message(text, author, is_bot, image_bytes, mime_type)
            messages.append({"role": role, "content": content})

        log.info("messages.built", count=len(messages), roles=[m["role"] for m in messages])
        return messages

    def _build_system_prompt(self, system_prompt: str, context: MessageContext) -> str:
        """Build system prompt with stickers, chat info, memories and date."""
        if "stickers" not in self._stickers_cache:
            self._stickers_cache["stickers"] = list(self.stickers_repo.get_all_stickers().keys())
        stickers = self._stickers_cache["stickers"]
        if stickers:
            system_prompt += f"\n\n## Доступные стикеры:\n{', '.join(sorted(stickers))}"

        chat_info: dict = {"title": context.chat.title, "type": context.chat.type}
        with suppress(Exception):
            cached = self.memory_repo.get_chat_metadata(context.chat.id)
            if cached:
                if not chat_info["title"] and cached.get("title"):
                    chat_info["title"] = cached["title"]
                if cached.get("description"):
                    chat_info["description"] = cached["description"]
                if cached.get("invite_link"):
                    chat_info["invite_link"] = cached["invite_link"]

        info_parts = []
        for key, label in [
            ("title", "Название"),
            ("type", "Тип"),
            ("description", "Описание"),
            ("invite_link", "Ссылка"),
        ]:
            if chat_info.get(key):
                info_parts.append(f"{label}: {chat_info[key]}")
        if info_parts:
            system_prompt += "\n\n# Информация о чате:\n" + "\n".join(info_parts) + "\n"

        mem_parts: list[str] = []
        with suppress(Exception):
            if context.chat.id:
                chat_mems = sorted(
                    self.memory_repo.get_chat_memories(context.chat.id),
                    key=lambda m: m.get("timestamp", ""),
                    reverse=True,
                )
                if chat_mems:
                    mem_parts.append(
                        "## Память чата:\n"
                        + "\n".join(
                            f"- {m['content'].strip()}"
                            for m in chat_mems
                            if m.get("content", "").strip()
                        )
                    )

            if context.user and context.user.id:
                user_mems = sorted(
                    self.memory_repo.get_user_memories(context.user.id),
                    key=lambda m: m.get("timestamp", ""),
                    reverse=True,
                )
                if user_mems:
                    uname = context.user.username or context.user.first_name
                    mem_parts.append(
                        f"## Память о пользователе {uname}:\n"
                        + "\n".join(
                            f"- {m['content'].strip()}"
                            for m in user_mems
                            if m.get("content", "").strip()
                        )
                    )

        if mem_parts:
            system_prompt += "\n\n# Память:\n" + "\n\n".join(mem_parts)

        date = datetime.now(tz=ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")
        system_prompt += f"\n\nТекущая дата: {date}"

        return system_prompt

    def _format_multimodal_message(
        self,
        text: str,
        author: str,
        is_bot: bool,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
    ) -> Any:
        """Format a message for OpenAI API, handling text and images."""
        text_content = text if is_bot else f"{author}: {text}"

        if image_bytes and mime_type and self.config.AI_MULTIMODAL_CONTEXT:
            content_parts = []
            if text:
                content_parts.append({"type": "text", "text": text_content})
            content_parts.append(
                {"type": "image_url", "image_url": {"url": make_data_url(image_bytes, mime_type)}}
            )
            return content_parts

        return text_content

    def _build_chat_context_from_logs(
        self, context: MessageContext, message: types.Message
    ) -> dict:
        """Build structured chat context from chat logs."""
        chat_context: dict = {}

        if message.reply_to_message:
            reply_data = self._build_reply_context(message)
            if reply_data:
                chat_context["reply_to"] = reply_data

        recent = self.chat_logs_repo.get_recent_messages(context.chat.id, 10)
        if recent:
            recent_messages = []
            for msg_data in recent:
                message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions = (
                    msg_data
                )

                reaction_text = ""
                if reactions:
                    all_emojis = {e for emojis in reactions.values() for e in emojis}
                    if all_emojis:
                        reaction_text = f" [Реакции: {', '.join(sorted(all_emojis))}]"

                msg_dict: dict = {
                    "message_id": message_id,
                    "author": author,
                    "is_bot": is_bot,
                    "text": text + reaction_text,
                }
                if image_bytes and mime_type:
                    msg_dict["image_bytes"] = image_bytes
                    msg_dict["mime_type"] = mime_type

                recent_messages.append(msg_dict)
            chat_context["recent_messages"] = recent_messages

        return chat_context

    def _build_reply_context(self, message: types.Message) -> dict | None:
        """Build structured reply context."""
        if not message.reply_to_message:
            return None

        replied_msg = message.reply_to_message
        replied_msg_id = get_message_id(replied_msg)
        author_name = (
            "Ассистент" if is_bot_message(replied_msg) else get_author_name(replied_msg, "unknown")
        )

        text = get_message_text(replied_msg)
        if not text or text == "(пусто)":
            log_msg = self.chat_logs_repo.get_message_by_id(message.chat.id, replied_msg_id)
            if log_msg:
                _, _, log_text = log_msg
                if log_text:
                    text = log_text

        return {
            "message_id": replied_msg_id,
            "author": author_name,
            "text": text if text and text != "(пусто)" else None,
            "quote": get_reply_quote(message),
        }
