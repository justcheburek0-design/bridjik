"""History repository implementation."""
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Deque, Optional
from collections import defaultdict, deque

from domain.interfaces import IHistoryRepository
from utils.text import shorten


class HistoryRepository(IHistoryRepository):
    """JSON-based conversation history repository."""
    
    def __init__(self, file_path: Path, max_messages: int = 5):
        self.file_path = file_path
        self.max_messages = max_messages
        self._history: Dict[str, Deque[Tuple[str, str]]] = defaultdict(
            lambda: deque(maxlen=max_messages)
        )
        self._load()
    
    def _make_key(self, chat_id: int, user_id: int) -> str:
        """Create storage key from chat_id and user_id."""
        return f"{chat_id}:{user_id}"
    
    def _parse_key(self, key: str) -> Optional[Tuple[int, int]]:
        """Parse storage key to chat_id and user_id."""
        try:
            chat, user = key.split(":", 1)
            return (int(chat), int(user))
        except Exception:
            return None
    
    def _load(self) -> None:
        """Load history from JSON file."""
        try:
            if not self.file_path.exists():
                return
            
            data = json.loads(self.file_path.read_text(encoding="utf-8") or "{}")
            for key, items in data.items():
                parsed_key = self._parse_key(key)
                if not parsed_key:
                    continue
                
                dq: Deque[Tuple[str, str]] = deque(maxlen=self.max_messages)
                for row in items:
                    try:
                        role, msg = row
                        dq.append((str(role), shorten(str(msg))))
                    except Exception:
                        continue
                self._history[key] = dq
        except Exception:
            logging.exception("Failed to load history from JSON")
    
    def _save(self) -> None:
        """Save history to JSON file."""
        try:
            out: Dict[str, list] = {}
            for key, dq in self._history.items():
                out[key] = [[role, msg] for role, msg in dq]
            
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps(out, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            logging.exception("Failed to save history to JSON")
    
    def add_user_message(self, chat_id: int, user_id: int, text: str) -> None:
        """Add user message to history."""
        key = self._make_key(chat_id, user_id)
        self._history[key].append(("user", shorten(text)))
        self._save()
    
    def add_assistant_message(self, chat_id: int, user_id: int, text: str) -> None:
        """Add assistant message to history."""
        key = self._make_key(chat_id, user_id)
        self._history[key].append(("assistant", shorten(text)))
        self._save()
    
    def get_history(self, chat_id: int, user_id: int) -> List[Tuple[str, str]]:
        """Get conversation history."""
        key = self._make_key(chat_id, user_id)
        return list(self._history.get(key, deque()))

