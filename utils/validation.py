"""Утилиты для валидации данных.

Модуль содержит функции для проверки и нормализации входных данных:
ID, строк, атрибутов объектов и контекста сообщений.
"""

from __future__ import annotations

from typing import Any


def is_valid_id(value: Any) -> bool:
    """Проверяет, является ли значение валидным ID (положительное целое число).

    Args:
        value: Значение для проверки

    Returns:
        True, если значение является положительным целым числом

    Examples:
        >>> is_valid_id(123)
        True
        >>> is_valid_id(-5)
        False
        >>> is_valid_id("123")
        False
    """
    return isinstance(value, int) and value > 0


def is_valid_string(value: Any, min_length: int = 0, max_length: int | None = None) -> bool:
    """Проверяет, является ли значение валидной непустой строкой.

    Args:
        value: Значение для проверки
        min_length: Минимальная длина после trim (по умолчанию 0)
        max_length: Максимальная длина или None для отсутствия ограничения

    Returns:
        True, если значение является валидной строкой в заданных пределах

    Examples:
        >>> is_valid_string("Привет")
        True
        >>> is_valid_string("   ")
        False
        >>> is_valid_string("Hi", min_length=5)
        False
        >>> is_valid_string("Очень длинная строка", max_length=10)
        False
    """
    if not isinstance(value, str):
        return False

    if len(value.strip()) < min_length:
        return False

    if max_length is not None and len(value) > max_length:
        return False

    return True


def normalize_string(value: str, max_length: int | None = None) -> str:
    """Нормализует строковое значение (trim и обрезка по длине).

    Удаляет пробелы с обеих сторон и обрезает строку до максимальной длины.

    Args:
        value: Строка для нормализации
        max_length: Максимальная длина или None для отсутствия ограничения

    Returns:
        Нормализованная строка или пустая строка для невалидных входных данных

    Examples:
        >>> normalize_string("  Привет  ")
        "Привет"
        >>> normalize_string("Длинная строка", max_length=5)
        "Длинн"
        >>> normalize_string(123)
        ""
    """
    if not isinstance(value, str):
        return ""

    normalized = value.strip()

    if max_length is not None and len(normalized) > max_length:
        normalized = normalized[:max_length]

    return normalized


def safe_get_attr(obj: Any, attr_name: str, default: Any = None) -> Any:
    """Безопасно получает атрибут объекта.

    Обёртка над getattr с обработкой исключений для безопасного доступа к атрибутам.

    Args:
        obj: Объект для получения атрибута
        attr_name: Имя атрибута
        default: Значение по умолчанию, если атрибут отсутствует

    Returns:
        Значение атрибута или default при ошибке

    Examples:
        >>> class MyClass:
        ...     value = 42
        >>> obj = MyClass()
        >>> safe_get_attr(obj, "value")
        42
        >>> safe_get_attr(obj, "missing", "default")
        'default'
    """
    try:
        return getattr(obj, attr_name, default)
    except Exception:
        return default


def validate_message_context(
    prompt: str, has_image: bool = False, image_bytes: bytes | None = None
) -> bool:
    """Валидирует контекст сообщения для AI completion.

    Проверяет, что сообщение содержит либо текст, либо изображение,
    и что данные изображения присутствуют, если оно заявлено.

    Args:
        prompt: Текст промпта пользователя
        has_image: Флаг наличия изображения
        image_bytes: Байты изображения (если доступно)

    Returns:
        True, если контекст валиден для обработки AI

    Examples:
        >>> validate_message_context("Привет")
        True
        >>> validate_message_context("", has_image=True, image_bytes=b"...")
        True
        >>> validate_message_context("", has_image=False)
        False
        >>> validate_message_context("", has_image=True, image_bytes=None)
        False
    """
    # Должен быть хотя бы текст или изображение
    if not prompt and not has_image:
        return False

    # Если заявлено изображение, должны быть его данные
    if has_image and not image_bytes:
        return False

    return True
