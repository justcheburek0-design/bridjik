"""Memory repository implementation."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import msgspec.json as mjson

from domain.interfaces import IMemoryRepository

logger = logging.getLogger(__name__)


class MemoryRepository(IMemoryRepository):
    """JSON-based chat and user memory repository."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._memories: dict[str, dict[int, list[dict]]] = {"chats": {}, "users": {}}
        self._load()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _migrate_chats_data(raw_chats: dict) -> dict[int, dict]:
        """Normalize chats data from any legacy format to {chat_id: {memories, metadata}}."""
        result = {}
        for k, v in raw_chats.items():
            chat_id = int(k)
            if isinstance(v, list):
                result[chat_id] = {"memories": v, "metadata": {}}
            elif isinstance(v, dict):
                result[chat_id] = {
                    "memories": v.get("memories", []),
                    "metadata": v.get("metadata", {}),
                }
            else:
                result[chat_id] = {"memories": [], "metadata": {}}
        return result

    def _get_memories_list(self, scope: str, scope_id: int) -> list[dict] | None:
        """Return the mutable memories list for the given scope/id, or None if not found."""
        if scope == "chat":
            data = self._memories["chats"].get(scope_id)
            return data["memories"] if data else None
        return self._memories["users"].get(scope_id)

    def _load(self):
        """Load memories from JSON file."""
        if not self.file_path.exists():
            self._memories = {"chats": {}, "users": {}}
            return

        try:
            data = mjson.decode(self.file_path.read_bytes())

            if isinstance(data, dict) and "chats" in data and "users" in data:
                self._memories = {
                    "chats": self._migrate_chats_data(data.get("chats", {})),
                    "users": {int(k): v for k, v in data.get("users", {}).items()},
                }
            else:
                # Very old structure: just chat_id -> memories
                self._memories = {
                    "chats": {int(k): {"memories": v, "metadata": {}} for k, v in data.items()},
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

            self.file_path.write_bytes(mjson.format(mjson.encode(data), indent=2))
        except Exception as e:
            logger.exception("Failed to save memories: %s", e)

    def get_chat_metadata(self, chat_id: int) -> dict:
        """Get cached metadata for a chat."""
        chat_data = self._memories["chats"].get(chat_id)
        if chat_data:
            return chat_data.get("metadata", {})
        return {}

    def save_chat_metadata(self, chat_id: int, metadata: dict) -> None:
        """Save metadata for a chat."""
        if chat_id not in self._memories["chats"]:
            self._memories["chats"][chat_id] = {"memories": [], "metadata": {}}

        # Update metadata, don't overwrite blindly if we want to merge (but usually overwrite is fine for sync)
        # Here we'll just replace it as requested, or merge? Let's merge for safety.
        current_meta = self._memories["chats"][chat_id].get("metadata", {})
        current_meta.update(metadata)
        self._memories["chats"][chat_id]["metadata"] = current_meta
        self._save()

    def add_chat_memory(
        self,
        chat_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
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
            self._memories["chats"][chat_id] = {"memories": [], "metadata": {}}

        self._memories["chats"][chat_id]["memories"].append(memory)
        self._save()

        logger.info(f"Added chat memory {memory_id} to chat {chat_id}")
        return memory_id

    def add_user_memory(
        self,
        user_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
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
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update a memory record. Returns True if found and updated."""
        memories_list = self._get_memories_list(scope, scope_id)
        if memories_list is None:
            return False

        for memory in memories_list:
            if memory["id"] == memory_id:
                if content is not None:
                    memory["content"] = content.strip()
                if tags is not None:
                    memory["tags"] = tags
                memory["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                logger.info(f"Updated {scope} memory {memory_id} in {scope} {scope_id}")
                return True

        return False

    def delete_memory(self, scope: str, scope_id: int, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        memories_list = self._get_memories_list(scope, scope_id)
        if memories_list is None:
            return False

        original_count = len(memories_list)
        memories_list[:] = [m for m in memories_list if m["id"] != memory_id]
        deleted = len(memories_list) < original_count

        if deleted:
            self._save()
            logger.info(f"Deleted {scope} memory {memory_id} from {scope} {scope_id}")

        return deleted

    def get_chat_memories(self, chat_id: int) -> list[dict]:
        """Get all memories for a chat."""
        chat_data = self._memories["chats"].get(chat_id)
        if chat_data:
            return chat_data.get("memories", [])
        return []

    def get_user_memories(self, user_id: int) -> list[dict]:
        """Get all memories about a user."""
        return self._memories["users"].get(user_id, [])

    def get_users_memories(self, user_ids: list[int]) -> dict:
        """Get memories about multiple users."""
        result = {}
        for user_id in user_ids:
            memories = self._memories["users"].get(user_id, [])
            if memories:
                result[user_id] = memories
        return result

    def search_memories(self, scope: str, scope_id: int, query: str) -> list[dict]:
        """Search memories by tags or content."""
        memories_list = self._get_memories_list(scope, scope_id)
        if not memories_list:
            return []

        query_lower = query.lower()
        return [
            m
            for m in memories_list
            if query_lower in m.get("content", "").lower()
            or any(query_lower in tag.lower() for tag in m.get("tags", []))
        ]

    def search_and_delete(self, scope: str, scope_id: int, query: str) -> dict | None:
        """Search for a memory and delete the first match. Returns deleted memory or None."""
        results = self.search_memories(scope, scope_id, query)

        if not results:
            return None

        # Delete first match
        memory_to_delete = results[0]
        self.delete_memory(scope, scope_id, memory_to_delete["id"])

        return memory_to_delete

    # async def find_similar_memories(  # RAG disabled - uncomment to enable
    #     self,
    #     scope: str,
    #     scope_id: int,
    #     content: str,
    #     rag_service,
    #     limit: int = 3,
    #     similarity_threshold: float = 0.7,
    # ) -> List[Tuple[dict, float]]:
    #     """Find similar memories using semantic search via RAG."""
    #     if scope not in ["chat", "user"]:
    #         return []
    #
    #     if scope == "chat":
    #         if scope_id not in self._memories["chats"]:
    #             return []
    #         memories = self._memories["chats"][scope_id]["memories"]
    #     else:
    #         if scope_id not in self._memories["users"]:
    #             return []
    #         memories = self._memories["users"][scope_id]
    #
    #     if not memories:
    #         return []
    #
    #     try:
    #         import numpy as np
    #
    #         # Get all memories for this scope
    #         all_texts = [content] + [m["content"] for m in memories]
    #         embeddings = await rag_service._embed_batch(all_texts)
    #
    #         if not embeddings or len(embeddings) != len(all_texts):
    #             return []
    #
    #         query_emb = np.array(embeddings[0], dtype="float32")
    #         query_emb /= max(np.linalg.norm(query_emb), 1e-12)
    #
    #         memory_embs = np.array(embeddings[1:], dtype="float32")
    #         norms = np.linalg.norm(memory_embs, axis=1, keepdims=True)
    #         norms = np.maximum(norms, 1e-12)
    #         memory_embs /= norms
    #
    #         similarities = memory_embs @ query_emb
    #
    #         results = []
    #         for idx, sim in enumerate(similarities):
    #             if sim >= similarity_threshold:
    #                 results.append((memories[idx], float(sim)))
    #
    #         results.sort(key=lambda x: x[1], reverse=True)
    #         return results[:limit]
    #
    #     except Exception as e:
    #         logger.exception(f"Failed to find similar memories: {e}")
    #         return []

    def restore_from_json(self, json_content: str) -> bool:
        """Restore memories from JSON string. Returns True on success."""
        try:
            data = mjson.decode(
                json_content.encode() if isinstance(json_content, str) else json_content
            )

            if isinstance(data, dict) and "chats" in data:
                chats_data = self._migrate_chats_data(data.get("chats", {}))
                users_data = {int(k): v for k, v in data.get("users", {}).items()}
            else:
                # Old structure fallback: top-level keys are chat_ids
                chats_data = {
                    int(k): {"memories": v, "metadata": {}} for k, v in data.items() if k != "users"
                }
                users_data = {}

            self._memories = {"chats": chats_data, "users": users_data}
            self._save()
            logger.info("Restored memories successfully")
            return True
        except Exception as e:
            logger.exception(f"Failed to restore memories: {e}")
            return False
