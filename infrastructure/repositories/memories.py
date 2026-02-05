"""Memory repository implementation."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from domain.interfaces import IMemoryRepository

logger = logging.getLogger(__name__)


class MemoryRepository(IMemoryRepository):
    """JSON-based chat and user memory repository."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._memories: Dict[str, Dict[int, List[dict]]] = {"chats": {}, "users": {}}
        self._load()

    def _load(self):
        """Load memories from JSON file."""
        if not self.file_path.exists():
            self._memories = {"chats": {}, "users": {}}
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle new structure
            if isinstance(data, dict) and "chats" in data and "users" in data:
                # New structure: {"chats": {...}, "users": {...}}
                self._memories = {
                    "chats": {int(k): v for k, v in data.get("chats", {}).items()},
                    "users": {int(k): v for k, v in data.get("users", {}).items()},
                }
            else:
                # Old structure: just chat_id -> memories
                # Treat all as chat memories
                self._memories = {
                    "chats": {int(k): v for k, v in data.items()},
                    "users": {},
                }

            logger.info(
                f"Loaded memories: {len(self._memories['chats'])} chats, "
                f"{len(self._memories['users'])} users"
            )
        except Exception as e:
            logger.exception("Failed to load memories: %s", e)
            self._memories = {"chats": {}, "users": {}}

    def _save(self):
        """Save memories to JSON file."""
        try:
            # Ensure parent directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert integer keys to strings for JSON
            data = {
                "chats": {str(k): v for k, v in self._memories["chats"].items()},
                "users": {str(k): v for k, v in self._memories["users"].items()},
            }

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Failed to save memories: %s", e)

    def add_chat_memory(
        self,
        chat_id: int,
        content: str,
        tags: Optional[List[str]] = None,
        author_id: Optional[int] = None,
    ) -> str:
        """Add a memory record for a chat. Returns memory ID."""
        memory_id = str(uuid.uuid4())

        memory = {
            "id": memory_id,
            "content": content.strip(),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "author_id": author_id,
        }

        if chat_id not in self._memories["chats"]:
            self._memories["chats"][chat_id] = []

        self._memories["chats"][chat_id].append(memory)
        self._save()

        logger.info(f"Added chat memory {memory_id} to chat {chat_id}")
        return memory_id

    def add_user_memory(
        self,
        user_id: int,
        content: str,
        tags: Optional[List[str]] = None,
        author_id: Optional[int] = None,
    ) -> str:
        """Add a memory record about a user. Returns memory ID."""
        memory_id = str(uuid.uuid4())

        memory = {
            "id": memory_id,
            "content": content.strip(),
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Only add author_id if explicitly provided
        if author_id is not None:
            memory["author_id"] = author_id

        if user_id not in self._memories["users"]:
            self._memories["users"][user_id] = []

        self._memories["users"][user_id].append(memory)
        self._save()

        logger.info(f"Added user memory {memory_id} for user {user_id}")
        return memory_id

    def update_memory(
        self,
        scope: str,
        scope_id: int,
        memory_id: str,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Update a memory record. Returns True if found and updated."""
        if scope not in ["chat", "user"]:
            logger.warning(f"Invalid scope: {scope}")
            return False

        scope_key = "chats" if scope == "chat" else "users"

        if scope_id not in self._memories[scope_key]:
            return False

        for memory in self._memories[scope_key][scope_id]:
            if memory["id"] == memory_id:
                # Update fields if provided
                if content is not None:
                    memory["content"] = content.strip()
                if tags is not None:
                    memory["tags"] = tags

                memory["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save()

                logger.info(f"Updated {scope} memory {memory_id} in {scope_key} {scope_id}")
                return True

        return False

    def delete_memory(self, scope: str, scope_id: int, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        if scope not in ["chat", "user"]:
            logger.warning(f"Invalid scope: {scope}")
            return False

        scope_key = "chats" if scope == "chat" else "users"

        if scope_id not in self._memories[scope_key]:
            return False

        original_count = len(self._memories[scope_key][scope_id])
        self._memories[scope_key][scope_id] = [
            m for m in self._memories[scope_key][scope_id] if m["id"] != memory_id
        ]

        deleted = len(self._memories[scope_key][scope_id]) < original_count
        if deleted:
            self._save()
            logger.info(f"Deleted {scope} memory {memory_id} from {scope_key} {scope_id}")

        return deleted

    def get_chat_memories(self, chat_id: int) -> List[dict]:
        """Get all memories for a chat."""
        return self._memories["chats"].get(chat_id, [])

    def get_user_memories(self, user_id: int) -> List[dict]:
        """Get all memories about a user."""
        return self._memories["users"].get(user_id, [])

    def get_users_memories(self, user_ids: List[int]) -> dict:
        """Get memories about multiple users.

        Returns:
            Dictionary mapping user_id -> list of memories
        """
        result = {}
        for user_id in user_ids:
            memories = self._memories["users"].get(user_id, [])
            if memories:
                result[user_id] = memories
        return result

    def search_memories(self, scope: str, scope_id: int, query: str) -> List[dict]:
        """Search memories by tags or content."""
        if scope not in ["chat", "user"]:
            logger.warning(f"Invalid scope: {scope}")
            return []

        scope_key = "chats" if scope == "chat" else "users"

        if scope_id not in self._memories[scope_key]:
            return []

        query_lower = query.lower()
        results = []

        for memory in self._memories[scope_key][scope_id]:
            # Check content
            if query_lower in memory.get("content", "").lower():
                results.append(memory)
                continue

            # Check tags
            tags = memory.get("tags", [])
            if any(query_lower in tag.lower() for tag in tags):
                results.append(memory)

        return results

    def search_and_delete(self, scope: str, scope_id: int, query: str) -> Optional[dict]:
        """Search for a memory and delete the first match. Returns deleted memory or None."""
        results = self.search_memories(scope, scope_id, query)

        if not results:
            return None

        # Delete first match
        memory_to_delete = results[0]
        self.delete_memory(scope, scope_id, memory_to_delete["id"])

        return memory_to_delete

    async def find_similar_memories(
        self,
        scope: str,
        scope_id: int,
        content: str,
        rag_service,
        limit: int = 3,
        similarity_threshold: float = 0.7,
    ) -> List[Tuple[dict, float]]:
        """Find similar memories using semantic search via RAG.

        Args:
            scope: "chat" or "user"
            scope_id: chat_id or user_id
            content: Content to search for similar memories
            rag_service: RAG service instance for embeddings
            limit: Maximum number of similar memories to return
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of tuples (memory_dict, similarity_score), sorted by similarity desc
        """
        if scope not in ["chat", "user"]:
            logger.warning(f"Invalid scope: {scope}")
            return []

        scope_key = "chats" if scope == "chat" else "users"

        if scope_id not in self._memories[scope_key] or not self._memories[scope_key][scope_id]:
            return []

        try:
            import numpy as np

            # Get all memories for this scope
            memories = self._memories[scope_key][scope_id]
            if not memories:
                return []

            # Get embeddings for query content and all memory contents
            all_texts = [content] + [m["content"] for m in memories]
            embeddings = await rag_service._embed_batch(all_texts)

            if not embeddings or len(embeddings) != len(all_texts):
                logger.warning("Failed to get embeddings for similarity search")
                return []

            # Query embedding is first
            query_emb = np.array(embeddings[0], dtype="float32")
            query_emb /= max(np.linalg.norm(query_emb), 1e-12)

            # Memory embeddings are the rest
            memory_embs = np.array(embeddings[1:], dtype="float32")
            # Normalize each row
            norms = np.linalg.norm(memory_embs, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            memory_embs /= norms

            # Compute cosine similarities
            similarities = memory_embs @ query_emb

            # Find indices of memories above threshold
            results = []
            for idx, sim in enumerate(similarities):
                if sim >= similarity_threshold:
                    results.append((memories[idx], float(sim)))

            # Sort by similarity descending
            results.sort(key=lambda x: x[1], reverse=True)

            # Return top N
            return results[:limit]

        except Exception as e:
            logger.exception(f"Failed to find similar memories: {e}")
            return []

    def restore_from_json(self, json_content: str) -> bool:
        """Restore memories from JSON string. Returns True on success."""
        try:
            data = json.loads(json_content)

            # Handle new or old structure
            if isinstance(data, dict) and "chats" in data and "users" in data:
                # New structure
                self._memories = {
                    "chats": {int(k): v for k, v in data.get("chats", {}).items()},
                    "users": {int(k): v for k, v in data.get("users", {}).items()},
                }
            else:
                # Old structure - treat as chat memories
                self._memories = {
                    "chats": {int(k): v for k, v in data.items()},
                    "users": {},
                }

            self._save()
            logger.info(
                f"Restored memories: {len(self._memories['chats'])} chats, "
                f"{len(self._memories['users'])} users"
            )
            return True
        except Exception as e:
            logger.exception(f"Failed to restore memories: {e}")
            return False
