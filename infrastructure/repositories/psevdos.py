"""Psevdonyms repository implementation."""

import logging
import re
from pathlib import Path
from typing import Dict, Optional

import msgspec.json as mjson

from domain.interfaces import IPsevdoRepository


class PsevdoRepository(IPsevdoRepository):
    """JSON-based user psevdonyms repository."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._psevdos: Dict[int, str] = {}
        self._load()

    def _load(self) -> None:
        """Load psevdonyms from JSON file."""
        try:
            if not self.file_path.exists():
                return

            raw = self.file_path.read_bytes()
            data = mjson.decode(raw) if raw.strip() else {}
            self._psevdos = {int(k): str(v) for k, v in data.items() if str(v).strip()}
        except Exception as e:
            logging.exception("Failed to load psevdos: %s", e)
            self._psevdos = {}

    def _save(self) -> None:
        """Save psevdonyms to JSON file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data = {str(k): v for k, v in self._psevdos.items()}
            self.file_path.write_bytes(mjson.format(mjson.encode(data), indent=2))
        except Exception as e:
            logging.exception("Failed to save psevdos: %s", e)

    def set_psevdo(self, user_id: int, name: str) -> str:
        """Set user psevdonym. Returns normalized name."""
        name = (name or "").strip()
        # Normalize whitespace and length
        name = re.sub(r"\s+", " ", name)
        if len(name) > 100:
            name = name[:100]

        self._psevdos[user_id] = name
        self._save()
        return name

    def get_psevdo(self, user_id: int) -> Optional[str]:
        """Get user psevdonym."""
        return self._psevdos.get(user_id)
