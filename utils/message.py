"""Message utilities."""
from typing import Optional
from aiogram import types


def get_media_description(message: types.Message) -> str:
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


def get_message_text(message: types.Message) -> str:
    """Extract text from message including media description."""
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    media_desc = get_media_description(message)
    
    # Combine text and media
    if text and media_desc:
        return f"{media_desc}\n\n{text}"
    elif media_desc:
        return media_desc
    elif text:
        return text
    else:
        return "(пусто)"


def get_reply_quote(message: types.Message) -> Optional[str]:
    """Extract quote text from reply message if available.
    
    Returns quote text if message has a quote,
    otherwise returns None.
    """
    # Check for quote in the message itself (Telegram Bot API 7.0+)
    quote = getattr(message, "quote", None)
    if quote:
        quote_text = getattr(quote, "text", None)
        if quote_text:
            return quote_text.strip()
            
    return None
