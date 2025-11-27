"""Stickers repository."""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class StickersRepository:
    """Repository for managing stickers."""

    def __init__(self, stickers_file: Path):
        self.stickers_file = stickers_file
        self._stickers: Dict[str, str] = {}
        self._load_stickers()

    def _load_stickers(self) -> None:
        """Load stickers from JSON file."""
        if not self.stickers_file.exists():
            logger.warning(f"Stickers file not found: {self.stickers_file}")
            self._stickers = {}
            return

        try:
            with open(self.stickers_file, "r", encoding="utf-8") as f:
                self._stickers = json.load(f)
            logger.info(f"Loaded {len(self._stickers)} stickers")
        except Exception:
            logger.exception("Failed to load stickers")
            self._stickers = {}

    def _save_stickers(self) -> None:
        """Save stickers to JSON file."""
        try:
            with open(self.stickers_file, "w", encoding="utf-8") as f:
                json.dump(self._stickers, f, ensure_ascii=False, indent=4)
        except Exception:
            logger.exception("Failed to save stickers")

    def get_sticker(self, name: str) -> Optional[str]:
        """Get sticker file_id by name (case-insensitive)."""
        return self._stickers.get(name.lower())

    def add_sticker(self, name: str, file_id: str) -> None:
        """Add or update a sticker."""
        self._stickers[name.lower()] = file_id
        self._save_stickers()

    def delete_sticker(self, name: str) -> bool:
        """Delete a sticker. Returns True if deleted."""
        name_lower = name.lower()
        if name_lower in self._stickers:
            del self._stickers[name_lower]
            self._save_stickers()
            return True
        return False

    def get_all_stickers(self) -> Dict[str, str]:
        """Get all stickers."""
        return self._stickers.copy()
