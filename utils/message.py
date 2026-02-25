"""Утилиты для работы с сообщениями Telegram."""

from __future__ import annotations

from aiogram import types


def get_media_description(message: types.Message) -> str:
    """Генерирует текстовое описание медиа из сообщения."""
    if message.photo:
        caption = getattr(message, "caption", None) or ""
        return f"🖼️ Фото{f': {caption}' if caption else ''}"

    if message.document:
        doc = message.document
        filename = getattr(doc, "file_name", "документ")
        mime = getattr(doc, "mime_type", "unknown")
        return f"📎 Документ: {filename} ({mime})"

    if message.voice:
        duration = getattr(message.voice, "duration", 0)
        return f"🎤 Голосовое сообщение ({duration}с)"

    if message.sticker:
        sticker = message.sticker
        emoji = getattr(sticker, "emoji", "")
        is_animated = getattr(sticker, "is_animated", False)
        is_video = getattr(sticker, "is_video", False)
        sticker_set = getattr(sticker, "set_name", "неизвестный набор")
        sticker_type = (
            "видео-стикер" if is_video else ("анимированный стикер" if is_animated else "стикер")
        )
        return f"🎨 {sticker_type} {emoji} из '{sticker_set}'"

    if message.animation:
        duration = getattr(message.animation, "duration", 0)
        filename = getattr(message.animation, "file_name", "гифка")
        return f"🎬 Гифка '{filename}' ({duration}с)"

    if message.video:
        duration = getattr(message.video, "duration", 0)
        return f"📹 Видео ({duration}с)"

    if message.audio:
        audio = message.audio
        duration = getattr(audio, "duration", 0)
        performer = getattr(audio, "performer", None)
        title = getattr(audio, "title", None)
        desc = "🎵 Аудио"
        if performer:
            desc += f" - {performer}"
        if title:
            desc += f": {title}"
        desc += f" ({duration}с)"
        return desc

    return ""


def get_message_text(message: types.Message) -> str:
    """Извлекает текст из сообщения, включая описание медиа."""
    from utils.message_formatter import combine_text_and_media

    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    media_desc = get_media_description(message)
    return combine_text_and_media(text, media_desc) or "(пусто)"


def get_reply_quote(message: types.Message) -> str | None:
    """Извлекает процитированный текст из ответа на сообщение (Telegram Bot API 7.0+)."""
    quote = getattr(message, "quote", None)
    if quote:
        quote_text = getattr(quote, "text", None)
        if quote_text:
            return quote_text.strip()
    return None
