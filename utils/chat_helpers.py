"""Chat helper utilities."""

from __future__ import annotations

from aiogram import types


def get_author_name(message: types.Message, fallback: str = "unknown") -> str:
    """Get author name from message.

    Args:
        message: Telegram message
        fallback: Default name if user is None

    Returns:
        Username or first_name or fallback
    """
    if not message.from_user:
        return fallback

    return message.from_user.username or message.from_user.first_name or fallback


def get_message_id(message: types.Message) -> int | None:
    """Safely get message ID.

    Args:
        message: Telegram message

    Returns:
        Message ID or None if not available
    """
    # In aiogram, message.message_id is always available
    try:
        return message.message_id
    except AttributeError:
        return getattr(message, "message_id", None)


def is_bot_message(message: types.Message) -> bool:
    """Check if message is from a bot.

    Args:
        message: Telegram message

    Returns:
        True if message is from a bot
    """
    if not message.from_user:
        return False

    return bool(getattr(message.from_user, "is_bot", False))
