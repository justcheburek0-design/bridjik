from __future__ import annotations

"""Message handlers."""

import logging

from aiogram import Router, types
from aiogram.types import ReactionTypeEmoji

from application.services.ai import AIService
from application.services.media import MediaService

# from application.services.rag import RAGService  # RAG disabled
from application.services.strings import StringsService
from application.services.subscription import SubscriptionService
from domain.dtos import IncomingMessageDTO
from domain.entities import Chat, MessageContext, User
from domain.interfaces import IChatLogsRepository, IFreezesRepository, IHistoryRepository
from infrastructure.external.gemini import GeminiAPI
from presentation.decorators import handle_errors
from utils.chat_helpers import get_author_name, get_message_id, is_bot_message
from utils.message import get_reply_quote
from utils.message_formatter import build_message_text_for_save
from utils.text import truncate_text

logger = logging.getLogger(__name__)

router = Router()

# Status messages
STATUS_PROCESSING = "⏳ <b>Думаю...</b>"
STATUS_STICKER = "🎨 <b>Распознаю стикер...</b>"
STATUS_ANIMATION = "🎬 <b>Распознаю гифку...</b>"
STATUS_IMAGE = "🖼️ <b>Распознаю изображение...</b>"
STATUS_VOICE = "🎙️ <b>Распознаю голосовое...</b>"
ERROR_MESSAGE = "Извини, не смог сформулировать ответ. Попробуй переформулировать вопрос."
SUBSCRIPTION_REQUIRED = "Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком"


def _save_incoming_message(
    chat_logs_repo: IChatLogsRepository,
    message: types.Message,
    text: str,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> None:
    """Save incoming message to chat logs."""
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

    # Получить file_id стикера, если есть
    file_id = None
    if message.sticker:
        file_id = message.sticker.file_id

    chat_logs_repo.add_message(
        chat_id, author, is_bot, final_text, message_id, image_bytes, mime_type, file_id
    )


@router.message()
@handle_errors
async def auto_reply(
    message: types.Message,
    subscription_service: SubscriptionService,
    ai_service: AIService,
    media_service: MediaService,
    # rag_service: RAGService,  # RAG disabled
    strings_service: StringsService,
    gemini_api: GeminiAPI,
    freezes_repo: IFreezesRepository,
    chat_logs_repo: IChatLogsRepository,
    history_repo: IHistoryRepository,
    config,
):
    """Auto-reply with AI using Strict Separation pattern."""
    # 1. Create DTO from Telegram message
    dto = IncomingMessageDTO.from_telegram(message)

    # 2. Check Decision Logic (Service Layer)
    should_respond = await ai_service.should_respond(dto, config.BOT_USERNAME)

    # Check manual freeze
    if dto.user_id is not None and freezes_repo.is_frozen(dto.user_id):
        should_respond = False
        logger.info("Auto replies are temporarily frozen for user %s", dto.user_id)

    # 3. Media processing logic (if we are responding OR if we just need to save to logs)

    image_bytes = None
    mime_type = None
    status_msg = None

    if dto.has_image:
        # Determine status message
        status_text = STATUS_IMAGE
        if getattr(message, "sticker", None):
            status_text = STATUS_STICKER
        elif getattr(message, "animation", None):
            status_text = STATUS_ANIMATION

        if should_respond:
            status_msg = await message.reply(status_text)

        # Download logic
        # We need to determine WHICH download method to use.
        # This logic was previously in _download_image_media helper.
        # Ideally MediaService should have `download_media(message)` generic method.
        # For now, we manually branch to fail fast if needed, or we implement the helper back but smaller.

        if getattr(message, "sticker", None):
            res = await media_service.download_sticker(message)
        elif getattr(message, "animation", None) or (
            getattr(message, "document", None) and dto.has_image
        ):
            # DTO checked document mime type for us
            res = await media_service.download_animation(message)
        else:
            res = await media_service.download_image(message)

        if res:
            image_bytes, mime_type = res
            dto.image_bytes = image_bytes
            dto.mime_type = mime_type

    # Voice handling - распознаём ВСЕГДА, даже если не отвечаем
    if dto.has_voice:
        if should_respond:
            await media_service.send_typing_action(message.chat.id)
            if not status_msg:
                status_msg = await message.reply(STATUS_VOICE)

        voice_data = await media_service.download_voice(message)
        if voice_data:
            v_bytes, v_mime = voice_data
            transcribed = await gemini_api.transcribe_voice(v_bytes, v_mime)
            if transcribed:
                dto.text = transcribed  # Update DTO with transcribed text
            else:
                # Если не распознано
                dto.text = "[не распознано]"

    # 4. If shouldn't respond -> Save to logs and exit
    if not should_respond:
        if not dto.text and not image_bytes:
            return  # Empty message, nothing to log

        _save_incoming_message(chat_logs_repo, message, dto.text, image_bytes, mime_type)
        return

    # Check subscription (Business Rule)
    if not await subscription_service.is_subscribed(dto.user_id):
        await message.reply(SUBSCRIPTION_REQUIRED)
        _save_incoming_message(chat_logs_repo, message, dto.text, image_bytes, mime_type)
        return

    # 5. Process Response
    try:
        await media_service.send_typing_action(message.chat.id)

        # Create entities
        user = User(
            id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            is_bot=message.from_user.is_bot,
        )
        chat = Chat(
            id=message.chat.id,
            type=dto.chat_type,
            title=getattr(message.chat, "title", None),
        )

        if not status_msg:
            status_msg = await message.reply(STATUS_PROCESSING)

        # Load system prompt
        system_prompt = strings_service.load_system_prompt_for_chat(message.chat)

        # Create Context (RAG disabled - using simple context)
        # context = await MessageContext.create_with_rag(
        #     prompt=dto.text,
        #     user=user,
        #     chat=chat,
        #     rag_service=rag_service,
        #     has_image=bool(image_bytes),
        #     image_bytes=image_bytes,
        #     mime_type=mime_type,
        #     bot=message.bot,
        # )
        context = MessageContext(
            prompt=dto.text,
            user=user,
            chat=chat,
            has_image=bool(image_bytes),
            image_bytes=image_bytes,
            mime_type=mime_type,
        )

        # Save Incoming to logs
        _save_incoming_message(chat_logs_repo, message, dto.text, image_bytes, mime_type)

        # Callback for status updates
        async def update_status(text: str):
            try:
                if status_msg:
                    await status_msg.edit_text(text)
            except Exception:
                pass

        # Generate Answer
        answer, memory_updates, pending_reactions = await ai_service.complete(
            context=context,
            system_prompt=system_prompt,
            message=message,
            on_tool_update=update_status,
        )

        if not answer and not memory_updates and not pending_reactions:
            answer = ERROR_MESSAGE

        answer = truncate_text(answer, config.MAX_OUTPUT_LENGTH)

        # Memory updates are now included in AI response itself, no need to append
        if memory_updates:
            memory_info = "\n\n💡 <b>Память обновлена:</b> " + memory_updates[0]
            answer += memory_info

        # Send Answer
        sent_messages = await media_service.long_text(
            status_msg,
            message,
            answer,
            tts_callback=ai_service.generate_speech if config.ENABLE_TTS else None,
        )

        # Log Assistant Answer
        if sent_messages:
            for msg_entry in sent_messages:
                # Unpack: (message_id, text, image_bytes, mime_type)
                if len(msg_entry) == 4:
                    msg_id, msg_text, img_bytes, mime = msg_entry
                else:
                    msg_id, msg_text = msg_entry[:2]
                    img_bytes, mime = None, None

                chat_logs_repo.add_message(
                    message.chat.id,
                    "Ассистент",
                    True,
                    msg_text,
                    message_id=msg_id,
                    image_bytes=img_bytes,
                    mime_type=mime,
                )

        # Set pending reactions after messages are logged
        if pending_reactions:
            for emoji, excerpt in pending_reactions:
                try:
                    # Find message by excerpt using ai_service helper
                    msg_id = ai_service._find_message_by_excerpt(message.chat.id, excerpt)

                    if msg_id:
                        await message.bot.set_message_reaction(
                            chat_id=message.chat.id,
                            message_id=msg_id,
                            reaction=[ReactionTypeEmoji(emoji=emoji)],
                        )
                        logger.info(
                            f"Set reaction {emoji} on message {msg_id} (excerpt: {excerpt[:20]}...)"
                        )
                    else:
                        logger.warning(
                            f"Could not find message for reaction {emoji} with excerpt: {excerpt[:30]}..."
                        )
                except Exception as e:
                    logger.warning(f"Failed to set reaction {emoji}: {e}")
    except Exception as e:
        logger.exception("Error in auto_reply")
        try:
            if status_msg:
                await status_msg.edit_text(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
        except Exception:
            pass


@router.message_reaction()
async def on_reaction_update(
    update: types.MessageReactionUpdated,
    chat_logs_repo: IChatLogsRepository,
):
    """Handle reaction updates."""
    try:
        chat_id = update.chat.id
        message_id = update.message_id
        user = update.user

        if not user:
            return

        # Determine user name (who reacted)
        # Use simple logic: username or first_name
        author_name = user.username or user.first_name or "Unknown"

        # Find the message in logs first to get current reactions
        msg_data = None
        for item in chat_logs_repo._logs.get(chat_id, []):
            if item[0] == message_id:
                msg_data = item
                break

        if not msg_data:
            return

        # item structure: (mid, author, is_bot, text, img, mime, fid, reactions)
        current_reactions = msg_data[7]  # this is dict[int, list[str]]

        # New reactions from this user
        # update.new_reaction is a list of ReactionType
        new_emojis = []
        for react in update.new_reaction:
            if hasattr(react, "emoji"):
                new_emojis.append(react.emoji)
            elif hasattr(react, "custom_emoji_id"):
                # Represent custom emojis clearly
                new_emojis.append(f"[{react.custom_emoji_id}]")

        # Update our store
        if new_emojis:
            current_reactions[author_name] = new_emojis
        else:
            # User removed all reactions
            if author_name in current_reactions:
                del current_reactions[author_name]

        # Commit changes
        chat_logs_repo.update_reactions(chat_id, message_id, current_reactions)

    except Exception:
        logger.exception("Error handling reaction update")
