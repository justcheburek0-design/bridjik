"""Game command handler."""
from aiogram import types, Router
from aiogram.filters import Command

from application.services.subscription import SubscriptionService
from application.services.game import GameService
from presentation.keyboards import KeyboardBuilder
from presentation.decorators import handle_errors


router = Router()


@router.message(Command("game"))
@handle_errors
async def cmd_game(
    message: types.Message,
    subscription_service: SubscriptionService,
    game_service: GameService,
    keyboard_builder: KeyboardBuilder
):
    """Handle /game command."""
    if not await subscription_service.is_subscribed(message.from_user.id):
        await message.reply("Подпишитесь на @MineBridgeOfficial, чтобы пользоваться ботом")
        return
    
    # Check if game is active
    active = game_service.is_game_active(message.chat.id)
    kb = keyboard_builder.game_keyboard(active=active)
    await message.reply("Выберите игру:", reply_markup=kb)

