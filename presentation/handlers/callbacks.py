"""Callback query handlers."""

import logging

from aiogram import Router, types

from application.services.ai import AIService
from application.services.game import GameService
from application.services.media import MediaService
from application.services.rag import RAGService
from application.services.strings import StringsService
from application.services.subscription import SubscriptionService
from domain.interfaces import IChatLogsRepository, IFreezesRepository
from infrastructure.external.gemini import GeminiAPI
from presentation.decorators import handle_errors
from presentation.formatters import Formatter
from presentation.keyboards import KeyboardBuilder

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query()
@handle_errors
async def callback_any(
    query: types.CallbackQuery,
    subscription_service: SubscriptionService,
    game_service: GameService,
    ai_service: AIService,
    media_service: MediaService,
    rag_service: RAGService,
    strings_service: StringsService,
    gemini_api: GeminiAPI,
    freezes_repo: IFreezesRepository,
    chat_logs_repo: IChatLogsRepository,
    keyboard_builder: KeyboardBuilder,
    config,
):
    """Handle all callback queries."""
    data = (query.data or "").strip()
    message = query.message
    # Get display name directly from telegram user
    username = query.from_user.first_name or query.from_user.username or "Пользователь"

    # Freeze callbacks
    if data.startswith("freeze:"):
        parts = data.split(":")
        if len(parts) != 3:
            await query.answer("Не удалось заморозить", show_alert=True)
            return

        _, user_id_str, hours_str = parts
        if user_id_str != str(query.from_user.id):
            await query.answer("Не твоё сообщение!", show_alert=True)
            return

        try:
            user_id = int(user_id_str)
            hours = int(hours_str)
        except ValueError:
            await query.answer("Недопустимые параметры", show_alert=True)
            return

        if hours not in config.FREEZE_OPTIONS:
            await query.answer("Недопустимая длительность", show_alert=True)
            return

        freezes_repo.set_freeze(user_id, hours)

        try:
            if message:
                await message.edit_text(
                    Formatter.format_freeze_message(username, hours, is_active=True),
                    reply_markup=keyboard_builder.freeze_keyboard(user_id, config.FREEZE_OPTIONS),
                )
        except Exception:
            logger.exception("freeze: failed to edit confirmation message")

        await query.answer(f"🔐 Авто-ответы выключены на {hours} ч.")
        return

    # Unfreeze callbacks
    if data.startswith("unfreeze:"):
        parts = data.split(":")
        if len(parts) != 2:
            await query.answer("Не удалось разморозить", show_alert=True)
            return

        _, user_id_str = parts
        if user_id_str != str(query.from_user.id):
            await query.answer("Это не твоё сообщение!", show_alert=True)
            return

        user_id = query.from_user.id
        freezes_repo.clear_freeze(user_id)

        try:
            if message:
                await message.edit_text(
                    Formatter.format_freeze_message(username, 0, is_active=False),
                    reply_markup=keyboard_builder.freeze_keyboard(
                        user_id, config.FREEZE_OPTIONS, hot=False
                    ),
                )
        except Exception:
            logger.exception("unfreeze: failed to edit confirmation message")

        await query.answer("🔑 Авто-ответы включены")
        return

    # Subscription check
    if data == "check_subscription":
        if await subscription_service.is_subscribed(query.from_user.id):
            await message.reply(
                f"Привет, {username}!\nМожешь писать мне свои вопросы\nОбращайся ко мне - бриджик"
            )
        else:
            await query.answer(
                "Подписка не найдена! Убедитесь, что подписаны на канал",
                show_alert=True,
            )
        return

    # Default
    await query.answer()
