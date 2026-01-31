"""User-related command handlers."""

import re
import time

from aiogram import Router, types
from aiogram.filters import Command

from application.services.user import UserService
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


@router.message(Command("psevdo"))
@handle_errors
async def cmd_psevdo(message: types.Message, user_service: UserService):
    """Handle /psevdo command."""
    if not message.from_user:
        return

    uid = message.from_user.id
    raw = (message.text or "").strip()

    # Extract everything after command token
    m = re.match(r"^/psevdo(?:@\w+)?\s+(.+)$", raw, flags=re.IGNORECASE)
    if not m:
        current = user_service.get_psevdo(uid)
        if current:
            await message.reply(
                f"Ваше текущее прозвище: <b>{current}</b>\n"
                f"Чтобы изменить: <code>/psevdo [Прозвище]</code>\n"
                f"Ограничение: 100 символов"
            )
        else:
            await message.reply(
                "Задайте прозвище: <code>/psevdo [Прозвище]</code>\n" "Ограничение: 100 символов"
            )
        return

    name = m.group(1).strip()
    if not name:
        await message.reply("Пустое прозвище не сохраняю. Пример: <code>/psevdo Вася</code>")
        return

    name = user_service.set_psevdo(uid, name)
    await message.reply(f"Готово. Ваше прозвище: <b>{name}</b>")


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
