"""Message handlers."""
import logging
import re
from aiogram import types, Router
from aiogram.enums import ChatType

from application.services.subscription import SubscriptionService
from application.services.user import UserService
from application.services.ai import AIService
from application.services.media import MediaService
from application.services.rag import RAGService
from application.services.strings import StringsService
from domain.entities import User, Chat, MessageContext
from domain.interfaces import IFreezesRepository, IChatLogsRepository
from infrastructure.external.gemini import GeminiAPI
from presentation.decorators import handle_errors


logger = logging.getLogger(__name__)

router = Router()


def _should_answer(message: types.Message, bot_username: str) -> bool:
    """Check if bot should answer in group chat."""
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    
    # If reply to bot's message
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
        replied_username = getattr(message.reply_to_message.from_user, "username", "") or ""
        if bot_username and replied_username == bot_username:
            return True
        return False
    
    # Check mentions
    if message.entities and text:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = text[entity.offset: entity.offset + entity.length]
                if bot_username and mention_text.lstrip("@").lower() == bot_username:
                    return True
    
    # Check bot address keywords
    BOT_ADDRESS_RE = re.compile(r'(?i)(?<!\w)(?:нейро-?бот(?:ик|яра)?|бот(?:ик|яра)?|бридж(?:ик)?)(?!\w)')
    if BOT_ADDRESS_RE.search(text):
        return True
    
    # Check questions and commands
    QUESTION_MARK_RE = re.compile(r'\?')
    INTERROGATIVE_RE = re.compile(
        r'(?i)\b('
        r'можно ли|кто может помочь|кто поможет|подскаж(?:и|ите)|помогите|нужна помощь|help|помощь'
        r')\b'
    )
    COMMAND_RE = re.compile(
        r'(?i)\b('
        r'объясни|расскажи|скажи|подскажи|помоги|проверь|сделай|напиши|создай|найди|покажи|настрой'
        r')\b'
    )
    NOISE_RE = re.compile(r'^\s*(?:[^\w\s]|[\w]{1,2})\s*$')
    
    if NOISE_RE.match(text):
        return False
    
    score = 0
    if QUESTION_MARK_RE.search(text):
        score += 1
    if INTERROGATIVE_RE.search(text):
        score += 2
    if COMMAND_RE.search(text):
        score += 1
    if len(text) >= 25:
        score += 1
    
    return score >= 3


def _save_incoming_message(chat_logs_repo: IChatLogsRepository, message: types.Message, text: str) -> None:
    """Save incoming message to chat logs."""
    chat_id = message.chat.id
    author = message.from_user.username or message.from_user.first_name or "unknown" if message.from_user else "unknown"
    is_bot = bool(getattr(message.from_user, "is_bot", False))
    
    if not text:
        if message.photo:
            text = f"Фото: {message.photo[-1].file_id}"
        elif message.document:
            text = f"Документ: {message.document.file_id}"
        elif message.voice:
            text = f"Голосовое сообщение: {message.voice.file_id}"
        elif message.sticker:
            text = f"Стикер {message.sticker.emoji}: {message.sticker.file_id}"
        else:
            return
    
    chat_logs_repo.add_message(chat_id, author, is_bot, text)


@router.message()
@handle_errors
async def auto_reply(
    message: types.Message,
    subscription_service: SubscriptionService,
    user_service: UserService,
    ai_service: AIService,
    media_service: MediaService,
    rag_service: RAGService,
    strings_service: StringsService,
    gemini_api: GeminiAPI,
    freezes_repo: IFreezesRepository,
    chat_logs_repo: IChatLogsRepository,
    config
):
    """Auto-reply with AI."""
    prompt = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    has_photo = bool(getattr(message, "photo", None))
    has_image_doc = bool(getattr(message, "document", None) and str(getattr(message.document, "mime_type", "")).startswith("image/"))
    has_image = has_photo or has_image_doc
    has_voice = bool(getattr(message, "voice", None))
    
    user_id = getattr(message.from_user, "id", None)
    
    # Voice transcription
    if has_voice:
        try:
            await media_service.send_typing_action(message.chat.id)
            voice_data = await media_service.download_voice(message)
            if voice_data:
                audio_bytes, mime = voice_data
                transcribed = await gemini_api.transcribe_voice(audio_bytes, mime)
                if transcribed:
                    prompt = transcribed
        except Exception:
            logger.exception("voice transcription flow failed")
    
    if not prompt and not has_image:
        _save_incoming_message(chat_logs_repo, message, prompt)
        return
    
    # Check freeze
    if user_id is not None and freezes_repo.is_frozen(user_id):
        logger.info("Auto replies are temporarily frozen for user %s", user_id)
        _save_incoming_message(chat_logs_repo, message, prompt)
        return
    
    # Check if in group and should answer
    chat_type = getattr(message.chat, "type", None)
    if isinstance(chat_type, str):
        ct_name = chat_type.upper()
    else:
        ct_name = getattr(chat_type, "name", str(chat_type)).upper()
    is_group = ct_name in ("GROUP", "SUPERGROUP")
    
    if is_group and not _should_answer(message, config.BOT_USERNAME):
        logger.info("Skipped message without bot mention in group")
        _save_incoming_message(chat_logs_repo, message, prompt)
        return
    
    # Check subscription
    if not await subscription_service.is_subscribed(user_id):
        await message.reply("Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком")
        _save_incoming_message(chat_logs_repo, message, prompt)
        return
    
    try:
        await media_service.send_typing_action(message.chat.id)
        
        # Prepare message context
        user = user_service.create_user_from_telegram(message.from_user)
        chat = Chat(
            id=message.chat.id,
            type=str(chat_type),
            title=getattr(message.chat, "title", None)
        )
        
        # Download image if present
        image_bytes = None
        mime_type = None
        if has_image:
            msg = await message.reply("🖼️ <b>Распознаю изображение...</b>")
            image_data = await media_service.download_image(message)
            if image_data:
                image_bytes, mime_type = image_data
        elif has_voice:
            msg = await message.reply("🎙️ <b>Распознаю голосовое...</b>")
        else:
            msg = await message.reply("⏳ <b>Думаю...</b>")
        
        # Load system prompt
        system_prompt = strings_service.load_system_prompt_for_chat(message.chat)
        
        # Build message context with RAG
        context = await MessageContext.create_with_rag(
            prompt=prompt,
            user=user,
            chat=chat,
            rag_service=rag_service,
            has_image=has_image,
            image_bytes=image_bytes,
            mime_type=mime_type
        )
        
        # Get AI response
        answer = await ai_service.complete(
            context=context,
            system_prompt=system_prompt,
            message=message
        )
        
        if not answer:
            answer = "Извини, не смог сформулировать ответ. Попробуй переформулировать вопрос."
        
        # Send response with media tag support
        await media_service.long_text(msg, message, answer)
        
    except Exception as e:
        logger.exception("Error in auto_reply")
        try:
            await msg.edit_text(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
        except Exception:
            pass

