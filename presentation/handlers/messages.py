"""Message handlers."""

import logging
import re
from typing import Optional, Tuple

from aiogram import Router, types
from aiogram.enums import ChatType

from application.services.ai import AIService
from application.services.media import MediaService
from application.services.rag import RAGService
from application.services.strings import StringsService
from application.services.subscription import SubscriptionService
from application.services.user import UserService
from domain.entities import Chat, MessageContext
from domain.interfaces import (
    IChatLogsRepository,
    IFreezesRepository,
    IHistoryRepository,
)
from infrastructure.external.gemini import GeminiAPI
from presentation.decorators import handle_errors
from utils.chat_helpers import (
    get_author_name,
    get_message_id,
    get_replied_message_id,
    is_bot_message,
    is_group_chat,
)
from utils.error_handlers import safe_execute_async
from utils.message import get_reply_quote
from utils.message_formatter import build_message_text_for_save, combine_text_and_media
from utils.text import truncate_text

logger = logging.getLogger(__name__)

router = Router()

# Constants for message detection
BOT_ADDRESS_RE = re.compile(
    r"(?i)(?<!\w)(?:нейро-?бот(?:ик|яра)?|бот(?:ик|яра)?|бридж(?:ик)?)(?!\w)"
)
QUESTION_MARK_RE = re.compile(r"\?")
INTERROGATIVE_RE = re.compile(
    r"(?i)\b("
    r"можно ли|кто может помочь|кто поможет|подскаж(?:и|ите)|помогите|нужна помощь|help|помощь"
    r")\b"
)
COMMAND_RE = re.compile(
    r"(?i)\b("
    r"объясни|расскажи|скажи|подскажи|помоги|проверь|сделай|напиши|создай|найди|покажи|настрой"
    r")\b"
)
NOISE_RE = re.compile(r"^\s*(?:[^\w\s]|[\w]{1,2})\s*$")

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

    # Check if document is video/gif (some GIFs sent as video/mp4 documents)
    if not has_animation and getattr(message, "document", None):
        doc = message.document
        mime_type = str(getattr(doc, "mime_type", "")).lower()
        filename = str(getattr(doc, "file_name", "")).lower()
        # Treat video/mp4 and image/gif documents as animations
        if mime_type in ("video/mp4", "video/mpeg", "image/gif") or filename.endswith(
            (".gif", ".mp4", ".webm")
        ):
            has_animation = True

    has_image = has_photo or has_image_doc or has_sticker or has_animation

    return has_image, has_photo, has_image_doc, has_sticker, has_animation


async def _handle_voice_transcription(
    message: types.Message, media_service: MediaService, gemini_api: GeminiAPI
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
    has_animation: bool,
    send_status: bool = True,
) -> Tuple[Optional[bytes], Optional[str], Optional[types.Message]]:
    """Download image media from message.

    Args:
        message: Telegram message
        media_service: Media service
        has_sticker: Whether message has sticker
        has_animation: Whether message has animation
        send_status: Whether to send status message (default: True)

    Returns:
        Tuple of (image_bytes, mime_type, status_message)
    """
    status_msg = None

    if has_sticker:
        if send_status:
            status_msg = await message.reply(STATUS_STICKER)
        image_data = await media_service.download_sticker(message)
    elif has_animation:
        if send_status:
            status_msg = await message.reply(STATUS_ANIMATION)
        image_data = await media_service.download_animation(message)
    else:
        if send_status:
            status_msg = await message.reply(STATUS_IMAGE)
        image_data = await media_service.download_image(message)

    if image_data:
        image_bytes, mime_type = image_data[0], image_data[1]
        logger.info(
            f"Downloaded image: {len(image_bytes) if image_bytes else 0} bytes, mime: {mime_type}"
        )
        return image_bytes, mime_type, status_msg
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
                mention_text = text[entity.offset : entity.offset + entity.length]
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

    return score >= 4


def _save_incoming_message(
    chat_logs_repo: IChatLogsRepository,
    message: types.Message,
    text: str,
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> None:
    """Save incoming message to chat logs.

    Args:
        chat_logs_repo: Chat logs repository
        message: Telegram message
        text: Message text
        image_bytes: Optional image data
        mime_type: Optional MIME type for image
    """
    logger.info(
        f"_save_incoming_message called with: image_bytes={len(image_bytes) if image_bytes else 0} bytes, mime_type={mime_type}"
    )

    chat_id = message.chat.id
    author = get_author_name(message, "unknown")
    is_bot = is_bot_message(message)
    message_id = get_message_id(message)

    # Build message text with reply information if present
    final_text = build_message_text_for_save(message, text)
    if not final_text or final_text == "(пусто)":
        return

    # Add reply information to log if this is a reply
    if message.reply_to_message:
        replied_msg = message.reply_to_message
        replied_id = get_message_id(replied_msg)

        # Check for specific quote
        quote = get_reply_quote(message)
        if quote:
            reply_info = f'[Ответ на цитату из {replied_id}: "{quote}"] '
            final_text = reply_info + final_text
        else:
            # Get text of replied message
            replied_text = (
                getattr(replied_msg, "text", None) or getattr(replied_msg, "caption", None) or ""
            ).strip()
            # Truncate if too long
            if len(replied_text) > 50:
                replied_text = replied_text[:47] + "..."

            if replied_text:
                reply_info = f'[Ответ на {replied_id}: "{replied_text}"] '
                final_text = reply_info + final_text
            else:
                reply_info = f"[Ответ на {replied_id}] "
                final_text = reply_info + final_text

    chat_logs_repo.add_message(
        chat_id, author, is_bot, final_text, message_id, image_bytes, mime_type
    )


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
    config,
):
    """Auto-reply with AI."""
    prompt = _get_message_text(message)
    has_image, has_photo, has_image_doc, has_sticker, has_animation = _has_image(message)
    has_voice = bool(getattr(message, "voice", None))
    user_id = getattr(message.from_user, "id", None)

    # Determine if we should respond (before downloading media or transcribing)
    chat_type = getattr(message.chat, "type", None)
    should_respond = not is_group_chat(chat_type) or _should_answer(message, config.BOT_USERNAME)

    # Voice transcription - only if we will respond
    if has_voice and should_respond:
        transcribed = await _handle_voice_transcription(message, media_service, gemini_api)
        if transcribed:
            prompt = transcribed

    # Download image/sticker/animation if present
    # Always download (for logs), but send status only if we will respond
    image_bytes = None
    mime_type = None
    msg = None
    if has_image:
        image_bytes, mime_type, msg = await _download_image_media(
            message, media_service, has_sticker, has_animation, send_status=should_respond
        )

    # Check if empty message
    if not prompt and not has_image:
        _save_incoming_message(chat_logs_repo, message, prompt, image_bytes, mime_type)
        return

    # Check freeze
    if user_id is not None and freezes_repo.is_frozen(user_id):
        logger.info("Auto replies are temporarily frozen for user %s", user_id)
        _save_incoming_message(chat_logs_repo, message, prompt, image_bytes, mime_type)
        return

    # If in group and shouldn't answer - save to logs and return
    if not should_respond:
        logger.info("Skipped message without bot mention in group")
        _save_incoming_message(chat_logs_repo, message, prompt, image_bytes, mime_type)
        return

    # Check subscription
    if not await subscription_service.is_subscribed(user_id):
        await message.reply(SUBSCRIPTION_REQUIRED)
        _save_incoming_message(chat_logs_repo, message, prompt, image_bytes, mime_type)
        return

    try:
        await media_service.send_typing_action(message.chat.id)

        # Prepare message context
        user = user_service.create_user_from_telegram(message.from_user)
        chat = Chat(
            id=message.chat.id,
            type=str(chat_type) if chat_type else "unknown",
            title=getattr(message.chat, "title", None),
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
            mime_type=mime_type,
        )

        # Save incoming message to logs BEFORE generating AI response
        # This ensures the current message is included in chat context
        logger.info(
            f"Saving message with image: {len(image_bytes) if image_bytes else 0} bytes, mime: {mime_type}"
        )
        _save_incoming_message(chat_logs_repo, message, prompt, image_bytes, mime_type)

        # Define status update callback
        async def update_status(text: str):
            try:
                if msg:
                    await msg.edit_text(text)
            except Exception:
                pass

        # Get AI response
        answer = await ai_service.complete(
            context=context,
            system_prompt=system_prompt,
            message=message,
            on_tool_update=update_status,
        )

        if not answer:
            answer = ERROR_MESSAGE

        answer = truncate_text(answer, config.MAX_OUTPUT_LENGTH)

        # Send response with media tag support
        sent_messages = await media_service.long_text(
            msg,
            message,
            answer,
            tts_callback=ai_service.generate_speech if config.ENABLE_TTS else None,
        )

        # Save the bot's answer to logs with message_id
        chat_id = message.chat.id
        if sent_messages:
            for msg_entry in sent_messages:
                # Unpack: (message_id, text, image_bytes, mime_type)
                if len(msg_entry) == 4:
                    msg_id, msg_text, img_bytes, mime = msg_entry
                else:
                    # Fallback for old format
                    msg_id, msg_text = msg_entry[:2]
                    img_bytes, mime = None, None

                chat_logs_repo.add_message(
                    chat_id,
                    "Ассистент",
                    True,
                    msg_text,
                    message_id=msg_id,
                    image_bytes=img_bytes,
                    mime_type=mime,
                )
        else:
            # Fallback if no messages were captured (should not happen if answer is not empty)
            chat_logs_repo.add_message(chat_id, "Ассистент", True, answer)

    except Exception as e:
        logger.exception("Error in auto_reply")
        try:
            if msg:
                await msg.edit_text(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
        except Exception:
            pass
