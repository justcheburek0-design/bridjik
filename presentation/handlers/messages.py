"""Message handlers."""
import logging
import re
from typing import Optional, Tuple
from aiogram import types, Router
from aiogram.enums import ChatType

from application.services.subscription import SubscriptionService
from application.services.user import UserService
from application.services.ai import AIService
from application.services.media import MediaService
from application.services.rag import RAGService
from application.services.strings import StringsService
from domain.entities import Chat, MessageContext
from domain.interfaces import IFreezesRepository, IChatLogsRepository, IHistoryRepository
from infrastructure.external.gemini import GeminiAPI
from presentation.decorators import handle_errors
from utils.chat_helpers import is_group_chat, get_author_name, get_message_id, is_bot_message, get_replied_message_id
from utils.message_formatter import combine_text_and_media, build_message_text_for_save
from utils.error_handlers import safe_execute_async


logger = logging.getLogger(__name__)

router = Router()

# Constants for message detection
BOT_ADDRESS_RE = re.compile(r'(?i)(?<!\w)(?:нейро-?бот(?:ик|яра)?|бот(?:ик|яра)?|бридж(?:ик)?)(?!\w)')
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

# Status messages
STATUS_PROCESSING = "⏳ <b>Думаю...</b>"
STATUS_STICKER = "🎨 <b>Распознаю стикер...</b>"
STATUS_ANIMATION = "🎬 <b>Распознаю гифку...</b>"
STATUS_IMAGE = "🖼️ <b>Распознаю изображение...</b>"
STATUS_VOICE = "🎙️ <b>Распознаю голосовое...</b>"
ERROR_MESSAGE = "Извини, не смог сформулировать ответ. Попробуй переформулировать вопрос."
SUBSCRIPTION_REQUIRED = "Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком"


def _get_message_text(message: types.Message) -> str:
    """Extract text from message (text or caption).
    
    Args:
        message: Telegram message
        
    Returns:
        Text content or empty string
    """
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


def _has_image(message: types.Message) -> Tuple[bool, bool, bool, bool, bool]:
    """Check if message contains image media.
    
    Args:
        message: Telegram message
        
    Returns:
        Tuple of (has_image, has_photo, has_image_doc, has_sticker, has_animation)
    """
    has_photo = bool(getattr(message, "photo", None))
    has_image_doc = bool(
        getattr(message, "document", None)
        and str(getattr(message.document, "mime_type", "")).startswith("image/")
    )
    has_sticker = bool(getattr(message, "sticker", None))
    has_animation = bool(getattr(message, "animation", None))
    has_image = has_photo or has_image_doc or has_sticker or has_animation
    
    return has_image, has_photo, has_image_doc, has_sticker, has_animation


async def _handle_voice_transcription(
    message: types.Message,
    media_service: MediaService,
    gemini_api: GeminiAPI
) -> Optional[str]:
    """Handle voice message transcription.
    
    Args:
        message: Telegram message with voice
        media_service: Media service
        gemini_api: Gemini API client
        
    Returns:
        Transcribed text or None
    """
    try:
        await media_service.send_typing_action(message.chat.id)
        voice_data = await media_service.download_voice(message)
        if voice_data:
            audio_bytes, mime = voice_data
            transcribed = await gemini_api.transcribe_voice(audio_bytes, mime)
            return transcribed if transcribed else None
    except Exception:
        logger.exception("voice transcription flow failed")
    
    return None


async def _download_image_media(
    message: types.Message,
    media_service: MediaService,
    has_sticker: bool,
    has_animation: bool
) -> Tuple[Optional[bytes], Optional[str], Optional[types.Message]]:
    """Download image media from message.
    
    Args:
        message: Telegram message
        media_service: Media service
        has_sticker: Whether message has sticker
        has_animation: Whether message has animation
        
    Returns:
        Tuple of (image_bytes, mime_type, status_message)
    """
    status_msg = None
    
    if has_sticker:
        status_msg = await message.reply(STATUS_STICKER)
        image_data = await media_service.download_sticker(message)
    elif has_animation:
        status_msg = await message.reply(STATUS_ANIMATION)
        image_data = await media_service.download_animation(message)
    else:
        status_msg = await message.reply(STATUS_IMAGE)
        image_data = await media_service.download_image(message)
    
    if image_data:
        return image_data[0], image_data[1], status_msg
    else:
        logger.warning("Failed to download image, continuing with text only")
        return None, None, status_msg


def _should_answer(message: types.Message, bot_username: str) -> bool:
    """Check if bot should answer in group chat.
    
    Args:
        message: Telegram message
        bot_username: Bot username
        
    Returns:
        True if bot should answer
    """
    text = _get_message_text(message)
    
    # If reply to bot's message - check if it's our bot
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user
        if is_bot_message(message.reply_to_message):
            replied_username = getattr(replied_user, "username", "") or ""
            if bot_username and replied_username == bot_username:
                # Reply to our bot - definitely answer
                return True
            # Reply to other bot - don't answer unless other conditions match
            # Continue checking other conditions below
    
    # Check mentions
    if message.entities and text:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = text[entity.offset: entity.offset + entity.length]
                if bot_username and mention_text.lstrip("@").lower() == bot_username.lower():
                    return True
    
    # Check bot address keywords
    if BOT_ADDRESS_RE.search(text):
        return True
    
    # Check questions and commands
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
    
    # If reply to any message (not necessarily bot), lower threshold
    if message.reply_to_message:
        return score >= 2
    
    return score >= 3


def _save_incoming_message(chat_logs_repo: IChatLogsRepository, message: types.Message, text: str) -> None:
    """Save incoming message to chat logs.
    
    Args:
        chat_logs_repo: Chat logs repository
        message: Telegram message
        text: Message text
    """
    chat_id = message.chat.id
    author = get_author_name(message, "unknown")
    is_bot = is_bot_message(message)
    message_id = get_message_id(message)
    
    # Build message text with reply information if present
    final_text = build_message_text_for_save(message, text)
    if not final_text or final_text == "(пусто)":
        return
    
    # Add reply information to log if this is a reply
    # if message.reply_to_message:
    #     replied_msg_id = get_replied_message_id(message)
    #     if replied_msg_id:
    #         reply_info = f"[Ответ на сообщение {replied_msg_id}] "
    #         final_text = reply_info + final_text
    
    chat_logs_repo.add_message(chat_id, author, is_bot, final_text, message_id)


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
    prompt = _get_message_text(message)
    has_image, has_photo, has_image_doc, has_sticker, has_animation = _has_image(message)
    has_voice = bool(getattr(message, "voice", None))
    user_id = getattr(message.from_user, "id", None)
    
    # Voice transcription
    if has_voice:
        transcribed = await _handle_voice_transcription(message, media_service, gemini_api)
        if transcribed:
            prompt = transcribed
    
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
    if is_group_chat(chat_type) and not _should_answer(message, config.BOT_USERNAME):
        logger.info("Skipped message without bot mention in group")
        _save_incoming_message(chat_logs_repo, message, prompt)
        return
    
    # Check subscription
    if not await subscription_service.is_subscribed(user_id):
        await message.reply(SUBSCRIPTION_REQUIRED)
        _save_incoming_message(chat_logs_repo, message, prompt)
        return
    
    msg = None
    try:
        await media_service.send_typing_action(message.chat.id)
        
        # Prepare message context
        user = user_service.create_user_from_telegram(message.from_user)
        chat = Chat(
            id=message.chat.id,
            type=str(chat_type) if chat_type else "unknown",
            title=getattr(message.chat, "title", None)
        )
        
        # Download image/sticker/animation if present
        image_bytes = None
        mime_type = None
        if has_image:
            image_bytes, mime_type, msg = await _download_image_media(
                message, media_service, has_sticker, has_animation
            )
        
        if not msg:
            msg = await message.reply(STATUS_VOICE if has_voice else STATUS_PROCESSING)
        
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
            answer = ERROR_MESSAGE
        
        # Send response with media tag support
        sent_messages = await media_service.long_text(msg, message, answer)
        
        # Save incoming message and outgoing response to logs
        _save_incoming_message(chat_logs_repo, message, prompt)
        
        # Save the bot's answer to logs with message_id
        chat_id = message.chat.id
        if sent_messages:
            for msg_id, msg_text in sent_messages:
                chat_logs_repo.add_message(chat_id, "Ассистент", True, msg_text, message_id=msg_id)
        else:
            # Fallback if no messages were captured (should not happen if answer is not empty)
            chat_logs_repo.add_message(chat_id, "Ассистент", True, answer)
        
        # Also save to history for private chats
        if user_id and chat_type == ChatType.PRIVATE:
            msg_to_save = build_message_text_for_save(message, prompt)
            history_repo.add_user_message(chat_id, user_id, msg_to_save)
            history_repo.add_assistant_message(chat_id, user_id, answer)

    except Exception as e:
        logger.exception("Error in auto_reply")
        try:
            if msg:
                await msg.edit_text(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
        except Exception:
            pass

