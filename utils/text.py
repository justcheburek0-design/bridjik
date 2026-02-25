"""Утилиты для работы с текстом."""

from __future__ import annotations

import hashlib
import re


def shorten(text: str, limit: int = 4000) -> str:
    """Сокращает текст до указанного лимита символов."""
    text = (text or "").strip()
    return (text[:limit] + "...") if len(text) > limit else text


def truncate_text(text: str, max_length: int = 2000) -> str:
    """Обрезает текст до max_length, сохраняя целостность тегов [type:payload]."""
    if not text or len(text) <= max_length:
        return text or ""

    tag_re = re.compile(
        r"\[(find_photo|gen_photo|sticker|kb|guess|voice):([^\]]+)\]", re.IGNORECASE
    )

    cut_point = max_length
    last_tag_start = -1
    last_tag_end = -1

    for match in tag_re.finditer(text):
        if match.start() < cut_point:
            last_tag_start = match.start()
            last_tag_end = match.end()
        else:
            break

    if last_tag_start != -1 and last_tag_end > cut_point:
        cut_point = last_tag_start

    result = text[:cut_point].rstrip()
    if len(result) < len(text):
        result += "..."
    return result


def hash_text(text: str) -> str:
    """Создаёт короткий SHA1-хеш текста (первые 10 символов)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def get_hour_string(hours: int) -> str:
    """Форматирует количество часов с правильным русским склонением."""
    if hours == 1:
        return "1 час"
    if hours in (2, 3, 4):
        return f"{hours} часа"
    return f"{hours} часов"
