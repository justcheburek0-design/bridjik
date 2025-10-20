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
from domain.interfaces import IFreezesRepository, IChatLogsRepository, IHistoryRepository
from infrastructure.external.gemini import GeminiAPI
from presentation.decorators import handle_errors


logger = logging.getLogger(__name__)

router = Router()


def _get_media_description(message: types.Message) -> str:
    """Generate media description from message.
    
    Returns empty string if no media found.
    """
    if message.photo:
        caption = getattr(message, "caption", None) or ""
        return f"🖼️ Фото{f': {caption}' if caption else ''}"
    elif message.document:
        doc = message.document
        filename = getattr(doc, "file_name", "документ")
        mime = getattr(doc, "mime_type", "unknown")
        return f"📎 Документ: {filename} ({mime})"
    elif message.voice:
        voice = message.voice
        duration = getattr(voice, "duration", 0)
        return f"🎤 Голосовое сообщение ({duration}с)"
    elif message.sticker:
        sticker = message.sticker
        emoji = getattr(sticker, "emoji", "")
        is_animated = getattr(sticker, "is_animated", False)
        is_video = getattr(sticker, "is_video", False)
        sticker_set = getattr(sticker, "set_name", "неизвестный набор")
        
        sticker_type = "стикер"
        if is_video:
            sticker_type = "видео-стикер"
        elif is_animated:
            sticker_type = "анимированный стикер"
        
        return f"🎨 {sticker_type} {emoji} из '{sticker_set}'"
    elif message.animation:
        animation = message.animation
        duration = getattr(animation, "duration", 0)
        filename = getattr(animation, "file_name", "гифка")
        return f"🎬 Гифка '{filename}' ({duration}с)"
    elif message.video:
        video = message.video
        duration = getattr(video, "duration", 0)
        return f"📹 Видео ({duration}с)"
    elif message.audio:
        audio = message.audio
        duration = getattr(audio, "duration", 0)
        performer = getattr(audio, "performer", None)
        title = getattr(audio, "title", None)
        desc = f"🎵 Аудио"
        if performer:
            desc += f" - {performer}"
        if title:
            desc += f": {title}"
        desc += f" ({duration}с)"
        return desc
    
    return ""


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
    
    # Get media description
    media_desc = _get_media_description(message)
    
    # Build final message
    if text and media_desc:
        # If both text and media, combine them
        final_text = f"{media_desc}\n\n{text}"
    elif media_desc:
        # Only media
        final_text = media_desc
    elif text:
        # Only text
        final_text = text
    else:
        # Nothing to save
        return
    
    chat_logs_repo.add_message(chat_id, author, is_bot, final_text)


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
    history_repo: IHistoryRepository,
    config
):
    """Auto-reply with AI."""
    prompt = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    has_photo = bool(getattr(message, "photo", None))
    has_image_doc = bool(getattr(message, "document", None) and str(getattr(message.document, "mime_type", "")).startswith("image/"))
    has_sticker = bool(getattr(message, "sticker", None))
    has_animation = bool(getattr(message, "animation", None))
    has_image = has_photo or has_image_doc or has_sticker or has_animation
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
        
        # Download image/sticker/animation if present
        image_bytes = None
        mime_type = None
        msg = None
        if has_image:
            if has_sticker:
                msg = await message.reply("🎨 <b>Распознаю стикер...</b>")
                image_data = await media_service.download_sticker(message)
            elif has_animation:
                msg = await message.reply("🎬 <b>Распознаю гифку...</b>")
                image_data = await media_service.download_animation(message)
            else:
                msg = await message.reply("🖼️ <b>Распознаю изображение...</b>")
                image_data = await media_service.download_image(message)
            
            if image_data:
                image_bytes, mime_type = image_data
            elif msg and has_image:
                # If image download failed, note it but continue
                logger.warning("Failed to download image, continuing with text only")
        
        if not msg:
            if has_voice:
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
        
        # Save incoming message and outgoing response to logs
        _save_incoming_message(chat_logs_repo, message, prompt)
        
        # Save the bot's answer to logs
        chat_id = message.chat.id
        chat_logs_repo.add_message(chat_id, "Ассистент", True, answer)
        
        # Also save to history for private chats
        user_id = getattr(message.from_user, "id", None)
        if user_id and chat_type == ChatType.PRIVATE:
            # Get media description
            media_desc = _get_media_description(message)
            
            # Build message to save
            if prompt and media_desc:
                msg_to_save = f"{media_desc}\n{prompt}"
            elif media_desc:
                msg_to_save = media_desc
            elif prompt:
                msg_to_save = prompt
            else:
                msg_to_save = "(пусто)"
            
            history_repo.add_user_message(chat_id, user_id, msg_to_save)
            
            # Save assistant message
            history_repo.add_assistant_message(chat_id, user_id, answer)

    except Exception as e:
        logger.exception("Error in auto_reply")
        try:
            if msg:
                await msg.edit_text(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
        except Exception:
            pass

