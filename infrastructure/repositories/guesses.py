"""Guessing game repository implementation."""

from __future__ import annotations

import logging
from pathlib import Path

import msgspec.json as mjson

from domain.interfaces import IGuessesRepository


class GuessesRepository(IGuessesRepository):
    """JSON-based guessing game repository."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._guesses: dict[str, str] = {}
        self._load()

    def _chat_key(self, chat_id: int) -> str:
        """Return canonical string key for chat."""
        return str(int(chat_id))

    def _load(self) -> None:
        """Load guesses from JSON file."""
        try:
            if not self.file_path.exists():
                return

            raw = self.file_path.read_bytes()
            data = mjson.decode(raw) if raw.strip() else {}
            if isinstance(data, dict):
                self._guesses.clear()
                for k, v in data.items():
                    if not isinstance(v, str) or not v:
                        continue
                    # Backward compat: previously keys were 'chat:user'
                    if isinstance(k, str) and ":" in k:
                        chat, _sep, _user = k.partition(":")
                        k = chat
                    # Normalize to string chat id
                    try:
                        chat_key = str(int(k))
                    except Exception:
                        chat_key = str(k)
                    self._guesses[chat_key] = v
        except Exception:
            logging.exception("Failed to load guesses from JSON")

    def _save(self) -> None:
        """Save guesses to JSON file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_bytes(mjson.format(mjson.encode(self._guesses), indent=2))
        except Exception:
            logging.exception("Failed to save guesses to JSON")

    def set_guess(self, chat_id: int, obj: str) -> None:
        """Set guessed object for chat."""
        self._guesses[self._chat_key(chat_id)] = (obj or "").strip()
        self._save()

    def get_guess(self, chat_id: int) -> str | None:
        """Get guessed object for chat."""
        return self._guesses.get(self._chat_key(chat_id))

    def clear_guess(self, chat_id: int) -> None:
        """Clear guessed object for chat."""
        self._guesses.pop(self._chat_key(chat_id), None)
        self._save()
