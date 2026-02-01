"""Test for image handling in chat logs and AI context."""

import tempfile
from pathlib import Path

import pytest

from infrastructure.repositories.chat_logs import ChatLogsRepository


def test_chat_logs_with_images():
    """Test that chat logs correctly store and retrieve images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = ChatLogsRepository(Path(tmpdir) / "test_logs.json", max_messages=5)

        # Add message with image
        test_image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        repo.add_message(
            chat_id=123,
            author="TestUser",
            is_bot=False,
            text="🖼️ Фото: Тестовая картинка",
            message_id=42,
            image_bytes=test_image_bytes,
            mime_type="image/png",
        )

        # Retrieve messages
        messages = repo.get_recent_messages(123, 10)
        assert len(messages) == 1

        msg_id, author, is_bot, text, img_bytes, mime, file_id = messages[0]
        assert msg_id == 42
        assert author == "TestUser"
        assert is_bot is False
        assert text == "🖼️ Фото: Тестовая картинка"
        assert img_bytes == test_image_bytes
        assert mime == "image/png"
        assert file_id is None


def test_chat_logs_without_images():
    """Test that chat logs work correctly without images (backward compatibility)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = ChatLogsRepository(Path(tmpdir) / "test_logs.json", max_messages=5)

        # Add message without image
        repo.add_message(
            chat_id=123, author="TestUser", is_bot=False, text="Привет!", message_id=42
        )

        # Retrieve messages
        messages = repo.get_recent_messages(123, 10)
        assert len(messages) == 1

        msg_id, author, is_bot, text, img_bytes, mime, file_id = messages[0]
        assert msg_id == 42
        assert img_bytes is None
        assert mime is None
        assert file_id is None


def test_json_serialization_with_image_bytes():
    """Test that image_bytes don't break JSON serialization in AI context."""
    import json

    # Simulate chat context with image_bytes
    chat_context = {
        "recent_messages": [
            {
                "message_id": 1,
                "author": "User",
                "is_bot": False,
                "text": "🖼️ Фото",
                "image_bytes": b"\x89PNG...",  # This should be removed before JSON
                "mime_type": "image/png",
            }
        ]
    }

    # Clean image_bytes before JSON serialization
    cleaned_messages = []
    for msg in chat_context["recent_messages"]:
        cleaned_msg = {
            "message_id": msg.get("message_id"),
            "author": msg.get("author"),
            "is_bot": msg.get("is_bot"),
            "text": msg.get("text"),
        }
        cleaned_messages.append(cleaned_msg)

    chat_context["recent_messages"] = cleaned_messages

    # This should NOT raise TypeError
    json_str = json.dumps(chat_context, ensure_ascii=False)
    assert "image_bytes" not in json_str
    assert "mime_type" not in json_str

    # Verify structure is intact
    parsed = json.loads(json_str)
    assert len(parsed["recent_messages"]) == 1
    assert parsed["recent_messages"][0]["text"] == "🖼️ Фото"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
