"""Repository interfaces."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple


class IHistoryRepository(ABC):
    """Interface for conversation history repository."""

    @abstractmethod
    def add_user_message(self, chat_id: int, user_id: int, text: str) -> None:
        """Add user message to history."""
        pass

    @abstractmethod
    def add_user_message_with_image(
        self, chat_id: int, user_id: int, text: str, image_bytes: bytes, mime_type: str
    ) -> None:
        """Add user message with image to history."""
        pass

    @abstractmethod
    def add_assistant_message(self, chat_id: int, user_id: int, text: str) -> None:
        """Add assistant message to history."""
        pass

    @abstractmethod
    def add_assistant_message_with_image(
        self, chat_id: int, user_id: int, text: str, image_bytes: bytes, mime_type: str
    ) -> None:
        """Add assistant message with image to history."""
        pass

    @abstractmethod
    def get_history(self, chat_id: int, user_id: int) -> List[dict]:
        """Get conversation history. Returns list of message dicts."""
        pass


class IChatLogsRepository(ABC):
    """Interface for chat logs repository."""

    @abstractmethod
    def add_message(
        self,
        chat_id: int,
        author: str,
        is_bot: bool,
        text: str,
        message_id: Optional[int] = None,
        image_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> None:
        """Add message to chat logs.

        Args:
            chat_id: Chat ID
            author: Author name
            is_bot: Whether message is from bot
            text: Text content (including media description)
            message_id: Optional message ID
            image_bytes: Optional image data
            mime_type: Optional MIME type for image
        """
        pass

    @abstractmethod
    def update_reactions(
        self, chat_id: int, message_id: int, reactions: dict[str, list[str]]
    ) -> None:
        """Update reactions for a message.

        Args:
            chat_id: Chat ID
            message_id: Message ID
            reactions: Dictionary mapping author_name to list of reaction emojis
        """
        pass

    @abstractmethod
    def get_recent_messages(
        self, chat_id: int, limit: int
    ) -> List[
        Tuple[
            Optional[int],
            str,
            bool,
            str,
            Optional[bytes],
            Optional[str],
            Optional[str],
            dict[str, list[str]],
        ]
    ]:
        """Get recent messages. returns (message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions)."""
        pass

    @abstractmethod
    def get_message_by_id(self, chat_id: int, message_id: int) -> Optional[Tuple[str, bool, str]]:
        """Get message by message_id. Returns (author, is_bot, text) or None if not found."""
        pass


class IPsevdoRepository(ABC):
    """Interface for user psevdonyms repository."""

    @abstractmethod
    def set_psevdo(self, user_id: int, name: str) -> str:
        """Set user psevdonym. Returns normalized name."""
        pass

    @abstractmethod
    def get_psevdo(self, user_id: int) -> Optional[str]:
        """Get user psevdonym."""
        pass


class IFreezesRepository(ABC):
    """Interface for auto-reply freezes repository."""

    @abstractmethod
    def set_freeze(self, user_id: int, hours: int) -> float:
        """Set freeze for user. Returns expiration timestamp."""
        pass

    @abstractmethod
    def get_freeze(self, user_id: int) -> Optional[float]:
        """Get freeze expiration timestamp."""
        pass

    @abstractmethod
    def clear_freeze(self, user_id: int) -> bool:
        """Clear freeze. Returns True if freeze was removed."""
        pass

    @abstractmethod
    def is_frozen(self, user_id: int) -> bool:
        """Check if user is frozen."""
        pass


class IGuessesRepository(ABC):
    """Interface for guessing game repository."""

    @abstractmethod
    def set_guess(self, chat_id: int, obj: str) -> None:
        """Set guessed object for chat."""
        pass

    @abstractmethod
    def get_guess(self, chat_id: int) -> Optional[str]:
        """Get guessed object for chat."""
        pass

    @abstractmethod
    def clear_guess(self, chat_id: int) -> None:
        """Clear guessed object for chat."""
        pass
