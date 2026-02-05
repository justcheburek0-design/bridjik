"""Domain entities."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from application.services.rag import RAGService


logger = logging.getLogger(__name__)


@dataclass
class User:
    """User entity."""

    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    is_bot: bool = False

    def get_display_name(self) -> str:
        """Get best display name for the user."""
        if self.first_name:
            return self.first_name
        if self.username:
            return self.username
        return "Пользователь"


@dataclass
class Chat:
    """Chat entity."""

    id: int
    type: str  # "private", "group", "supergroup"
    title: Optional[str] = None


@dataclass
class MessageContext:
    """Message context for AI completion."""

    prompt: str
    user: User
    chat: Chat
    has_image: bool = False
    image_bytes: Optional[bytes] = None
    mime_type: Optional[str] = None
    rag_context: str = ""

    @classmethod
    async def create_with_rag(
        cls,
        prompt: str,
        user: "User",
        chat: "Chat",
        rag_service: "RAGService",
        has_image: bool = False,
        image_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> "MessageContext":
        """Create MessageContext with structured RAG context (JSON format).

        Args:
            prompt: The user's message/prompt
            user: User entity
            chat: Chat entity
            rag_service: RAGService instance to build context
            has_image: Whether message contains image
            image_bytes: Image data if present
            mime_type: MIME type of image

        Returns:
            MessageContext with rag_context as JSON string
        """
        rag_context = ""
        try:
            import json

            structured_context = await rag_service.build_structured_context(
                prompt, user.id, chat.id
            )
            print(structured_context)
            rag_context = json.dumps(structured_context, ensure_ascii=False)
        except Exception:
            logger.exception("RAG: failed to build structured context")

        return cls(
            prompt=prompt,
            user=user,
            chat=chat,
            has_image=has_image,
            image_bytes=image_bytes,
            mime_type=mime_type,
            rag_context=rag_context,
        )
