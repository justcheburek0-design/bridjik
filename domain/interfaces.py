"""Repository interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IHistoryRepository(Protocol):
    """Interface for conversation history repository."""

    def add_user_message(self, chat_id: int, user_id: int, text: str) -> None: ...

    def add_user_message_with_image(
        self, chat_id: int, user_id: int, text: str, image_bytes: bytes, mime_type: str
    ) -> None: ...

    def add_assistant_message(self, chat_id: int, user_id: int, text: str) -> None: ...

    def add_assistant_message_with_image(
        self, chat_id: int, user_id: int, text: str, image_bytes: bytes, mime_type: str
    ) -> None: ...

    def get_history(self, chat_id: int, user_id: int) -> list[dict]: ...


@runtime_checkable
class IChatLogsRepository(Protocol):
    """Interface for chat logs repository."""

    def add_message(
        self,
        chat_id: int,
        author: str,
        is_bot: bool,
        text: str,
        message_id: int | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
    ) -> None: ...

    def update_reactions(
        self, chat_id: int, message_id: int, reactions: dict[str, list[str]]
    ) -> None: ...

    def get_recent_messages(
        self, chat_id: int, limit: int
    ) -> list[
        tuple[
            int | None, str, bool, str, bytes | None, str | None, str | None, dict[str, list[str]]
        ]
    ]: ...

    def get_message_by_id(self, chat_id: int, message_id: int) -> tuple[str, bool, str] | None: ...


@runtime_checkable
class IMemoryRepository(Protocol):
    """Interface for chat and user memory repository.

    Memory is divided into two types:
    - Chat memory: local memes, jokes, chat-specific information
    - User memory: global information about users (city, education, health, etc.)
    """

    def add_chat_memory(
        self,
        chat_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
    ) -> str: ...

    def add_user_memory(
        self,
        user_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
    ) -> str: ...

    def update_memory(
        self,
        scope: str,
        scope_id: int,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> bool: ...

    def delete_memory(self, scope: str, scope_id: int, memory_id: str) -> bool: ...

    def get_chat_memories(self, chat_id: int) -> list[dict]: ...

    def get_user_memories(self, user_id: int) -> list[dict]: ...

    def get_users_memories(self, user_ids: list[int]) -> dict: ...

    def search_memories(self, scope: str, scope_id: int, query: str) -> list[dict]: ...

    def search_and_delete(self, scope: str, scope_id: int, query: str) -> dict | None: ...


@runtime_checkable
class IFreezesRepository(Protocol):
    """Interface for auto-reply freezes repository."""

    def set_freeze(self, user_id: int, hours: int) -> float: ...

    def get_freeze(self, user_id: int) -> float | None: ...

    def clear_freeze(self, user_id: int) -> bool: ...

    def is_frozen(self, user_id: int) -> bool: ...
