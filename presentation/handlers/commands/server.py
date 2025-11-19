"""Server-related command handlers."""
from aiogram import types, Router
from aiogram.filters import Command

from application.services.subscription import SubscriptionService
from infrastructure.external.mc_api import MinecraftAPI
from infrastructure.external.mb_api import MineBridgeAPI
from presentation.formatters import Formatter
from presentation.decorators import handle_errors


router = Router()


@router.message(Command("status"))
@handle_errors
async def cmd_status(message: types.Message, mc_api: MinecraftAPI):
    """Handle /status command."""
    msg = await message.reply("🔎 Проверяю статус сервера...")
    try:
        payload = await mc_api.fetch_status()
        text = mc_api.format_status_text(payload)
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"⚠️ Не удалось получить статус: `{str(e)}`")


@router.message(Command("player"))
@handle_errors
async def cmd_player(
    message: types.Message,
    subscription_service: SubscriptionService,
    mb_api: MineBridgeAPI,
    formatter: Formatter
):
    """Handle /player command."""
    user_id = message.from_user.id
    text = (message.text or "").strip()
    
    if not await subscription_service.is_subscribed(user_id):
        await message.reply("Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком")
        return
    
    msg = await message.reply("🔎 Проверяю тебя...")
    try:
        player_info = await mb_api.fetch_player_by_id(str(user_id))
        if not player_info:
            await msg.edit_text(
                f"😕 Игрок <code>{user_id}</code> не найден или произошла ошибка API\n"
                f"Проверьте привязан ли ваш <a href='https://майнбридж.рф/auth'>телеграм к сайту</a>"
            )
            return
        text = formatter.format_player_info(player_info)
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при запросе: {str(e)}")

