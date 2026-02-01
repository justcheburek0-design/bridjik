"""Chat logs repository implementation."""

import asyncio
import base64
import json
import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from domain.interfaces import IChatLogsRepository
from utils.text import shorten


class ChatLogsRepository(IChatLogsRepository):
    """JSON-based chat logs repository."""

    def __init__(self, file_path: Path, max_messages: int = 12):
        self.file_path = file_path
        self.max_messages = max_messages
        # Store: (message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions)
        # reactions is a dict: {user_id: [emoji1, emoji2]}
        self._logs: Dict[
            int,
            Deque[
                Tuple[
                    Optional[int],
                    str,
                    bool,
                    str,
                    Optional[bytes],
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    dict[str, list[str]],
                ]
            ],
        ] = defaultdict(lambda: deque(maxlen=max_messages))
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

                dq: Deque[
                    Tuple[
                        Optional[int],
                        str,
                        bool,
                        str,
                        Optional[bytes],
                        Optional[str],
                        Optional[str],
                        dict[int, list[str]],
                    ]
                ] = deque(maxlen=self.max_messages)
                for row in items:
                    try:
                        # Skip if it's history format (dict)
                        if isinstance(row, dict):
                            continue

                        # Initialize defaults
                        message_id = None
                        author = "Unknown"
                        is_bot = False
                        msg = ""
                        image_bytes = None
                        mime_type = None
                        file_id = None
                        reactions = {}

                        # Support multiple formats
                        if len(row) == 3:
                            # Old format: [author, is_bot, msg]
                            author, is_bot, msg = row
                        elif len(row) == 4:
                            # Format: [message_id, author, is_bot, msg]
                            message_id, author, is_bot, msg = row
                            message_id = int(message_id) if message_id is not None else None
                        elif len(row) == 6:
                            # Old format: [message_id, author, is_bot, msg, image_b64, mime]
                            message_id, author, is_bot, msg, image_b64, mime = row
                            message_id = int(message_id) if message_id is not None else None
                            if image_b64:
                                try:
                                    image_bytes = base64.b64decode(image_b64)
                                    mime_type = mime if mime else None
                                except Exception:
                                    pass
                        elif len(row) == 7:
                            # New format: [message_id, author, is_bot, msg, image_b64, mime, file_id]
                            message_id, author, is_bot, msg, image_b64, mime, file_id = row
                            message_id = int(message_id) if message_id is not None else None
                            if image_b64:
                                try:
                                    image_bytes = base64.b64decode(image_b64)
                                    mime_type = mime if mime else None
                                except Exception:
                                    pass
                        elif len(row) == 8:
                            # New format with reactions: [..., reactions]
                            (
                                message_id,
                                author,
                                is_bot,
                                msg,
                                image_b64,
                                mime,
                                file_id,
                                reactions_raw,
                            ) = row
                            message_id = int(message_id) if message_id is not None else None
                            if image_b64:
                                try:
                                    image_bytes = base64.b64decode(image_b64)
                                    mime_type = mime if mime else None
                                except Exception:
                                    pass

                            # Normalize reactions if needed (ensure keys are strings)
                            if isinstance(reactions_raw, dict):
                                reactions = {str(k): v for k, v in reactions_raw.items()}
                        else:
                            continue

                        dq.append(
                            (
                                message_id,
                                str(author),
                                bool(is_bot),
                                shorten(str(msg)),
                                image_bytes,
                                mime_type,
                                file_id,
                                reactions,
                            )
                        )
                    except Exception:
                        continue
                if dq:
                    self._logs[chat_id] = dq
        except Exception:
            logging.exception("Failed to load chat logs from JSON")

    def _save(self) -> None:
        """Save chat logs to JSON file.

        Note: This is now run in a thread executor to avoid blocking the event loop.
        """
        try:
            out: Dict[str, list] = {}
            # Copy keys first to avoid "dictionary changed size during iteration"
            chat_ids = list(self._logs.keys())

            for chat_id in chat_ids:
                dq = self._logs[chat_id]
                # list(dq) creates a shallow copy of the deque
                out[str(chat_id)] = [
                    [
                        message_id,
                        author,
                        bool(is_bot),
                        msg,
                        base64.b64encode(img_bytes).decode("ascii") if img_bytes else None,
                        mime,
                        file_id,
                        reactions,
                    ]
                    for (
                        message_id,
                        author,
                        is_bot,
                        msg,
                        img_bytes,
                        mime,
                        file_id,
                        reactions,
                    ) in list(dq)
                ]

            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            logging.exception("Failed to save chat logs to JSON")

    def _schedule_save(self) -> None:
        """Schedule save in background."""
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._save)
        except RuntimeError:
            self._save()

    def add_message(
        self,
        chat_id: int,
        author: str,
        is_bot: bool,
        text: str,
        message_id: Optional[int] = None,
        image_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        file_id: Optional[str] = None,
        reactions: Optional[dict[int, list[str]]] = None,
    ) -> None:
        """Add message to chat logs."""
        self._logs[chat_id].append(
            (
                message_id,
                author,
                is_bot,
                shorten(text),
                image_bytes,
                mime_type,
                file_id,
                reactions or {},
            )
        )
        self._schedule_save()

    def update_reactions(
        self, chat_id: int, message_id: int, reactions: dict[int, list[str]]
    ) -> None:
        """Update reactions for a message."""
        if chat_id not in self._logs:
            return

        # We need to find the message in the deque and update it
        # Since deques don't support random access update easily, we'll iterate
        for i, item in enumerate(self._logs[chat_id]):
            # item is (message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions)
            if item[0] == message_id:
                # Found it. Tuples are immutable, so we reconstruct it
                (
                    mid,
                    author,
                    is_bot,
                    text,
                    img_bytes,
                    mime,
                    fid,
                    _,
                ) = item  # Ignore old reactions
                new_item = (
                    mid,
                    author,
                    is_bot,
                    text,
                    img_bytes,
                    mime,
                    fid,
                    reactions,
                )
                self._logs[chat_id][i] = new_item
                self._schedule_save()
                break

    def get_file_id_by_message_id(self, chat_id: int, message_id: int) -> Optional[str]:
        # Get file_id by message_id from chat logs.
        if chat_id not in self._logs:
            return None

        # Check tuple length to handle old logs without reactions
        for item in self._logs[chat_id]:
            if len(item) >= 7:
                # Standardize to unpack safely
                msg_id = item[0]
                file_id = item[6]
                if msg_id == message_id and file_id:
                    return file_id
        return None

    def get_recent_messages(self, chat_id: int, limit: int) -> List[
        Tuple[
            Optional[int],
            str,
            bool,
            str,
            Optional[bytes],
            Optional[str],
            Optional[str],
            dict[int, list[str]],
        ]
    ]:
        """Get recent messages."""
        messages = list(self._logs.get(chat_id, deque()))

        # Normalize messages to 8 elements for consumption
        normalized = []
        for item in messages:
            if len(item) == 8:
                normalized.append(item)
            elif len(item) == 7:
                # Add empty reactions
                normalized.append(item + ({},))
            elif len(item) == 6:
                # Add file_id=None, reactions={}
                normalized.append(item + (None, {}))
            elif len(item) == 4:
                # (mid, auth, bot, txt) -> add img=None, mime=None, fid=None, react={}
                normalized.append(item + (None, None, None, {}))

        return normalized[-limit:] if limit else normalized

    def get_message_by_id(self, chat_id: int, message_id: int) -> Optional[Tuple[str, bool, str]]:
        """Get message by message_id.

        Args:
            chat_id: Chat ID
            message_id: Message ID to find

        Returns:
            Tuple of (author, is_bot, text) or None if not found
        """
        messages = list(self._logs.get(chat_id, deque()))
        for item in messages:
            if item[0] == message_id:
                return (item[1], item[2], item[3])  # author, is_bot, text
        return None
