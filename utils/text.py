"""Утилиты для работы с текстом.

Модуль содержит функции для обработки и форматирования текста:
сокращение, обрезка с учётом тегов, хеширование и форматирование времени.
"""

import hashlib
import re


def shorten(text: str, limit: int = 700) -> str:
    """Сокращает текст до указанного лимита символов.

    Если текст длиннее лимита, обрезает его и добавляет "...".

    Args:
        text: Текст для сокращения
        limit: Максимальное количество символов (по умолчанию 700)

    Returns:
        Сокращённый текст с "..." или исходный текст, если он короче лимита

    Examples:
        >>> shorten("Короткий текст", 50)
        "Короткий текст"
        >>> shorten("Очень длинный текст" * 100, 20)
        "Очень длинный текст ..."
    """
    text = (text or "").strip()
    return (text[:limit] + "...") if len(text) > limit else text


def truncate_text(text: str, max_length: int = 2000) -> str:
    """Обрезает текст до максимальной длины с учётом тегов [[...]].

    Функция пытается сохранить целостность специальных тегов в формате [[type:payload]].
    Если точка обрезки попадает внутрь тега, текст обрезается перед началом тега.

    Поддерживаемые типы тегов:
    - [[photo:...]] - фотография
    - [[sticker:...]] - стикер
    - [[kb:...]] - база знаний
    - [[guess:...]] - угадайка
    - [[voice:...]] - голосовое сообщение

    Args:
        text: Текст для обрезки
        max_length: Максимальная длина текста (по умолчанию 2000)

    Returns:
        Обрезанный текст с "..." если был обрезан, или исходный текст

    Examples:
        >>> truncate_text("Короткий текст", 100)
        "Короткий текст"
        >>> long_text = "Текст " + "[[photo:image.jpg]] " * 100
        >>> result = truncate_text(long_text, 50)
        >>> "..." in result
        True
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    # Паттерн для поиска тегов в формате [[type:payload]]
    tag_re = re.compile(r"\[\[(photo|sticker|kb|guess|voice):([^\]]+)\]\]", re.IGNORECASE)

    # Точка обрезки
    cut_point = max_length

    # Поиск последнего тега перед точкой обрезки
    last_tag_start = -1
    last_tag_end = -1

    for match in tag_re.finditer(text):
        if match.start() < cut_point:
            last_tag_start = match.start()
            last_tag_end = match.end()
        else:
            break

    # Если точка обрезки попадает внутрь тега (start < cut_point < end)
    if last_tag_start != -1 and last_tag_end > cut_point:
        # Обрезаем перед тегом для сохранения целостности
        cut_point = last_tag_start

    # Обрезаем текст и удаляем пробелы справа
    result = text[:cut_point].rstrip()
    if len(result) < len(text):
        result += "..."

    return result


def hash_text(text: str) -> str:
    """Создаёт короткий детерминированный хеш для текста.

    Использует SHA1 и возвращает первые 10 символов для компактности.
    Полезно для создания уникальных идентификаторов на основе содержимого.

    Args:
        text: Текст для хеширования

    Returns:
        Первые 10 символов SHA1 хеша в hexadecimal формате

    Examples:
        >>> hash_text("Привет мир")
        'a1b2c3d4e5'
        >>> hash_text("Другой текст")
        'f6g7h8i9j0'
        >>> # Одинаковый текст всегда даёт одинаковый хеш
        >>> hash_text("test") == hash_text("test")
        True
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def get_hour_string(hours: int) -> str:
    """Форматирует количество часов в читаемую русскую строку.

    Правильно склоняет слово "час" в зависимости от числа.

    Args:
        hours: Количество часов

    Returns:
        Форматированная строка с правильным склонением

    Examples:
        >>> get_hour_string(1)
        "1 час"
        >>> get_hour_string(2)
        "2 часа"
        >>> get_hour_string(5)
        "5 часов"
        >>> get_hour_string(24)
        "24 часа"
    """
    if hours == 1:
        return "1 час"
    elif hours in (2, 3, 4):
        return f"{hours} часа"
    else:
        return f"{hours} часов"
