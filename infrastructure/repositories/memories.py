"""Memory repository implementation."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from domain.interfaces import IMemoryRepository

logger = logging.getLogger(__name__)


class MemoryRepository(IMemoryRepository):
    """JSON-based chat memory repository."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._memories: Dict[int, List[dict]] = {}
        self._load()

    def _load(self):
        """Load memories from JSON file."""
        if not self.file_path.exists():
            self._memories = {}
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Convert string keys back to integers
            self._memories = {int(k): v for k, v in data.items()}
            logger.info(f"Loaded memories for {len(self._memories)} chats")
        except Exception as e:
            logger.exception("Failed to load memories: %s", e)
            self._memories = {}

    def _save(self):
        """Save memories to JSON file."""
        try:
            # Ensure parent directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert integer keys to strings for JSON
            data = {str(k): v for k, v in self._memories.items()}

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Failed to save memories: %s", e)

    def add_memory(
        self,
        chat_id: int,
        category: str,
        content: str,
        tags: Optional[List[str]] = None,
        author_id: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Add a memory record. Returns memory ID."""
        memory_id = str(uuid.uuid4())

        memory = {
            "id": memory_id,
            "category": category,
            "content": content.strip(),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "author_id": author_id,
            "metadata": metadata or {},
        }

        if chat_id not in self._memories:
            self._memories[chat_id] = []

        self._memories[chat_id].append(memory)
        self._save()

        logger.info(f"Added memory {memory_id} to chat {chat_id} (category: {category})")
        return memory_id

    def delete_memory(self, chat_id: int, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        if chat_id not in self._memories:
            return False

        original_count = len(self._memories[chat_id])
        self._memories[chat_id] = [m for m in self._memories[chat_id] if m["id"] != memory_id]

        deleted = len(self._memories[chat_id]) < original_count
        if deleted:
            self._save()
            logger.info(f"Deleted memory {memory_id} from chat {chat_id}")

        return deleted

    def get_memories_by_category(self, chat_id: int, category: str) -> List[dict]:
        """Get all memories for a chat by category."""
        if chat_id not in self._memories:
            return []

        return [m for m in self._memories[chat_id] if m.get("category") == category]

    def search_memories(self, chat_id: int, query: str) -> List[dict]:
        """Search memories by tags or content."""
        if chat_id not in self._memories:
            return []

        query_lower = query.lower()
        results = []

        for memory in self._memories[chat_id]:
            # Check content
            if query_lower in memory.get("content", "").lower():
                results.append(memory)
                continue

            # Check tags
            tags = memory.get("tags", [])
            if any(query_lower in tag.lower() for tag in tags):
                results.append(memory)

        return results

    def search_and_delete(self, chat_id: int, query: str) -> Optional[dict]:
        """Search for a memory and delete the first match. Returns deleted memory or None."""
        results = self.search_memories(chat_id, query)

        if not results:
            return None

        # Delete first match
        memory_to_delete = results[0]
        self.delete_memory(chat_id, memory_to_delete["id"])

        return memory_to_delete

    def get_all_memories(self, chat_id: int) -> List[dict]:
        """Get all memories for a chat."""
        return self._memories.get(chat_id, [])

    def get_memory_categories(self, chat_id: int) -> Dict[str, List[dict]]:
        """Get memories grouped by category."""
        if chat_id not in self._memories:
            return {}

        categories = {}
        for memory in self._memories[chat_id]:
            category = memory.get("category", "other")
            if category not in categories:
                categories[category] = []
            categories[category].append(memory)

        return categories

    def restore_from_json(self, json_content: str) -> bool:
        """Restore memories from JSON string. Returns True on success."""
        try:
            data = json.loads(json_content)
            # Convert string keys to integers
            self._memories = {int(k): v for k, v in data.items()}
            self._save()
            logger.info(f"Restored memories for {len(self._memories)} chats")
            return True
        except Exception as e:
            logger.exception(f"Failed to restore memories: {e}")
            return False
