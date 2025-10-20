"""Start command handler."""
from aiogram import types, Router
from aiogram.filters import Command

from application.services.subscription import SubscriptionService
from application.services.user import UserService
from presentation.keyboards import KeyboardBuilder
from presentation.decorators import handle_errors


router = Router()


@router.message(Command("start"))
@handle_errors
async def cmd_start(
    message: types.Message,
    subscription_service: SubscriptionService,
    user_service: UserService,
    keyboard_builder: KeyboardBuilder
):
    """Handle /start command."""
    user_id = message.from_user.id
    username = user_service.get_display_name(user_id, message.from_user)
    
    if await subscription_service.is_subscribed(user_id):
        await message.reply(
            f"Привет, {username}!\nМожешь писать мне свои вопросы\nОбращайся ко мне - бриджик"
        )
        return
    
    kb = keyboard_builder.subscription_keyboard()
    await message.answer(
        "Для доступа нужен канал @MineBridgeOfficial — подпишитесь и нажмите «<b>Проверить подписку</b>»",
        reply_markup=kb
    )

