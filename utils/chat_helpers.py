"""Chat helper utilities."""
from typing import Optional, Union
from aiogram import types
from aiogram.enums import ChatType


def is_group_chat(chat_type: Optional[Union[ChatType, str]]) -> bool:
    """Check if chat is a group or supergroup.
    
    Args:
        chat_type: Chat type from aiogram (ChatType enum or string)
        
    Returns:
        True if chat is GROUP or SUPERGROUP
    """
    if chat_type is None:
        return False
    
    if isinstance(chat_type, str):
        return chat_type.upper() in ("GROUP", "SUPERGROUP")
    
    return chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)


def get_author_name(message: types.Message, fallback: str = "unknown") -> str:
    """Get author name from message.
    
    Args:
        message: Telegram message
        fallback: Default name if user is None
        
    Returns:
        Username or first_name or fallback
    """
    if not message.from_user:
        return fallback
    
    return (
        message.from_user.username
        or message.from_user.first_name
        or fallback
    )


def get_message_id(message: types.Message) -> Optional[int]:
    """Safely get message ID.
    
    Args:
        message: Telegram message
        
    Returns:
        Message ID or None if not available
    """
    # In aiogram, message.message_id is always available
    try:
        return message.message_id
    except AttributeError:
        return getattr(message, "message_id", None)


def get_replied_message_id(message: types.Message) -> Optional[int]:
    """Safely get replied message ID.
    
    Args:
        message: Telegram message
        
    Returns:
        Replied message ID or None if not available
    """
    if not message.reply_to_message:
        return None
    
    return getattr(message.reply_to_message, "message_id", None)


def is_bot_message(message: types.Message) -> bool:
    """Check if message is from a bot.
    
    Args:
        message: Telegram message
        
    Returns:
        True if message is from a bot
    """
    if not message.from_user:
        return False
    
    return bool(getattr(message.from_user, "is_bot", False))

