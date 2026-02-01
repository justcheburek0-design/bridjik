from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.types import BufferedInputFile, FSInputFile

from application.services.media import MediaService


@pytest.fixture
def media_service():
    bot = AsyncMock()
    config = Mock()
    config.PIXABAY_API_KEY = "dummy_key"
    stickers_repo = Mock()

    service = MediaService(
        bot=bot, bot_token="dummy_token", config=config, stickers_repo=stickers_repo
    )
    return service


@pytest.mark.asyncio
async def test_resolve_photo_payload_url(media_service):
    """Test that _resolve_photo_payload returns the URL string if input is a URL."""
    url = "https://example.com/image.jpg"
    result = await media_service._resolve_photo_payload(url)
    assert result == url


@pytest.mark.asyncio
async def test_resolve_photo_payload_local_file(media_service):
    """Test that _resolve_photo_payload returns FSInputFile if input matches a local file."""
    # Mock _find_photo_file to return a path
    with patch.object(media_service, "_find_photo_file", return_value="photos/test.jpg"):
        result = await media_service._resolve_photo_payload("test")
        assert isinstance(result, FSInputFile)
        # Check path string since FSInputFile stores it differently depending on version,
        # but typically .path usually holds it.
        # In Aiogram 3.x: path is stored in .path
        assert str(result.path) == "photos/test.jpg"


@pytest.mark.asyncio
async def test_resolve_photo_payload_search(media_service):
    """Test that _resolve_photo_payload calls _search_image_online if not URL and not local file."""
    with patch.object(media_service, "_find_photo_file", return_value=None):
        with patch.object(
            media_service, "_search_image_online", new_callable=AsyncMock
        ) as mock_search:
            expected_result = BufferedInputFile(b"data", filename="test.jpg")
            mock_search.return_value = expected_result

            result = await media_service._resolve_photo_payload("query")
            assert result == expected_result
            mock_search.assert_awaited_once_with("query")
