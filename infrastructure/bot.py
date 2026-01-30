"""Bot and Dispatcher initialization."""

from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


def create_bot(token: str) -> Bot:
    """Create and configure Bot instance."""
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher() -> Dispatcher:
    """Create and configure Dispatcher instance."""
    return Dispatcher()


# Bot metadata
last_update = datetime.now()
