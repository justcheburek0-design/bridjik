"""Deterministic reminder management without an LLM round trip."""
from aiogram import Router, types
from aiogram.filters import Command, CommandObject

router = Router()


@router.message(Command("reminders"))
async def list_active(message: types.Message, container):
    if message.from_user:
        await message.answer(container.reminders.listing(message), parse_mode=None)


@router.message(Command("cancel_reminder"))
async def cancel_active(message: types.Message, command: CommandObject, container):
    if not message.from_user:
        return
    try:
        reminder_id = int((command.args or "").strip().lstrip("#"))
    except ValueError:
        await message.answer("Использование: /cancel_reminder ID", parse_mode=None)
        return
    await message.answer(container.reminders.cancel(message, reminder_id), parse_mode=None)
