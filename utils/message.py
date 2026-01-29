"""Утилиты для работы с сообщениями Telegram.

Модуль содержит функции для извлечения и описания медиа-контента из сообщений.
"""

from typing import Optional
from aiogram import types


def get_media_description(message: types.Message) -> str:
    """Генерирует описание медиа из сообщения.

    Функция проверяет тип медиа в сообщении и возвращает читаемое описание
    с эмодзи и дополнительной информацией (длительность, имя файла и т.д.).

    Args:
        message: Telegram сообщение для анализа

    Returns:
        Текстовое описание медиа или пустая строка, если медиа отсутствует

    Examples:
        >>> # Для сообщения с фото вернёт: "🖼️ Фото: подпись к фото"
        >>> # Для голосового: "🎤 Голосовое сообщение (15с)"
    """
    if message.photo:
        caption = getattr(message, "caption", None) or ""
        return f"🖼️ Фото{f': {caption}' if caption else ''}"

    elif message.document:
        doc = message.document
        filename = getattr(doc, "file_name", "документ")
        mime = getattr(doc, "mime_type", "unknown")
        return f"📎 Документ: {filename} ({mime})"

    elif message.voice:
        voice = message.voice
        duration = getattr(voice, "duration", 0)
        return f"🎤 Голосовое сообщение ({duration}с)"

    elif message.sticker:
        sticker = message.sticker
        emoji = getattr(sticker, "emoji", "")
        is_animated = getattr(sticker, "is_animated", False)
        is_video = getattr(sticker, "is_video", False)
        sticker_set = getattr(sticker, "set_name", "неизвестный набор")

        sticker_type = "стикер"
        if is_video:
            sticker_type = "видео-стикер"
        elif is_animated:
            sticker_type = "анимированный стикер"

        return f"🎨 {sticker_type} {emoji} из '{sticker_set}'"

    elif message.animation:
        animation = message.animation
        duration = getattr(animation, "duration", 0)
        filename = getattr(animation, "file_name", "гифка")
        return f"🎬 Гифка '{filename}' ({duration}с)"

    elif message.video:
        video = message.video
        duration = getattr(video, "duration", 0)
        return f"📹 Видео ({duration}с)"

    elif message.audio:
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
    """Извлекает текст из сообщения, включая описание медиа.

    Комбинирует текстовое содержимое сообщения (text/caption) с описанием медиа.

    Args:
        message: Telegram сообщение

    Returns:
        Полный текст сообщения с описанием медиа или "(пусто)" если текст отсутствует

    Examples:
        >>> # Фото с подписью "Котик" вернёт: "🖼️ Фото: Котик"
        >>> # Обычное сообщение "Привет" вернёт: "Привет"
    """
    from utils.message_formatter import combine_text_and_media

    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    media_desc = get_media_description(message)

    return combine_text_and_media(text, media_desc) or "(пусто)"


def get_reply_quote(message: types.Message) -> Optional[str]:
    """Извлекает процитированный текст из ответа на сообщение.

    Используется для получения цитаты при ответе на конкретную часть сообщения
    (доступно в Telegram Bot API 7.0+).

    Args:
        message: Telegram сообщение с возможной цитатой

    Returns:
        Текст цитаты или None, если цитата отсутствует

    Note:
        Работает только с новыми версиями Telegram Bot API, которые поддерживают quote.
    """
    # Проверка на наличие цитаты в сообщении (Telegram Bot API 7.0+)
    quote = getattr(message, "quote", None)
    if quote:
        quote_text = getattr(quote, "text", None)
        if quote_text:
            return quote_text.strip()

    return None
