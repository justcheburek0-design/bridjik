import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from infrastructure.search_archive import SearchArchive


class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_date_and_failed_chat_does_not_block_others(self):
        from unittest.mock import AsyncMock
        import asyncio
        history = SimpleNamespace(client=AsyncMock(side_effect=ValueError('unavailable')),
                                  lock=asyncio.Lock(), blocked_until=0)
        with tempfile.TemporaryDirectory(dir='/root/.hermes/cache/scratch') as directory:
            archive = SearchArchive(Path(directory)/'test.sqlite3', history, None)
            archive.ingest(7, [(10, 'A', False, '[Время сообщения: 2020-01-02 03:04:05 МСК (UTC+03:00)] давно')])
            archive.ingest(8, [(11, 'B', True, 'bot')])
            self.assertEqual(archive.db.execute('SELECT sent_at FROM messages WHERE chat=7').fetchone()[0], '2020-01-02T03:04:05+03:00')
            await archive.backfill()
            await archive.backfill()
            self.assertEqual(history.client.await_count, 2)
            self.assertTrue(all(r[0] > 0 for r in archive.db.execute('SELECT retry_after FROM coverage')))
            archive.db.close()

    async def test_real_semantic_search_isolation_and_persistence(self):
        with tempfile.TemporaryDirectory(dir='/root/.hermes/cache/scratch') as directory:
            path = Path(directory) / 'search.sqlite3'
            history = SimpleNamespace(config=SimpleNamespace(DATA_DIR=Path('/srv/services/bridjik/data')))
            archive = SearchArchive(path, history, None)
            await archive.initialize()
            archive.ingest(7, [(1, 'A', False, 'Нужно оплатить аренду сервера завтра'),
                               (2, 'B', False, 'На ужин будет пицца')])
            archive.ingest(8, [(3, 'private', False, 'Оплата сервера')])
            await archive.embed_pending()
            result = await archive.search(7, 'платёж за хостинг')
            self.assertEqual(result['results'][0]['message_id'], 1)
            self.assertEqual(result['indexed'], 2)
            self.assertTrue(all(r['author'] != 'private' for r in result['results']))
            self.assertTrue(all(r['link'] is None for r in result['results']))
            archive.ingest(7, [(1, 'A', False, 'Обновлённое сообщение')])
            self.assertEqual(archive.db.execute('SELECT vector FROM messages WHERE chat=7 AND id=1').fetchone()[0], None)
            archive.db.close()
            reopened = SearchArchive(path, history, None)
            self.assertEqual(reopened.db.execute('SELECT count(*) FROM messages').fetchone()[0], 3)
            reopened.db.close()
