"""Model selection command handler."""

from aiogram import Router, types
from aiogram.filters import Command

from application.services.ai import AIService
from presentation.decorators import handle_errors

router = Router()


@router.message(Command("model"))
@handle_errors
async def cmd_model(message: types.Message, ai_service: AIService, config):
    """Show or switch the active AI model."""
    if not message.from_user:
        return

    if message.from_user.id not in config.ADMIN_IDS:
        await message.reply("⛔ Только для администраторов")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1 or not parts[1].strip():
        await message.reply(
            "Текущая модель: "
            f"<code>{ai_service.model}</code>\n"
            "Смена: <code>/model provider/model</code>"
        )
        return

    model = parts[1].strip()
    ai_service.set_model(model)
    await message.reply(f"✅ Модель переключена на <code>{model}</code>")
