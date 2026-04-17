"""Утилиты для работы с сообщениями Telegram."""

from __future__ import annotations

from aiogram import types

from utils.message_media import combine_text_and_media, get_media_description


def get_message_text(message: types.Message) -> str:
    """Извлекает текст из сообщения, включая описание медиа."""
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    media_desc = get_media_description(message)
    return combine_text_and_media(text, media_desc) or "(пусто)"


def get_reply_quote(message: types.Message) -> str | None:
    """Извлекает процитированный текст из ответа на сообщение."""
    quote = getattr(message, "quote", None)
    if quote:
        quote_text = getattr(quote, "text", None)
        if quote_text:
            return quote_text.strip()
    return None
