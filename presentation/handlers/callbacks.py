"""Callback query handlers."""
import logging
from aiogram import types, Router
from aiogram.filters import StateFilter

from application.services.subscription import SubscriptionService
from application.services.user import UserService
from application.services.game import GameService
from application.services.ai import AIService
from application.services.media import MediaService
from application.services.rag import RAGService
from application.services.strings import StringsService
from domain.entities import User, Chat, MessageContext
from domain.interfaces import IFreezesRepository
from infrastructure.external.gemini import GeminiAPI
from presentation.keyboards import KeyboardBuilder
from presentation.formatters import Formatter
from presentation.decorators import handle_errors


logger = logging.getLogger(__name__)

router = Router()


@router.callback_query()
@handle_errors
async def callback_any(
    query: types.CallbackQuery,
    subscription_service: SubscriptionService,
    user_service: UserService,
    game_service: GameService,
    ai_service: AIService,
    media_service: MediaService,
    rag_service: RAGService,
    strings_service: StringsService,
    gemini_api: GeminiAPI,
    freezes_repo: IFreezesRepository,
    keyboard_builder: KeyboardBuilder,
    config
):
    """Handle all callback queries."""
    data = (query.data or "").strip()
    message = query.message
    username = user_service.get_display_name(query.from_user.id, query.from_user)
    
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
                    reply_markup=keyboard_builder.freeze_keyboard(user_id, config.FREEZE_OPTIONS, hot=False),
                )
        except Exception:
            logger.exception("unfreeze: failed to edit confirmation message")
        
        await query.answer("🔑 Авто-ответы включены")
        return
    
    # Game callbacks
    if data.startswith("game:"):
        if data == "game:guess_object":
            try:
                await query.answer("Игра запущена")
            except Exception:
                pass
            
            try:
                user_id = query.from_user.id
                chat_id = message.chat.id if message else user_id
                
                # Build game prompt
                game_prompt = (
                    "Начинай игру 'Кто я?'. Выбери в уме один предмет из майнкрафта (моб, предмет, существо, gui интерфейс, событие по типу дождя и другое). "
                    "В свой первый ответ обязательно незаметно добавь служебную метку [[guess:СЛОВО]], где СЛОВО — выбранный предмет на русском языке, "
                    "а в основном тексте не раскрывай его и предложи мне начинать угадывать. Предмет должен быть тяжёлым для отгадывания, не очевиден."
                )
                
                # Send typing action
                await media_service.send_typing_action(chat_id)
                
                # Load system prompt
                system_prompt = strings_service.load_system_prompt_for_chat(message.chat) if message else \
                    "Ты — бот MineBridge, помощник игроков Minecraft-сервера. Отвечай кратко, дружелюбно и по делу."
                
                # Create message context with RAG
                user = user_service.create_user_from_telegram(query.from_user)
                chat = Chat(
                    id=chat_id,
                    type=str(getattr(message.chat, "type", "private")) if message else "private"
                )
                
                context = await MessageContext.create_with_rag(
                    prompt=game_prompt,
                    user=user,
                    chat=chat,
                    rag_service=rag_service
                )
                
                # Send game start message
                tmp = await message.reply("🎲 Запускаю игру...") if message else None
                
                # Get AI response
                answer, _ = await ai_service.complete(context, system_prompt, message)
                
                if tmp:
                    await media_service.long_text(tmp, message, answer)
                else:
                    await query.message.answer(answer) if query.message else None
                    
            except Exception as e:
                logger.exception(f"game:guess_object failed: {e}")
                try:
                    if message:
                        await message.reply("Не удалось запустить игру. Попробуйте ещё раз.")
                except Exception:
                    pass
            return
        
        elif data == "game:guess_stop":
            try:
                await query.answer("Останавливаю игру")
            except Exception:
                pass
            
            try:
                if message:
                    game_service.stop_guess_game(message.chat.id)
                    await message.reply("Игра завершена. Чтобы начать заново — /game.")
            except Exception:
                logger.exception("game:guess_stop failed")
            return
        
        await query.answer()
        return
    
    # Subscription check
    if data == "check_subscription":
        if await subscription_service.is_subscribed(query.from_user.id):
            await message.reply(f"Привет, {username}!\nМожешь писать мне свои вопросы\nОбращайся ко мне - бриджик")
        else:
            await query.answer("Подписка не найдена! Убедитесь, что подписаны на канал", show_alert=True)
        return
    
    # Default
    await query.answer()

