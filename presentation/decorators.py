"""Handler decorators."""
import logging
from functools import wraps
from typing import Callable
from aiogram import types


def handle_errors(handler: Callable):
    """Decorator to handle errors in handlers."""
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        try:
            return await handler(message, *args, **kwargs)
        except Exception as e:
            logging.exception(f"Error in handler {handler.__name__}")
            try:
                await message.reply(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
            except Exception:
                pass
    return wrapper


def log_handler(handler: Callable):
    """Decorator to log handler calls."""
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else "unknown"
        chat_id = message.chat.id if message.chat else "unknown"
        logging.info(f"Handler {handler.__name__} called by user {user_id} in chat {chat_id}")
        return await handler(message, *args, **kwargs)
    return wrapper

