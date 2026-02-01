"""Тесты для domain/entities.py."""

from domain.entities import Chat, MessageContext, User


class TestUser:
    """Тесты для сущности User."""

    def test_get_display_name_with_psevdo(self):
        """Приоритет у псевдонима."""
        user = User(id=123, username="username", first_name="Иван", psevdo="Крутой игрок")
        assert user.get_display_name() == "Крутой игрок"

    def test_get_display_name_with_first_name(self):
        """Если нет псевдонима, используется first_name."""
        user = User(id=123, username="username", first_name="Иван", psevdo=None)
        assert user.get_display_name() == "Иван"

    def test_get_display_name_with_username(self):
        """Если нет first_name, используется username."""
        user = User(id=123, username="username", first_name=None, psevdo=None)
        assert user.get_display_name() == "username"

    def test_get_display_name_fallback(self):
        """Если ничего нет, возвращается 'Пользователь'."""
        user = User(id=123, username=None, first_name=None, psevdo=None)
        assert user.get_display_name() == "Пользователь"


class TestChat:
    """Тесты для сущности Chat."""

    def test_private_chat(self):
        """Приватный чат."""
        chat = Chat(id=123, type="private", title=None)
        assert chat.type == "private"
        assert chat.title is None

    def test_group_chat(self):
        """Групповой чат."""
        chat = Chat(id=456, type="supergroup", title="Тестовая группа")
        assert chat.type == "supergroup"
        assert chat.title == "Тестовая группа"


class TestMessageContext:
    """Тесты для сущности MessageContext."""

    def test_basic_context(self, sample_user, sample_chat_private):
        """Базовый контекст без изображения."""
        context = MessageContext(
            prompt="Привет", user=sample_user, chat=sample_chat_private, has_image=False
        )
        assert context.prompt == "Привет"
        assert context.user == sample_user
        assert context.chat == sample_chat_private
        assert context.has_image is False
        assert context.image_bytes is None

    def test_context_with_image(self, sample_user, sample_chat_private):
        """Контекст с изображением."""
        image_data = b"fake_image_data"
        context = MessageContext(
            prompt="Что на фото?",
            user=sample_user,
            chat=sample_chat_private,
            has_image=True,
            image_bytes=image_data,
            mime_type="image/jpeg",
        )
        assert context.has_image is True
        assert context.image_bytes == image_data
        assert context.mime_type == "image/jpeg"
