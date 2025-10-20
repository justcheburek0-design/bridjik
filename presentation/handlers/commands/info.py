"""Info command handlers."""
from datetime import datetime
from aiogram import types, Router
from aiogram.filters import Command

from application.services.subscription import SubscriptionService
from presentation.keyboards import KeyboardBuilder
from infrastructure.bot import last_update
from presentation.decorators import handle_errors


router = Router()


@router.message(Command("version"))
@handle_errors
async def cmd_version(
    message: types.Message,
    subscription_service: SubscriptionService,
    config
):
    """Handle /version command."""
    user_id = message.from_user.id
    
    if await subscription_service.is_subscribed(user_id):
        await message.reply(
            f"Моя версия: <b>{config.VERSION}</b>\n"
            f"Последнее обновление: <b>{last_update.strftime('%Y-%m-%d %H:%M:%S')}</b>"
        )
        return
    
    await subscription_service.send_subscription_prompt(message)


@router.message(Command("support"))
@handle_errors
async def cmd_support(message: types.Message, keyboard_builder: KeyboardBuilder):
    """Handle /support command."""
    kb = keyboard_builder.support_keyboard()
    await message.reply(
        "Отвечаем от пары минут до пары часов, пишите всё в одно сообщение!",
        reply_markup=kb
    )


@router.message(Command("donate"))
@handle_errors
async def cmd_donate(message: types.Message, keyboard_builder: KeyboardBuilder):
    """Handle /donate command."""
    kb = keyboard_builder.donate_keyboard()
    await message.reply(
        "На сервере действует валюта мостики, 1 мостик = 1 рубль",
        reply_markup=kb
    )

