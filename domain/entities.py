"""Domain entities."""

from __future__ import annotations

import msgspec


class Memory(msgspec.Struct):
    """A single memory record (chat or user scope)."""

    id: str
    content: str
    tags: list[str] = []
    timestamp: str = ""
    author_id: int | None = None
    updated_at: str | None = None


class User(msgspec.Struct):
    """User entity."""

    id: int
    username: str | None = None
    first_name: str | None = None
    is_bot: bool = False


class Chat(msgspec.Struct):
    """Chat entity."""

    id: int
    type: str  # "private", "group", "supergroup"
    title: str | None = None


class MessageContext(msgspec.Struct):
    """Message context for AI completion."""

    prompt: str
    user: User
    chat: Chat
    has_image: bool = False
    image_bytes: bytes | None = None
    mime_type: str | None = None
