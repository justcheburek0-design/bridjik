"""Bot and Dispatcher initialization."""
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from datetime import datetime


def create_bot(token: str) -> Bot:
    """Create and configure Bot instance."""
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )


def create_dispatcher() -> Dispatcher:
    """Create and configure Dispatcher instance."""
    return Dispatcher()


# Bot metadata
last_update = datetime.now()

