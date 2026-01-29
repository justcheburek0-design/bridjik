"""Утилиты для форматирования сообщений.

Модуль содержит функции для форматирования сообщений, комбинирования текста
с медиа-описаниями и создания записей для истории чата и логов.
"""

from typing import Optional
from aiogram import types

from utils.message import get_message_text, get_reply_quote, get_media_description


def format_reply_message(
    message: types.Message,
    author_name: str,
    current_msg_id: Optional[int] = None,
    replied_msg_id: Optional[int] = None,
    quote: Optional[str] = None,
    is_private: bool = False,
    replied_message_text: Optional[str] = None,
) -> str:
    """Форматирует сообщение-ответ для контекста AI.

    Создаёт читаемое представление сообщения, которое является ответом на другое сообщение,
    включая информацию о процитированном тексте.

    Args:
        message: Telegram сообщение
        author_name: Отображаемое имя автора
        current_msg_id: ID текущего сообщения (опционально)
        replied_msg_id: ID сообщения, на которое отвечают (опционально)
        quote: Процитированный текст (опционально)
        is_private: Флаг приватного чата
        replied_message_text: Полный текст сообщения, на которое отвечают (опционально)

    Returns:
        Форматированная строка с информацией об ответе

    Examples:
        >>> # В группе: "[123] Иван (отвечая на сообщение 122): Согласен"
        >>> # В личке: "Пользователь (отвечая на \"твой текст\"): Ответ"
    """
    current_text = get_message_text(message)

    # Определяем метку автора
    author_label = "Пользователь" if is_private else author_name

    # Формируем информацию о сообщении, на которое отвечают
    if replied_message_text:
        # Используем полный текст, если доступен (обрезаем до 100 символов)
        truncated = replied_message_text[:100]
        if len(replied_message_text) > 100:
            truncated += "..."
        replied_info = f'сообщение {replied_msg_id} ("{truncated}")'
    elif quote:
        # Используем цитату, если доступна
        replied_info = f'"{quote}"'
    elif replied_msg_id:
        # Используем только ID сообщения
        replied_info = f"сообщение {replied_msg_id}"
    else:
        replied_info = "сообщение"

    # Форматируем финальное сообщение
    if current_msg_id:
        return f"[{current_msg_id}] {author_label} (отвечая на {replied_info}): {current_text}"
    else:
        return f"{author_label} (отвечая на {replied_info}): {current_text}"


def combine_text_and_media(text: str, media_desc: str) -> str:
    """Комбинирует текст и описание медиа.

    Объединяет текстовое содержимое с описанием медиа в правильном порядке.
    Если оба параметра пусты, возвращает пустую строку.

    Args:
        text: Текстовое содержимое
        media_desc: Описание медиа-контента

    Returns:
        Объединённая строка или пустая строка

    Examples:
        >>> combine_text_and_media("Привет", "🖼️ Фото")
        "🖼️ Фото\\n\\nПривет"
        >>> combine_text_and_media("", "🎤 Голосовое сообщение (15с)")
        "🎤 Голосовое сообщение (15с)"
        >>> combine_text_and_media("Текст", "")
        "Текст"
    """
    if text and media_desc:
        return f"{media_desc}\\n\\n{text}"
    elif media_desc:
        return media_desc
    elif text:
        return text
    else:
        return ""


def build_message_text_for_save(message: types.Message, prompt: str) -> str:
    """Формирует текст сообщения для сохранения в историю/логи.

    Комбинирует пользовательский текст prompt с описанием медиа из сообщения.

    Args:
        message: Telegram сообщение
        prompt: Текст промпта пользователя

    Returns:
        Объединённый текст с медиа или "(пусто)" если текст отсутствует
    """
    media_desc = get_media_description(message)
    return combine_text_and_media(prompt, media_desc) or "(пусто)"


def format_chat_history_entry(role: str, text: str) -> str:
    """Форматирует запись для истории чата.

    Создаёт читаемую запись для истории переписки с AI.

    Args:
        role: Роль отправителя ("user" или "assistant")
        text: Текст сообщения

    Returns:
        Форматированная строка записи

    Examples:
        >>> format_chat_history_entry("user", "Как дела?")
        "Пользователь: Как дела?"
        >>> format_chat_history_entry("assistant", "Отлично!")
        "Ассистент: Отлично!"
    """
    who = "Пользователь" if role == "user" else "Ассистент"
    return f"{who}: {text}"


def format_chat_log_entry(message_id: Optional[int], author: str, is_bot: bool, text: str) -> str:
    """Форматирует запись для лога чата.

    Создаёт запись для общего лога сообщений с указанием ID и автора.

    Args:
        message_id: ID сообщения в Telegram (если доступен)
        author: Имя автора сообщения
        is_bot: Флаг, является ли автор ботом
        text: Текст сообщения

    Returns:
        Форматированная строка записи лога

    Examples:
        >>> format_chat_log_entry(123, "Иван", False, "Привет")
        "[123] Иван: Привет"
        >>> format_chat_log_entry(None, "Bot", True, "Здравствуйте")
        "Ассистент: Здравствуйте"
    """
    role = "Ассистент" if is_bot else author
    if message_id:
        return f"[{message_id}] {role}: {text}"
    else:
        return f"{role}: {text}"
