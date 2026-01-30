"""Тесты для utils/validation.py."""

import pytest

from utils.validation import (
    is_valid_id,
    is_valid_string,
    normalize_string,
    safe_get_attr,
    validate_message_context,
)


class TestIsValidId:
    """Тесты для функции is_valid_id."""

    def test_positive_integer(self):
        """Положительное целое число - валидный ID."""
        assert is_valid_id(123) is True
        assert is_valid_id(1) is True

    def test_zero(self):
        """Ноль - не валидный ID."""
        assert is_valid_id(0) is False

    def test_negative(self):
        """Отрицательное число - не валидный ID."""
        assert is_valid_id(-5) is False

    def test_string(self):
        """Строка - не валидный ID."""
        assert is_valid_id("123") is False

    def test_float(self):
        """Float - не валидный ID."""
        assert is_valid_id(123.45) is False


class TestIsValidString:
    """Тесты для функции is_valid_string."""

    def test_valid_string(self):
        """Валидная непустая строка."""
        assert is_valid_string("Привет") is True

    def test_empty_string(self):
        """Пустая строка с min_length=0 валидна."""
        assert is_valid_string("", min_length=0) is True
        assert is_valid_string("", min_length=1) is False

    def test_whitespace_only(self):
        """Только пробелы с min_length=0 валидны после strip."""
        assert is_valid_string("   ", min_length=0) is True
        assert is_valid_string("   ", min_length=1) is False

    def test_min_length(self):
        """Минимальная длина."""
        assert is_valid_string("Hi", min_length=5) is False
        assert is_valid_string("Hello", min_length=5) is True

    def test_max_length(self):
        """Максимальная длина."""
        assert is_valid_string("Короткий", max_length=10) is True
        assert is_valid_string("Очень длинная строка", max_length=10) is False

    def test_non_string(self):
        """Не строка."""
        assert is_valid_string(123) is False
        assert is_valid_string(None) is False


class TestNormalizeString:
    """Тесты для функции normalize_string."""

    def test_trim_whitespace(self):
        """Удаление пробелов."""
        assert normalize_string("  Привет  ") == "Привет"

    def test_max_length(self):
        """Обрезка по длине."""
        result = normalize_string("Длинная строка", max_length=5)
        assert result == "Длинн"

    def test_non_string(self):
        """Не строка возвращает пустую строку."""
        assert normalize_string(123) == ""
        assert normalize_string(None) == ""

    def test_empty_string(self):
        """Пустая строка."""
        assert normalize_string("") == ""


class TestSafeGetAttr:
    """Тесты для функции safe_get_attr."""

    def test_existing_attribute(self):
        """Существующий атрибут."""

        class TestClass:
            value = 42

        obj = TestClass()
        assert safe_get_attr(obj, "value") == 42

    def test_missing_attribute(self):
        """Отсутствующий атрибут возвращает default."""

        class TestClass:
            pass

        obj = TestClass()
        assert safe_get_attr(obj, "missing", "default") == "default"

    def test_none_default(self):
        """Default по умолчанию None."""

        class TestClass:
            pass

        obj = TestClass()
        assert safe_get_attr(obj, "missing") is None


class TestValidateMessageContext:
    """Тесты для функции validate_message_context."""

    def test_text_only(self):
        """Только текст - валидно."""
        assert validate_message_context("Привет") is True

    def test_image_only(self):
        """Только изображение - валидно."""
        assert validate_message_context("", has_image=True, image_bytes=b"data") is True

    def test_empty_no_image(self):
        """Пустой текст без изображения - не валидно."""
        assert validate_message_context("", has_image=False) is False

    def test_image_without_bytes(self):
        """Флаг изображения без данных - не валидно."""
        assert validate_message_context("", has_image=True, image_bytes=None) is False

    def test_text_and_image(self):
        """Текст и изображение вместе - валидно."""
        assert validate_message_context("Описание", has_image=True, image_bytes=b"data") is True
