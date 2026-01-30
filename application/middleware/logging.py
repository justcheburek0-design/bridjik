"""Logging middleware."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging incoming messages."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user = event.from_user
        chat = event.chat
        text = event.text or event.caption or ""

        user_info = (
            f"@{user.username}"
            if user and user.username
            else f"ID:{user.id if user else 'unknown'}"
        )
        chat_info = f"{chat.type}:{chat.id}" if chat else "unknown"

        logging.info(f"Message from {user_info} in {chat_info}: {text[:50]}")

        return await handler(event, data)
