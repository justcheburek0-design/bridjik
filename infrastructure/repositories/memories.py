"""Memory repository implementation."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import (  # Tuple  # RAG disabled (used only in find_similar_memories)
    Dict,
    List,
    Optional,
)

import msgspec.json as mjson

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
            data = mjson.decode(self.file_path.read_bytes())

            # Handle new structure
            if isinstance(data, dict) and "chats" in data and "users" in data:
                chats_data = {}
                # Migration logic: convert list to dict if needed
                for k, v in data.get("chats", {}).items():
                    chat_id = int(k)
                    if isinstance(v, list):
                        # Old structure: list of memories
                        chats_data[chat_id] = {"memories": v, "metadata": {}}
                    elif isinstance(v, dict):
                        # New structure or already migrated
                        chats_data[chat_id] = {
                            "memories": v.get("memories", []),
                            "metadata": v.get("metadata", {}),
                        }
                    else:
                        chats_data[chat_id] = {"memories": [], "metadata": {}}

                self._memories = {
                    "chats": chats_data,
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
            self._memories["chats"][chat_id] = {"memories": [], "metadata": {}}

        self._memories["chats"][chat_id]["memories"].append(memory)
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

        if scope == "chat":
            if scope_id not in self._memories["chats"]:
                return False
            memories_list = self._memories["chats"][scope_id]["memories"]
        else:
            if scope_id not in self._memories["users"]:
                return False
            memories_list = self._memories["users"][scope_id]

        for memory in memories_list:
            if memory["id"] == memory_id:
                # Update fields if provided
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
        if scope not in ["chat", "user"]:
            logger.warning(f"Invalid scope: {scope}")
            return False

        if scope == "chat":
            if scope_id not in self._memories["chats"]:
                return False
            memories_list = self._memories["chats"][scope_id]["memories"]
            original_count = len(memories_list)
            self._memories["chats"][scope_id]["memories"] = [
                m for m in memories_list if m["id"] != memory_id
            ]
            deleted = len(self._memories["chats"][scope_id]["memories"]) < original_count
        else:
            if scope_id not in self._memories["users"]:
                return False
            memories_list = self._memories["users"][scope_id]
            original_count = len(memories_list)
            self._memories["users"][scope_id] = [m for m in memories_list if m["id"] != memory_id]
            deleted = len(self._memories["users"][scope_id]) < original_count

        if deleted:
            self._save()
            logger.info(f"Deleted {scope} memory {memory_id} from {scope} {scope_id}")

        return deleted

    def get_chat_memories(self, chat_id: int) -> List[dict]:
        """Get all memories for a chat."""
        chat_data = self._memories["chats"].get(chat_id)
        if chat_data:
            return chat_data.get("memories", [])
        return []

    def get_user_memories(self, user_id: int) -> List[dict]:
        """Get all memories about a user."""
        return self._memories["users"].get(user_id, [])

    def get_users_memories(self, user_ids: List[int]) -> dict:
        """Get memories about multiple users."""
        result = {}
        for user_id in user_ids:
            memories = self._memories["users"].get(user_id, [])
            if memories:
                result[user_id] = memories
        return result

    def search_memories(self, scope: str, scope_id: int, query: str) -> List[dict]:
        """Search memories by tags or content."""
        if scope not in ["chat", "user"]:
            return []

        if scope == "chat":
            if scope_id not in self._memories["chats"]:
                return []
            memories_list = self._memories["chats"][scope_id]["memories"]
        else:
            if scope_id not in self._memories["users"]:
                return []
            memories_list = self._memories["users"][scope_id]

        query_lower = query.lower()
        results = []

        for memory in memories_list:
            if query_lower in memory.get("content", "").lower():
                results.append(memory)
                continue
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

            chats_data = {}
            if isinstance(data, dict) and "chats" in data:
                # Same migration logic as _load
                for k, v in data.get("chats", {}).items():
                    chat_id = int(k)
                    if isinstance(v, list):
                        chats_data[chat_id] = {"memories": v, "metadata": {}}
                    elif isinstance(v, dict):
                        chats_data[chat_id] = {
                            "memories": v.get("memories", []),
                            "metadata": v.get("metadata", {}),
                        }
                    else:
                        chats_data[chat_id] = {"memories": [], "metadata": {}}
            else:
                # Old structure fallback
                for k, v in data.items():
                    if k != "users":
                        chats_data[int(k)] = {"memories": v, "metadata": {}}

            self._memories = {
                "chats": chats_data,
                "users": (
                    {int(k): v for k, v in data.get("users", {}).items()} if "users" in data else {}
                ),
            }

            self._save()
            logger.info("Restored memories successfully")
            return True
        except Exception as e:
            logger.exception(f"Failed to restore memories: {e}")
            return False
