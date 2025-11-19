"""Message formatting utilities."""
from typing import Optional
from aiogram import types

from utils.message import get_message_text, get_reply_quote, get_media_description


def format_reply_message(
    message: types.Message,
    author_name: str,
    current_msg_id: Optional[int] = None,
    replied_msg_id: Optional[int] = None,
    quote: Optional[str] = None,
    is_private: bool = False,
    replied_message_text: Optional[str] = None
) -> str:
    """Format reply message for AI context.
    
    Args:
        message: Telegram message
        author_name: Author display name
        current_msg_id: Current message ID
        replied_msg_id: ID of replied message
        quote: Quote text if available
        is_private: Whether this is a private chat
        replied_message_text: Full text of replied message if available
        
    Returns:
        Formatted reply message string
    """
    current_text = get_message_text(message)
    
    # Build reply prefix
    if is_private:
        author_label = "Пользователь"
    else:
        author_label = author_name
    
    # Build replied message info
    if replied_message_text:
        # Use full text if available
        replied_info = f"сообщение {replied_msg_id} (\"{replied_message_text[:100]}{'...' if len(replied_message_text) > 100 else ''}\")"
    elif quote:
        # Use quote if available
        replied_info = f"\"{quote}\""
    elif replied_msg_id:
        # Use message ID only
        replied_info = f"сообщение {replied_msg_id}"
    else:
        replied_info = "сообщение"
    
    # Format with replied message info
    if current_msg_id:
        return f"[{current_msg_id}] {author_label} (отвечая на {replied_info}): {current_text}"
    else:
        return f"{author_label} (отвечая на {replied_info}): {current_text}"


def combine_text_and_media(text: str, media_desc: str) -> str:
    """Combine text and media description.
    
    Args:
        text: Text content
        media_desc: Media description
        
    Returns:
        Combined string, or empty string if both are empty
    """
    if text and media_desc:
        return f"{media_desc}\n\n{text}"
    elif media_desc:
        return media_desc
    elif text:
        return text
    else:
        return ""


def build_message_text_for_save(message: types.Message, prompt: str) -> str:
    """Build message text for saving to history/logs.
    
    Args:
        message: Telegram message
        prompt: User prompt text
        
    Returns:
        Combined text with media description
    """
    media_desc = get_media_description(message)
    return combine_text_and_media(prompt, media_desc) or "(пусто)"


def format_chat_history_entry(role: str, text: str) -> str:
    """Format single history entry.
    
    Args:
        role: Role name ("user" or "assistant")
        text: Message text
        
    Returns:
        Formatted entry string
    """
    who = "Пользователь" if role == "user" else "Ассистент"
    return f"{who}: {text}"


def format_chat_log_entry(
    message_id: Optional[int],
    author: str,
    is_bot: bool,
    text: str
) -> str:
    """Format single chat log entry.
    
    Args:
        message_id: Message ID if available
        author: Author name
        is_bot: Whether author is a bot
        text: Message text
        
    Returns:
        Formatted entry string
    """
    role = "Ассистент" if is_bot else author
    if message_id:
        return f"[{message_id}] {role}: {text}"
    else:
        return f"{role}: {text}"

