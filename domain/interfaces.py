"""Repository interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod


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
    def get_history(self, chat_id: int, user_id: int) -> list[dict]:
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
        message_id: int | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
    ) -> None:
        """Add message to chat logs."""
        pass

    @abstractmethod
    def update_reactions(
        self, chat_id: int, message_id: int, reactions: dict[str, list[str]]
    ) -> None:
        """Update reactions for a message."""
        pass

    @abstractmethod
    def get_recent_messages(
        self, chat_id: int, limit: int
    ) -> list[
        tuple[
            int | None, str, bool, str, bytes | None, str | None, str | None, dict[str, list[str]]
        ]
    ]:
        """Get recent messages. returns (message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions)."""
        pass

    @abstractmethod
    def get_message_by_id(self, chat_id: int, message_id: int) -> tuple[str, bool, str] | None:
        """Get message by message_id. Returns (author, is_bot, text) or None if not found."""
        pass


class IMemoryRepository(ABC):
    """Interface for chat and user memory repository.

    Memory is divided into two types:
    - Chat memory: local memes, jokes, chat-specific information
    - User memory: global information about users (city, education, health, etc.)
    """

    @abstractmethod
    def add_chat_memory(
        self,
        chat_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
    ) -> str:
        """Add a memory record for a chat. Returns memory ID."""
        pass

    @abstractmethod
    def add_user_memory(
        self,
        user_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
    ) -> str:
        """Add a memory record about a user. Returns memory ID."""
        pass

    @abstractmethod
    def update_memory(
        self,
        scope: str,
        scope_id: int,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update a memory record. Returns True if found and updated."""
        pass

    @abstractmethod
    def delete_memory(self, scope: str, scope_id: int, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        pass

    @abstractmethod
    def get_chat_memories(self, chat_id: int) -> list[dict]:
        """Get all memories for a chat."""
        pass

    @abstractmethod
    def get_user_memories(self, user_id: int) -> list[dict]:
        """Get all memories about a user."""
        pass

    @abstractmethod
    def get_users_memories(self, user_ids: list[int]) -> dict:
        """Get memories about multiple users. Returns dict mapping user_id -> list of memories."""
        pass

    @abstractmethod
    def search_memories(self, scope: str, scope_id: int, query: str) -> list[dict]:
        """Search memories by tags or content."""
        pass

    @abstractmethod
    def search_and_delete(self, scope: str, scope_id: int, query: str) -> dict | None:
        """Search for a memory and delete the first match. Returns deleted memory or None."""
        pass

    # @abstractmethod  # RAG disabled - uncomment to enable
    # async def find_similar_memories(
    #     self,
    #     scope: str,
    #     scope_id: int,
    #     content: str,
    #     rag_service,
    #     limit: int = 3,
    #     similarity_threshold: float = 0.7,
    # ) -> List[Tuple[dict, float]]:
    #     """Find similar memories using semantic search.
    #
    #     Args:
    #         scope: "chat" or "user"
    #         scope_id: chat_id or user_id
    #         content: Content to search for similar memories
    #         rag_service: RAG service instance for embeddings
    #         limit: Maximum number of similar memories to return
    #         similarity_threshold: Minimum similarity score (0.0-1.0)
    #     """
    #     pass


class IFreezesRepository(ABC):
    """Interface for auto-reply freezes repository."""

    @abstractmethod
    def set_freeze(self, user_id: int, hours: int) -> float:
        """Set freeze for user. Returns expiration timestamp."""
        pass

    @abstractmethod
    def get_freeze(self, user_id: int) -> float | None:
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
