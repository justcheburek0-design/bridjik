"""Game service."""

from typing import Optional

from domain.interfaces import IGuessesRepository


class GameService:
    """Service for game-related operations."""

    def __init__(self, guesses_repo: IGuessesRepository):
        self.guesses_repo = guesses_repo

    def start_guess_game(self, chat_id: int, obj: str) -> None:
        """Start guessing game for chat."""
        self.guesses_repo.set_guess(chat_id, obj)

    def get_guessed_object(self, chat_id: int) -> Optional[str]:
        """Get guessed object for chat."""
        return self.guesses_repo.get_guess(chat_id)

    def stop_guess_game(self, chat_id: int) -> None:
        """Stop guessing game for chat."""
        self.guesses_repo.clear_guess(chat_id)

    def is_game_active(self, chat_id: int) -> bool:
        """Check if game is active for chat."""
        return self.guesses_repo.get_guess(chat_id) is not None
