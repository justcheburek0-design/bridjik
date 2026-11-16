import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telethon import types
from telethon.errors import FloodWaitError

from infrastructure.telegram_history import TelegramHistory


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        row = (10, 'local', False, 'cached', b'image', 'image/jpeg', 'file', {})
        local = SimpleNamespace(get_recent_messages=lambda *args: [row])
        service = TelegramHistory(SimpleNamespace(), local)
        service.bot_id = 99
        return service

    def message(self, mid, peer):
        return types.Message(id=mid, peer_id=types.PeerUser(peer),
                             from_id=types.PeerUser(peer),
                             date=datetime.now(timezone.utc), message='text')

    async def test_private_peer_isolation(self):
        service = self.service()
        service.client = AsyncMock(return_value=SimpleNamespace(
            users=[], messages=[self.message(10, 7), self.message(9, 8)]))
        rows = await service._fetch(7, 10, 200)
        self.assertEqual([r[0] for r in rows], [10])
        self.assertEqual(len(rows[0]), 8)
        self.assertIn('МСК', rows[0][3])

    async def test_remote_preserves_cached_media(self):
        service = self.service()
        service.client = object()
        service._fetch = AsyncMock(return_value=[(10, 'remote', False, 'fresh', None, None, None, {})])
        rows = await service.recent(7)
        self.assertEqual(rows[0][3], 'fresh')
        self.assertEqual(rows[0][4:7], (b'image', 'image/jpeg', 'file'))

    async def test_failure_and_empty_fallback(self):
        service = self.service()
        service.client = object()
        service._fetch = AsyncMock(side_effect=RuntimeError('offline'))
        self.assertEqual((await service.recent(7))[0][3], 'cached')
        service._fetch = AsyncMock(return_value=[])
        self.assertEqual((await service.recent(7))[0][3], 'cached')

    async def test_flood_wait_backoff(self):
        service = self.service()
        service.client = object()
        service._fetch = AsyncMock(side_effect=FloodWaitError(request=None, capture=30))
        await service.recent(7)
        await service.recent(7)
        self.assertEqual(service._fetch.await_count, 1)

    async def test_scan_bounded_and_ordered(self):
        service = self.service()
        service.client = AsyncMock(return_value=SimpleNamespace(users=[], messages=[]))
        self.assertEqual(await service._fetch(7, 10000, 200), [])
        self.assertEqual(service.client.await_count, 20)
