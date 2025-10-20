"""Repository interfaces."""
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Deque


class IHistoryRepository(ABC):
    """Interface for conversation history repository."""
    
    @abstractmethod
    def add_user_message(self, chat_id: int, user_id: int, text: str) -> None:
        """Add user message to history."""
        pass
    
    @abstractmethod
    def add_assistant_message(self, chat_id: int, user_id: int, text: str) -> None:
        """Add assistant message to history."""
        pass
    
    @abstractmethod
    def get_history(self, chat_id: int, user_id: int) -> List[Tuple[str, str]]:
        """Get conversation history. Returns list of (role, text) tuples."""
        pass


class IChatLogsRepository(ABC):
    """Interface for chat logs repository."""
    
    @abstractmethod
    def add_message(self, chat_id: int, author: str, is_bot: bool, text: str) -> None:
        """Add message to chat logs."""
        pass
    
    @abstractmethod
    def get_recent_messages(self, chat_id: int, limit: int) -> List[Tuple[str, bool, str]]:
        """Get recent messages. Returns list of (author, is_bot, text) tuples."""
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

