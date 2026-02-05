"""Unit tests for MemoryRepository."""

import tempfile
from pathlib import Path

import pytest

from infrastructure.repositories.memories import MemoryRepository


@pytest.fixture
def temp_memory_file():
    """Create temporary memory file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = Path(f.name)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def memory_repo(temp_memory_file):
    """Create MemoryRepository instance with temp file."""
    return MemoryRepository(temp_memory_file)


class TestMemoryRepository:
    """Test cases for MemoryRepository."""

    def test_add_chat_memory(self, memory_repo):
        """Test adding a chat memory."""
        memory_id = memory_repo.add_chat_memory(
            chat_id=123,
            content="Chat memory",
            tags=["chat", "test"],
            author_id=456,
        )

        assert memory_id is not None
        assert isinstance(memory_id, str)

        memories = memory_repo.get_chat_memories(123)
        assert len(memories) == 1
        assert memories[0]["content"] == "Chat memory"
        assert memories[0]["tags"] == ["chat", "test"]
        assert memories[0]["author_id"] == 456

    def test_add_user_memory(self, memory_repo):
        """Test adding a user memory."""
        memory_id = memory_repo.add_user_memory(
            user_id=789,
            content="User memory",
            tags=["user", "fact"],
            author_id=456,
        )

        assert memory_id is not None

        memories = memory_repo.get_user_memories(789)
        assert len(memories) == 1
        assert memories[0]["content"] == "User memory"

    def test_search_memories(self, memory_repo):
        """Test searching memories."""
        memory_repo.add_chat_memory(123, "Python coding", ["coding"])
        memory_repo.add_chat_memory(123, "Java coding", ["coding"])
        memory_repo.add_chat_memory(123, "Coffee break", ["rest"])

        results = memory_repo.search_memories("chat", 123, "coding")
        assert len(results) == 2

        results = memory_repo.search_memories("chat", 123, "break")
        assert len(results) == 1

        results = memory_repo.search_memories("chat", 123, "nothing")
        assert len(results) == 0

    def test_delete_memory(self, memory_repo):
        """Test deleting a memory."""
        memory_id = memory_repo.add_chat_memory(123, "To be deleted")

        deleted = memory_repo.delete_memory("chat", 123, memory_id)
        assert deleted is True

        memories = memory_repo.get_chat_memories(123)
        assert len(memories) == 0

    def test_update_memory(self, memory_repo):
        """Test updating a memory."""
        memory_id = memory_repo.add_chat_memory(123, "Old content", ["old"])

        updated = memory_repo.update_memory(
            scope="chat", scope_id=123, memory_id=memory_id, content="New content", tags=["new"]
        )
        assert updated is True

        memories = memory_repo.get_chat_memories(123)
        assert len(memories) == 1
        assert memories[0]["content"] == "New content"
        assert memories[0]["tags"] == ["new"]
        assert "updated_at" in memories[0]

    def test_scope_isolation(self, memory_repo):
        """Test that memory scopes (chat/user) are isolated."""
        memory_repo.add_chat_memory(100, "Chat content")
        memory_repo.add_user_memory(100, "User content")  # Same ID but different scope

        chat_memories = memory_repo.get_chat_memories(100)
        user_memories = memory_repo.get_user_memories(100)

        assert len(chat_memories) == 1
        assert chat_memories[0]["content"] == "Chat content"

        assert len(user_memories) == 1
        assert user_memories[0]["content"] == "User content"

    def test_search_and_delete(self, memory_repo):
        """Test search and delete."""
        memory_repo.add_chat_memory(123, "Delete me please")

        deleted_item = memory_repo.search_and_delete("chat", 123, "Delete me")
        assert deleted_item is not None
        assert deleted_item["content"] == "Delete me please"

        memories = memory_repo.get_chat_memories(123)
        assert len(memories) == 0
