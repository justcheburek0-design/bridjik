"""Тесты для utils/text.py."""

from utils.text import get_hour_string, hash_text, shorten, truncate_text


class TestShorten:
    """Тесты для функции shorten."""

    def test_short_text(self):
        """Короткий текст не обрезается."""
        text = "Короткий текст"
        result = shorten(text, limit=50)
        assert result == text

    def test_long_text(self):
        """Длинный текст обрезается и добавляется ..."""
        text = "Очень длинный текст" * 100
        result = shorten(text, limit=20)
        assert len(result) == 23  # 20 + "..."
        assert result.endswith("...")

    def test_empty_text(self):
        """Пустой текст возвращает пустую строку."""
        assert shorten("") == ""
        assert shorten(None) == ""

    def test_whitespace_text(self):
        """Текст из пробелов обрезается."""
        assert shorten("   ") == ""


class TestTruncateText:
    """Тесты для функции truncate_text."""

    def test_short_text(self):
        """Короткий текст не изменяется."""
        text = "Короткий текст"
        result = truncate_text(text, max_length=100)
        assert result == text

    def test_empty_text(self):
        """Пустой текст возвращает пустую строку."""
        assert truncate_text("") == ""
        assert truncate_text(None) == ""

    def test_text_with_tag_before_cutpoint(self):
        """Текст с тегом до точки обрезки."""
        text = "Текст [find_photo:image.jpg] ещё текст" * 10
        result = truncate_text(text, max_length=50)
        assert "..." in result

    def test_text_with_tag_at_cutpoint(self):
        """Тег на точке обрезки - обрезается перед тегом."""
        text = "Начало " + "[find_photo:image.jpg]" + " продолжение" * 100
        result = truncate_text(text, max_length=20)
        # Должна обрезаться перед тегом
        assert "[" not in result or result.count("[") == result.count("]")

    def test_preserves_complete_tags(self):
        """Сохраняет целостность тегов."""
        text = "Text [sticker:pack:123] more text"
        result = truncate_text(text, max_length=100)
        assert result == text


class TestHashText:
    """Тесты для функции hash_text."""

    def test_deterministic(self):
        """Одинаковый текст даёт одинаковый хеш."""
        text = "Тестовый текст"
        hash1 = hash_text(text)
        hash2 = hash_text(text)
        assert hash1 == hash2

    def test_different_texts(self):
        """Разные тексты дают разные хеши."""
        hash1 = hash_text("Текст 1")
        hash2 = hash_text("Текст 2")
        assert hash1 != hash2

    def test_hash_length(self):
        """Хеш имеет фиксированную длину."""
        text = "Любой текст"
        result = hash_text(text)
        assert len(result) == 10


class TestGetHourString:
    """Тесты для функции get_hour_string."""

    def test_one_hour(self):
        """1 час."""
        assert get_hour_string(1) == "1 час"

    def test_two_hours(self):
        """2 часа."""
        assert get_hour_string(2) == "2 часа"

    def test_three_hours(self):
        """3 часа."""
        assert get_hour_string(3) == "3 часа"

    def test_four_hours(self):
        """4 часа."""
        assert get_hour_string(4) == "4 часа"

    def test_five_hours(self):
        """5 часов."""
        assert get_hour_string(5) == "5 часов"

    def test_many_hours(self):
        """Много часов."""
        assert get_hour_string(24) == "24 часов"
        assert get_hour_string(100) == "100 часов"
