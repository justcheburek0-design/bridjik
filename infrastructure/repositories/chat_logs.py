"""Chat logs repository implementation."""

import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Deque, Optional
from collections import defaultdict, deque

from domain.interfaces import IChatLogsRepository
from utils.text import shorten


class ChatLogsRepository(IChatLogsRepository):
    """JSON-based chat logs repository."""

    def __init__(self, file_path: Path, max_messages: int = 12):
        self.file_path = file_path
        self.max_messages = max_messages
        self._logs: Dict[int, Deque[Tuple[Optional[int], str, bool, str]]] = (
            defaultdict(lambda: deque(maxlen=max_messages))
        )
        self._load()

    def _load(self) -> None:
        """Load chat logs from JSON file."""
        try:
            if not self.file_path.exists():
                return

            data = json.loads(self.file_path.read_text(encoding="utf-8") or "{}")
            for key, items in data.items():
                try:
                    chat_id = int(key)
                except Exception:
                    continue

                dq: Deque[Tuple[Optional[int], str, bool, str]] = deque(
                    maxlen=self.max_messages
                )
                for row in items:
                    try:
                        # Skip if it's history format (dict)
                        if isinstance(row, dict):
                            continue
                        # Support both old format (3 elements) and new format (4 elements)
                        if len(row) == 3:
                            # Old format: [author, is_bot, msg]
                            author, is_bot, msg = row
                            message_id = None
                        else:
                            # New format: [message_id, author, is_bot, msg]
                            message_id, author, is_bot, msg = row
                            message_id = (
                                int(message_id) if message_id is not None else None
                            )
                        dq.append(
                            (message_id, str(author), bool(is_bot), shorten(str(msg)))
                        )
                    except Exception:
                        continue
                if dq:
                    self._logs[chat_id] = dq
        except Exception:
            logging.exception("Failed to load chat logs from JSON")

    def _save(self) -> None:
        """Save chat logs to JSON file."""
        try:
            out: Dict[str, list] = {}
            for chat_id, dq in self._logs.items():
                out[str(chat_id)] = [
                    [message_id, author, bool(is_bot), msg]
                    for (message_id, author, is_bot, msg) in dq
                ]

            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            logging.exception("Failed to save chat logs to JSON")

    def add_message(
        self,
        chat_id: int,
        author: str,
        is_bot: bool,
        text: str,
        message_id: Optional[int] = None,
    ) -> None:
        """Add message to chat logs."""
        self._logs[chat_id].append((message_id, author, is_bot, shorten(text)))
        self._save()

    def get_recent_messages(
        self, chat_id: int, limit: int
    ) -> List[Tuple[Optional[int], str, bool, str]]:
        """Get recent messages."""
        messages = list(self._logs.get(chat_id, deque()))
        return messages[-limit:] if limit else messages

    def get_message_by_id(
        self, chat_id: int, message_id: int
    ) -> Optional[Tuple[str, bool, str]]:
        """Get message by message_id.

        Args:
            chat_id: Chat ID
            message_id: Message ID to find

        Returns:
            Tuple of (author, is_bot, text) or None if not found
        """
        messages = list(self._logs.get(chat_id, deque()))
        for msg_id, author, is_bot, text in messages:
            if msg_id == message_id:
                return (author, is_bot, text)
        return None
