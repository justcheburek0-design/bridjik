from dataclasses import dataclass
from typing import Optional

from aiogram import types


@dataclass
class IncomingMessageDTO:
    """Data Transfer Object for incoming Telegram messages."""

    # Raw Telegram objects
    original_message: types.Message
    chat_id: int
    user_id: Optional[int]

    # Extracted data
    text: str
    author_name: str
    is_bot: bool
    chat_type: str

    # Media flags
    has_image: bool
    has_voice: bool

    # Media content (populated by MediaService if needed, or extracted early)
    # Ideally, we pass the raw message to MediaService to download,
    # but for decision making in AIService, we might just need flags.
    # We'll store potential media attributes here.
    image_bytes: Optional[bytes] = None
    mime_type: Optional[str] = None

    @classmethod
    def from_telegram(cls, message: types.Message) -> "IncomingMessageDTO":
        """Factory method to create DTO from Telegram message."""
        text = (message.text or message.caption or "").strip()

        # Check for media presence
        has_photo = bool(message.photo)
        has_document = bool(message.document)
        has_sticker = bool(message.sticker)
        has_animation = bool(message.animation)
        has_voice = bool(message.voice)

        # Basic check for image-like document
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
