"""Утилиты для форматирования сообщений."""

from __future__ import annotations

from aiogram import types

from utils.message import get_media_description


def combine_text_and_media(text: str, media_desc: str) -> str:
    """Комбинирует текст и описание медиа в одну строку."""
    if text and media_desc:
        if media_desc.startswith("🎤 Голосовое сообщение"):
            return f"{media_desc}: {text}"
        return f"{media_desc}\\n\\n{text}"
    return media_desc or text or ""


def build_message_text_for_save(message: types.Message, prompt: str) -> str:
    """Формирует текст сообщения для сохранения в историю/логи."""
    media_desc = get_media_description(message)
    return combine_text_and_media(prompt, media_desc) or "(пусто)"


def format_chat_history_entry(role: str, text: str) -> str:
    """Форматирует запись для истории чата."""
    who = "Пользователь" if role == "user" else "Ассистент"
    return f"{who}: {text}"


def format_chat_log_entry(message_id: int | None, author: str, is_bot: bool, text: str) -> str:
    """Форматирует запись для лога чата."""
    role = "Ассистент" if is_bot else author
    if message_id:
        return f"[{message_id}] {role}: {text}"
    return f"{role}: {text}"
