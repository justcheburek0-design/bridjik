"""Stickers repository."""

import logging
from pathlib import Path
from typing import Dict, Optional

import msgspec.json as mjson

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
            self._stickers = mjson.decode(self.stickers_file.read_bytes())
            logger.info(f"Loaded {len(self._stickers)} stickers")
        except Exception:
            logger.exception("Failed to load stickers")
            self._stickers = {}

    def _save_stickers(self) -> None:
        """Save stickers to JSON file."""
        try:
            self.stickers_file.write_bytes(mjson.format(mjson.encode(self._stickers), indent=4))
        except Exception:
            logger.exception("Failed to save stickers")

    def get_sticker(self, name: str) -> Optional[str]:
        """Get sticker file_id by name (case-insensitive)."""
        return self._stickers.get(name.lower())

    def find_by_name(self, name: str) -> Optional[str]:
        """Find sticker name by searching case-insensitively.

        Returns:
            The original sticker name if found, None otherwise.
        """
        name_lower = name.lower()
        for sticker_name in self._stickers.keys():
            if sticker_name.lower() == name_lower:
                return sticker_name
        return None

    def find_by_file_id(self, file_id: str) -> Optional[str]:
        """Find sticker name by file_id.

        Returns:
            The sticker name if found, None otherwise.
        """
        for sticker_name, sticker_file_id in self._stickers.items():
            if sticker_file_id == file_id:
                return sticker_name
        return None

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Edit distance (number of operations needed to transform s1 into s2)
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def get_sticker_fuzzy(self, name: str) -> tuple[Optional[str], Optional[str], float]:
        """Get sticker by name with fuzzy matching using Levenshtein distance.

        First tries exact match (case-insensitive), then finds most similar sticker
        if similarity is within acceptable threshold (30-40% difference).

        Args:
            name: Sticker name to search for

        Returns:
            Tuple of (file_id, actual_name, similarity_score):
            - file_id: Telegram file_id of the sticker
            - actual_name: The actual name found in database
            - similarity_score: 0.0 to 1.0, where 1.0 is exact match
            Returns (None, None, 0.0) if no suitable match found.
        """
        # Try exact match first
        exact_file_id = self.get_sticker(name)
        if exact_file_id:
            # Find the actual name (with original casing) for logging
            actual_name = self.find_by_name(name)
            return (exact_file_id, actual_name or name.lower(), 1.0)

        # No exact match - try fuzzy search
        name_lower = name.lower()
        best_match = None
        best_distance = float("inf")
        best_name = None

        for sticker_name in self._stickers.keys():
            distance = self._levenshtein_distance(name_lower, sticker_name)

            # Calculate similarity threshold based on the longer string
            max_len = max(len(name_lower), len(sticker_name))
            threshold = max_len * 0.4  # 40% difference allowed

            if distance < best_distance and distance <= threshold:
                best_distance = distance
                best_match = self._stickers[sticker_name]
                best_name = sticker_name

        if best_match:
            # Calculate similarity score (1.0 = exact, 0.0 = completely different)
            max_len = max(len(name_lower), len(best_name))
            similarity = 1.0 - (best_distance / max_len) if max_len > 0 else 0.0
            return (best_match, best_name, similarity)

        return (None, None, 0.0)

    def add_sticker(self, name: str, file_id: str) -> dict:
        """Add a new sticker.

        Args:
            name: Sticker name/description
            file_id: Telegram file_id

        Returns:
            dict with:
                - success: bool
                - message: str (error/success message)
                - duplicate_type: Optional[str] ('name' or 'file_id')
                - existing_name: Optional[str] (name of existing sticker)
        """
        # Check for duplicate by name (case-insensitive)
        existing_name = self.find_by_name(name)
        if existing_name:
            return {
                "success": False,
                "message": f"Стикер с названием '{existing_name}' уже существует",
                "duplicate_type": "name",
                "existing_name": existing_name,
            }

        # Check for duplicate by file_id
        existing_by_file_id = self.find_by_file_id(file_id)
        if existing_by_file_id:
            return {
                "success": False,
                "message": f"Этот стикер уже добавлен в базу под названием '{existing_by_file_id}'",
                "duplicate_type": "file_id",
                "existing_name": existing_by_file_id,
            }

        # Add new sticker
        self._stickers[name.lower()] = file_id
        self._save_stickers()

        return {
            "success": True,
            "message": f"Стикер '{name}' успешно добавлен",
            "duplicate_type": None,
            "existing_name": None,
        }

    def update_sticker(self, name: str, file_id: str) -> dict:
        """Update an existing sticker without duplicate checks.

        Used for editing stickers where the name is already known to exist.

        Args:
            name: Sticker name/description
            file_id: New Telegram file_id

        Returns:
            dict with success status and message
        """
        self._stickers[name.lower()] = file_id
        self._save_stickers()

        return {
            "success": True,
            "message": f"Стикер '{name}' обновлен",
            "duplicate_type": None,
            "existing_name": None,
        }

    def find_similar_stickers(self, search_term: str, limit: int = 5) -> list[str]:
        """Find stickers with names similar to the search term.

        Args:
            search_term: Term to search for (case-insensitive)
            limit: Maximum number of results to return

        Returns:
            List of similar sticker names
        """
        search_lower = search_term.lower()
        similar = []

        for sticker_name in self._stickers.keys():
            if search_lower in sticker_name:
                similar.append(sticker_name)
                if len(similar) >= limit:
                    break

        return similar

    def rename_sticker(self, old_name: str, new_name: str) -> dict:
        """Rename an existing sticker.

        Args:
            old_name: Current sticker name
            new_name: New sticker name/description

        Returns:
            dict with:
                - success: bool
                - message: str (error/success message)
                - similar_stickers: Optional[list] (suggested alternatives if not found)
        """
        # Find existing sticker (case-insensitive)
        existing_name = self.find_by_name(old_name)
        if not existing_name:
            similar = self.find_similar_stickers(old_name)
            if similar:
                return {
                    "success": False,
                    "message": f"Стикер '{old_name}' не найден",
                    "similar_stickers": similar,
                }
            else:
                return {
                    "success": False,
                    "message": f"Стикер '{old_name}' не найден в базе данных",
                    "similar_stickers": None,
                }

        # Check if new name is already taken by a different sticker
        new_name_existing = self.find_by_name(new_name)
        if new_name_existing and new_name_existing.lower() != existing_name.lower():
            return {
                "success": False,
                "message": f"Стикер с названием '{new_name_existing}' уже существует",
                "similar_stickers": None,
            }

        # If new name is the same as old name (case-insensitive), nothing to do
        if new_name.lower() == existing_name.lower():
            return {
                "success": True,
                "message": f"Стикер уже называется '{existing_name}'",
                "similar_stickers": None,
            }

        # Perform rename: get file_id, delete old entry, add new entry
        file_id = self._stickers[existing_name.lower()]
        del self._stickers[existing_name.lower()]
        self._stickers[new_name.lower()] = file_id
        self._save_stickers()

        return {
            "success": True,
            "message": f"Стикер '{existing_name}' переименован в '{new_name}'",
            "similar_stickers": None,
        }

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

    def get_stickers_file_path(self) -> Path:
        """Get the path to the stickers file."""
        return self.stickers_file

    def restore_from_json(self, json_content: str) -> bool:
        """Restore stickers from JSON content. Returns True if successful."""
        try:
            new_stickers = mjson.decode(
                json_content.encode() if isinstance(json_content, str) else json_content
            )
            if not isinstance(new_stickers, dict):
                return False

            # Validate that values are strings (file_ids)
            for k, v in new_stickers.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    return False

            self._stickers = new_stickers
            self._save_stickers()
            return True
        except Exception:
            logger.exception("Failed to restore stickers from JSON")
            return False
