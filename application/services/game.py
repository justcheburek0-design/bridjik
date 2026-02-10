"""Game service."""

from typing import Optional

from domain.interfaces import IMemoryRepository


class GameService:
    """Service for game-related operations."""

    def __init__(self, memory_repo: IMemoryRepository):
        self.memory_repo = memory_repo

    def start_guess_game(self, chat_id: int, obj: str) -> None:
        """Start guessing game for chat using memory with #game and #guess tags."""
        # Check if game already exists
        existing = self.memory_repo.search_memories("chat", chat_id, "#game")
        if existing:
            # Update existing game
            mem_id = existing[0]["id"]
            self.memory_repo.update_memory(
                "chat", chat_id, mem_id, content=f"Загаданный предмет: {obj}"
            )
        else:
            # Create new game memory
            self.memory_repo.add_chat_memory(
                chat_id=chat_id,
                content=f"Загаданный предмет: {obj}",
                tags=["#game", "#guess"],
            )

    def get_guessed_object(self, chat_id: int) -> Optional[str]:
        """Get guessed object for chat from memory."""
        memories = self.memory_repo.search_memories("chat", chat_id, "#game")
        if memories:
            content = memories[0].get("content", "")
            # Extract object from "Загаданный предмет: {obj}"
            if content.startswith("Загаданный предмет: "):
                return content[len("Загаданный предмет: ") :]
        return None

    def stop_guess_game(self, chat_id: int) -> None:
        """Stop guessing game for chat by deleting game memory."""
        self.memory_repo.search_and_delete("chat", chat_id, "#game")

    def is_game_active(self, chat_id: int) -> bool:
        """Check if game is active for chat."""
        memories = self.memory_repo.search_memories("chat", chat_id, "#game")
        return len(memories) > 0
