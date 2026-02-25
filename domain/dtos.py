from __future__ import annotations

import msgspec
from aiogram import types


class IncomingMessageDTO(msgspec.Struct):
    """Data Transfer Object for incoming Telegram messages."""

    original_message: types.Message
    chat_id: int
    user_id: int | None
    text: str
    author_name: str
    is_bot: bool
    chat_type: str
    has_image: bool
    has_voice: bool
    image_bytes: bytes | None = None
    mime_type: str | None = None

    @classmethod
    def from_telegram(cls, message: types.Message) -> IncomingMessageDTO:
        """Factory method to create DTO from Telegram message."""
        text = (message.text or message.caption or "").strip()

        has_photo = bool(message.photo)
        has_document = bool(message.document)
        has_sticker = bool(message.sticker)
        has_animation = bool(message.animation)
        has_voice = bool(message.voice)

        if has_document and message.document.mime_type:
            if message.document.mime_type.startswith("image/"):
                has_photo = True

        has_image = has_photo or has_sticker or has_animation

        return cls(
            original_message=message,
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else None,
            text=text,
            author_name=message.from_user.full_name if message.from_user else "Unknown",
            is_bot=message.from_user.is_bot if message.from_user else False,
            chat_type=message.chat.type,
            has_image=has_image,
            has_voice=has_voice,
        )
