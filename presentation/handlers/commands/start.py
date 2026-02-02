"""Start command handler."""

from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from application.services.subscription import SubscriptionService
from presentation.decorators import handle_errors
from presentation.keyboards import KeyboardBuilder

router = Router()


@router.message(CommandStart())
@router.message(Command("start"))
@handle_errors
async def cmd_start(
    message: types.Message,
    subscription_service: SubscriptionService,
    keyboard_builder: KeyboardBuilder,
    config,
):
    """Handle /start command."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    # Get display name directly
    username = message.from_user.first_name or message.from_user.username or "Пользователь"

    if await subscription_service.is_subscribed(user_id):
        await message.reply(
            f"Привет, {username}!\nМожешь писать мне свои вопросы\nОбращайся ко мне - бриджик",
        )
    else:
        await message.reply(
            "Подпишись на канал, чтобы пользоваться бриджиком!",
            reply_markup=keyboard_builder.subscribe_keyboard(),
        )
