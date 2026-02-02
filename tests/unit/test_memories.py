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

    def test_add_memory(self, memory_repo):
        """Test adding a memory."""
        memory_id = memory_repo.add_memory(
            chat_id=123,
            category="user_facts",
            content="Test user fact",
            tags=["test", "user"],
            author_id=456,
        )

        assert memory_id is not None
        assert isinstance(memory_id, str)

        # Verify memory was added
        memories = memory_repo.get_all_memories(123)
        assert len(memories) == 1
        assert memories[0]["content"] == "Test user fact"
        assert memories[0]["category"] == "user_facts"
        assert memories[0]["tags"] == ["test", "user"]
        assert memories[0]["author_id"] == 456

    def test_add_multiple_memories(self, memory_repo):
        """Test adding multiple memories to same chat."""
        memory_repo.add_memory(123, "user_facts", "Fact 1", ["tag1"])
        memory_repo.add_memory(123, "events", "Event 1", ["tag2"])
        memory_repo.add_memory(123, "agreements", "Agreement 1", ["tag3"])

        memories = memory_repo.get_all_memories(123)
        assert len(memories) == 3

    def test_delete_memory(self, memory_repo):
        """Test deleting a memory by ID."""
        memory_id = memory_repo.add_memory(123, "user_facts", "Test fact")

        # Delete it
        deleted = memory_repo.delete_memory(123, memory_id)
        assert deleted is True

        # Verify it's gone
        memories = memory_repo.get_all_memories(123)
        assert len(memories) == 0

    def test_delete_nonexistent_memory(self, memory_repo):
        """Test deleting non-existent memory returns False."""
        deleted = memory_repo.delete_memory(123, "nonexistent-id")
        assert deleted is False

    def test_get_memories_by_category(self, memory_repo):
        """Test getting memories filtered by category."""
        memory_repo.add_memory(123, "user_facts", "Fact 1")
        memory_repo.add_memory(123, "user_facts", "Fact 2")
        memory_repo.add_memory(123, "events", "Event 1")

        user_facts = memory_repo.get_memories_by_category(123, "user_facts")
        assert len(user_facts) == 2

        events = memory_repo.get_memories_by_category(123, "events")
        assert len(events) == 1

    def test_search_memories_by_content(self, memory_repo):
        """Test searching memories by content."""
        memory_repo.add_memory(123, "user_facts", "User likes coding at night")
        memory_repo.add_memory(123, "events", "Night event happened")
        memory_repo.add_memory(123, "user_facts", "User prefers morning coffee")

        results = memory_repo.search_memories(123, "night")
        assert len(results) == 2

        results = memory_repo.search_memories(123, "coffee")
        assert len(results) == 1

    def test_search_memories_by_tags(self, memory_repo):
        """Test searching memories by tags."""
        memory_repo.add_memory(123, "user_facts", "Fact 1", tags=["python", "coding"])
        memory_repo.add_memory(123, "user_facts", "Fact 2", tags=["javascript"])
        memory_repo.add_memory(123, "events", "Event 1", tags=["python", "tutorial"])

        results = memory_repo.search_memories(123, "python")
        assert len(results) == 2

        results = memory_repo.search_memories(123, "javascript")
        assert len(results) == 1

    def test_search_and_delete(self, memory_repo):
        """Test search and delete functionality."""
        memory_repo.add_memory(123, "user_facts", "Delete this fact")
        memory_repo.add_memory(123, "user_facts", "Keep this fact")

        deleted = memory_repo.search_and_delete(123, "Delete")
        assert deleted is not None
        assert "Delete this fact" in deleted["content"]

        # Verify only one memory remains
        memories = memory_repo.get_all_memories(123)
        assert len(memories) == 1
        assert memories[0]["content"] == "Keep this fact"

    def test_search_and_delete_not_found(self, memory_repo):
        """Test search and delete when nothing matches."""
        memory_repo.add_memory(123, "user_facts", "Some fact")

        deleted = memory_repo.search_and_delete(123, "nonexistent")
        assert deleted is None

    def test_get_memory_categories(self, memory_repo):
        """Test getting memories grouped by category."""
        memory_repo.add_memory(123, "user_facts", "Fact 1")
        memory_repo.add_memory(123, "user_facts", "Fact 2")
        memory_repo.add_memory(123, "events", "Event 1")
        memory_repo.add_memory(123, "agreements", "Agreement 1")

        categories = memory_repo.get_memory_categories(123)

        assert "user_facts" in categories
        assert "events" in categories
        assert "agreements" in categories
        assert len(categories["user_facts"]) == 2
        assert len(categories["events"]) == 1
        assert len(categories["agreements"]) == 1

    def test_persistence(self, temp_memory_file):
        """Test that memories persist across repository instances."""
        # Create repo and add memory
        repo1 = MemoryRepository(temp_memory_file)
        memory_id = repo1.add_memory(123, "user_facts", "Persistent fact")

        # Create new repo instance with same file
        repo2 = MemoryRepository(temp_memory_file)
        memories = repo2.get_all_memories(123)

        assert len(memories) == 1
        assert memories[0]["content"] == "Persistent fact"
        assert memories[0]["id"] == memory_id

    def test_multiple_chats(self, memory_repo):
        """Test that memories are isolated per chat."""
        memory_repo.add_memory(123, "user_facts", "Chat 123 fact")
        memory_repo.add_memory(456, "user_facts", "Chat 456 fact")

        chat_123_memories = memory_repo.get_all_memories(123)
        chat_456_memories = memory_repo.get_all_memories(456)

        assert len(chat_123_memories) == 1
        assert len(chat_456_memories) == 1
        assert chat_123_memories[0]["content"] == "Chat 123 fact"
        assert chat_456_memories[0]["content"] == "Chat 456 fact"

    def test_empty_chat(self, memory_repo):
        """Test getting memories from chat with no memories."""
        memories = memory_repo.get_all_memories(999)
        assert memories == []

        categories = memory_repo.get_memory_categories(999)
        assert categories == {}

    def test_memory_metadata(self, memory_repo):
        """Test that memory includes proper metadata."""
        memory_id = memory_repo.add_memory(
            chat_id=123,
            category="user_facts",
            content="Test fact",
            tags=["test"],
            author_id=456,
            metadata={"priority": 8, "related_user_ids": [789]},
        )

        memories = memory_repo.get_all_memories(123)
        memory = memories[0]

        assert memory["id"] == memory_id
        assert memory["category"] == "user_facts"
        assert memory["content"] == "Test fact"
        assert memory["tags"] == ["test"]
        assert memory["author_id"] == 456
        assert "timestamp" in memory
        assert memory["metadata"]["priority"] == 8
        assert memory["metadata"]["related_user_ids"] == [789]
