"""Базовые фикстуры для pytest."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from core.config import Config
from domain.entities import User, Chat, MessageContext


@pytest.fixture
def mock_config():
    """Мок конфигурации для тестов."""
    config = MagicMock(spec=Config)
    config.BOT_TOKEN = "test_token"
    config.BOT_USERNAME = "test_bot"
    config.ADMIN_IDS = [123456789]
    config.GROUP_MAX_MESSAGES = 14
    config.DM_MAX_MESSAGES = 7
    config.MAX_OUTPUT_LENGTH = 4000
    config.BASE_DIR = Path(__file__).parent.parent
    return config


@pytest.fixture
def sample_user():
    """Пример пользователя для тестов."""
    return User(id=12345, username="test_user", first_name="Тест", psevdo=None, is_bot=False)


@pytest.fixture
def sample_user_with_psevdo():
    """Пользователь с псевдонимом."""
    return User(
        id=67890, username="another_user", first_name="Иван", psevdo="Крутой игрок", is_bot=False
    )


@pytest.fixture
def sample_chat_private():
    """Приватный чат для тестов."""
    return Chat(id=12345, type="private", title=None)


@pytest.fixture
def sample_chat_group():
    """Групповой чат для тестов."""
    return Chat(id=67890, type="supergroup", title="Тестовая группа")


@pytest.fixture
def sample_message_context(sample_user, sample_chat_private):
    """Базовый контекст сообщения."""
    return MessageContext(
        prompt="Привет, как дела?",
        user=sample_user,
        chat=sample_chat_private,
        has_image=False,
        image_bytes=None,
        mime_type=None,
        rag_context="",
    )


@pytest.fixture
def sample_message_context_with_image(sample_user, sample_chat_private):
    """Контекст сообщения с изображением."""
    return MessageContext(
        prompt="Что на этой картинке?",
        user=sample_user,
        chat=sample_chat_private,
        has_image=True,
        image_bytes=b"fake_image_data",
        mime_type="image/jpeg",
        rag_context="",
    )
