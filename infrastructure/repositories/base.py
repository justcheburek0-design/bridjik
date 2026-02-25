"""Base repository for JSON-based storage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Generic, TypeVar

import msgspec.json as mjson

from utils.error_handlers import handle_file_operation, handle_json_operation

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseJSONRepository(Generic[T]):
    """Base class for JSON-based repositories.

    Provides common functionality for loading and saving JSON data.
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._data: dict[str, T] = {}
        self._load()

    def _load(self) -> None:
        """Load data from JSON file."""

        def load_operation():
            if not self.file_path.exists():
                return {}

            raw = self.file_path.read_bytes()
            return mjson.decode(raw) if raw.strip() else {}

        data = handle_json_operation(load_operation, f"Loading {self.file_path.name}", {})

        if isinstance(data, dict):
            self._data = data
        else:
            logger.warning("Invalid data format in %s, using empty dict", self.file_path.name)
            self._data = {}

    def _save(self) -> None:
        """Save data to JSON file."""

        def save_operation():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_bytes(mjson.format(mjson.encode(self._data), indent=2))

        handle_file_operation(save_operation, f"Saving {self.file_path.name}")

    def _transform_key(self, key: Any) -> str:
        return str(key)

    def _parse_key(self, key: str) -> Any | None:
        try:
            return key
        except Exception:
            return None

    def get(self, key: Any) -> T | None:
        return self._data.get(self._transform_key(key))

    def set(self, key: Any, value: T) -> None:
        self._data[self._transform_key(key)] = value
        self._save()

    def delete(self, key: Any) -> None:
        str_key = self._transform_key(key)
        if str_key in self._data:
            del self._data[str_key]
            self._save()

    def get_all(self) -> dict[str, T]:
        return self._data.copy()
