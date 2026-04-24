"""Memory repository implementation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import msgspec.json as mjson
import structlog

from domain.entities import Memory
from domain.interfaces import IMemoryRepository
from infrastructure.repositories.base import BaseJSONRepository

log = structlog.get_logger(__name__)

_EMPTY_MEMORIES: dict = {"chats": {}, "users": {}}


def _memory_from_dict(d: dict) -> Memory:
    return Memory(
        id=d.get("id", ""),
        content=d.get("content", ""),
        tags=d.get("tags", []),
        timestamp=d.get("timestamp", ""),
        author_id=d.get("author_id"),
        updated_at=d.get("updated_at"),
    )


def _memory_to_dict(m: Memory) -> dict:
    d = {
        "id": m.id,
        "content": m.content,
        "tags": m.tags,
        "timestamp": m.timestamp,
    }
    if m.author_id is not None:
        d["author_id"] = m.author_id
    if m.updated_at is not None:
        d["updated_at"] = m.updated_at
    return d


class MemoryRepository(BaseJSONRepository, IMemoryRepository):
    """JSON-based chat and user memory repository."""

    def __init__(self, file_path: Path):
        super().__init__(file_path)

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
        if scope == "chat":
            data = self._memories["chats"].get(scope_id)
            return data["memories"] if data else None
        return self._memories["users"].get(scope_id)

    @property
    def _memories(self) -> dict:
        return self._data  # type: ignore[return-value]

    def _load(self) -> None:
        if not self.file_path.exists():
            self._data = {"chats": {}, "users": {}}
            return
        try:
            data = mjson.decode(self.file_path.read_bytes())
            if isinstance(data, dict) and "chats" in data and "users" in data:
                self._data = {
                    "chats": self._migrate_chats_data(data.get("chats", {})),
                    "users": {int(k): v for k, v in data.get("users", {}).items()},
                }
            else:
                self._data = {
                    "chats": {int(k): {"memories": v, "metadata": {}} for k, v in data.items()},
                    "users": {},
                }
            log.info(
                "memories.loaded",
                chats=len(self._data["chats"]),
                users=len(self._data["users"]),
            )
        except Exception as e:
            log.exception("memories.load_failed", error=str(e))
            self._data = {"chats": {}, "users": {}}

    def _save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "chats": {str(k): v for k, v in self._data["chats"].items()},
                "users": {str(k): v for k, v in self._data["users"].items()},
            }
            self.file_path.write_bytes(mjson.format(mjson.encode(data), indent=2))
        except Exception as e:
            log.exception("memories.save_failed", error=str(e))

    # -------------------------------------------------------------------------
    # Chat metadata
    # -------------------------------------------------------------------------

    def get_chat_metadata(self, chat_id: int) -> dict:
        chat_data = self._memories["chats"].get(chat_id)
        return chat_data.get("metadata", {}) if chat_data else {}

    def save_chat_metadata(self, chat_id: int, metadata: dict) -> None:
        if chat_id not in self._memories["chats"]:
            self._memories["chats"][chat_id] = {"memories": [], "metadata": {}}
        current = self._memories["chats"][chat_id].get("metadata", {})
        current.update(metadata)
        self._memories["chats"][chat_id]["metadata"] = current
        self._save()

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    def add_chat_memory(
        self,
        chat_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
    ) -> str:
        memory = Memory(
            id=str(uuid.uuid4()),
            content=content.strip(),
            tags=tags or [],
            timestamp=datetime.now(timezone.utc).isoformat(),
            author_id=author_id,
        )
        if chat_id not in self._memories["chats"]:
            self._memories["chats"][chat_id] = {"memories": [], "metadata": {}}
        self._memories["chats"][chat_id]["memories"].append(_memory_to_dict(memory))
        self._save()
        log.info("memory.added", scope="chat", chat_id=chat_id, memory_id=memory.id)
        return memory.id

    def add_user_memory(
        self,
        user_id: int,
        content: str,
        tags: list[str] | None = None,
        author_id: int | None = None,
    ) -> str:
        memory = Memory(
            id=str(uuid.uuid4()),
            content=content.strip(),
            tags=tags or [],
            timestamp=datetime.now(timezone.utc).isoformat(),
            author_id=author_id,
        )
        if user_id not in self._memories["users"]:
            self._memories["users"][user_id] = []
        self._memories["users"][user_id].append(_memory_to_dict(memory))
        self._save()
        log.info("memory.added", scope="user", user_id=user_id, memory_id=memory.id)
        return memory.id

    def update_memory(
        self,
        scope: str,
        scope_id: int,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        memories_list = self._get_memories_list(scope, scope_id)
        if memories_list is None:
            return False
        for d in memories_list:
            if d["id"] == memory_id:
                if content is not None:
                    d["content"] = content.strip()
                if tags is not None:
                    d["tags"] = tags
                d["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                log.info("memory.updated", scope=scope, scope_id=scope_id, memory_id=memory_id)
                return True
        return False

    def delete_memory(self, scope: str, scope_id: int, memory_id: str) -> bool:
        memories_list = self._get_memories_list(scope, scope_id)
        if memories_list is None:
            return False
        original = len(memories_list)
        memories_list[:] = [m for m in memories_list if m["id"] != memory_id]
        if len(memories_list) < original:
            self._save()
            log.info("memory.deleted", scope=scope, scope_id=scope_id, memory_id=memory_id)
            return True
        return False

    # -------------------------------------------------------------------------
    # Queries — return Memory objects for type-safe access
    # -------------------------------------------------------------------------

    def get_chat_memories(self, chat_id: int) -> list[dict]:
        chat_data = self._memories["chats"].get(chat_id)
        return chat_data.get("memories", []) if chat_data else []

    def get_user_memories(self, user_id: int) -> list[dict]:
        return self._memories["users"].get(user_id, [])

    def get_users_memories(self, user_ids: list[int]) -> dict:
        return {uid: mems for uid in user_ids if (mems := self._memories["users"].get(uid))}

    def search_memories(self, scope: str, scope_id: int, query: str) -> list[dict]:
        memories_list = self._get_memories_list(scope, scope_id)
        if not memories_list:
            return []
        q = query.lower()
        return [
            m
            for m in memories_list
            if q in m.get("content", "").lower()
            or any(q in tag.lower() for tag in m.get("tags", []))
        ]

    def search_and_delete(self, scope: str, scope_id: int, query: str) -> dict | None:
        results = self.search_memories(scope, scope_id, query)
        if not results:
            return None
        target = results[0]
        self.delete_memory(scope, scope_id, target["id"])
        return target

    # -------------------------------------------------------------------------
    # Backup / restore
    # -------------------------------------------------------------------------

    def restore_from_json(self, json_content: str) -> bool:
        try:
            data = mjson.decode(
                json_content.encode() if isinstance(json_content, str) else json_content
            )
            if isinstance(data, dict) and "chats" in data:
                chats = self._migrate_chats_data(data.get("chats", {}))
                users = {int(k): v for k, v in data.get("users", {}).items()}
            else:
                chats = {
                    int(k): {"memories": v, "metadata": {}} for k, v in data.items() if k != "users"
                }
                users = {}
            self._data = {"chats": chats, "users": users}
            self._save()
            log.info("memories.restored")
            return True
        except Exception as e:
            log.exception("memories.restore_failed", error=str(e))
            return False
