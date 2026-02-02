"""User-related command handlers."""

import time

from aiogram import Router, types
from aiogram.filters import Command

from domain.interfaces import IFreezesRepository
from presentation.decorators import handle_errors
from presentation.keyboards import KeyboardBuilder

router = Router()


@router.message(Command("id"))
@handle_errors
async def cmd_id(message: types.Message):
    """Handle /id command."""
    chat_id = getattr(message.chat, "id", None)
    if chat_id is None:
        await message.reply("Не удалось определить ID чата")
        return
    await message.reply(f"ID чата: <code>{chat_id}</code>")


@router.message(Command("freeze"))
@handle_errors
async def cmd_freeze(
    message: types.Message,
    freezes_repo: IFreezesRepository,
    keyboard_builder: KeyboardBuilder,
    config,
):
    """Handle /freeze command."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    current_freeze = freezes_repo.get_freeze(user_id)

    if current_freeze:
        minutes_unfreeze = round((current_freeze - time.time()) / 60)
        current_freeze_text = f"\n⏳ Текущая заморозка действует ещё <b>{minutes_unfreeze} мин</b>"
    else:
        current_freeze_text = ""

    text_body = "❄️ Выбери <b>длительность заморозки автоответов</b>" + current_freeze_text

    await message.reply(
        text_body,
        reply_markup=keyboard_builder.freeze_keyboard(
            user_id, config.FREEZE_OPTIONS, hot=bool(current_freeze)
        ),
    )
