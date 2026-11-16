import asyncio
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from application.services.reminders import ReminderService


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.s = ReminderService(Path(self.tmp.name)/'r.db', self.bot)
        self.msg = SimpleNamespace(chat=SimpleNamespace(id=1),from_user=SimpleNamespace(id=2),message_thread_id=8,message_id=3)
        self.when = (datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat()

    async def asyncTearDown(self):
        await self.s.close()
        self.tmp.cleanup()

    def due(self):
        with self.s.connect() as db:
            db.execute('UPDATE reminders SET due=?',(time.time()-1,))

    async def test_early_waits(self):
        self.s.generate = AsyncMock(return_value='AI ready')
        self.s.create(self.msg,'reason',self.when)
        await self.s.tick()
        await asyncio.gather(*self.s._preparing.values())
        self.bot.send_message.assert_not_awaited()
        self.due()
        await self.s.tick()
        self.assertIn('AI ready',self.bot.send_message.call_args.kwargs['text'])
        await self.s.tick()
        self.bot.send_message.assert_awaited_once()

    async def test_late_continues_and_sends_followup(self):
        gate = asyncio.Event()
        async def generate(row):
            await gate.wait()
            return 'late AI'
        self.s.generate = generate
        self.s.create(self.msg,'reason',self.when)
        await self.s.tick()
        self.due()
        await self.s.tick()
        self.assertIn('reason',self.bot.send_message.call_args.kwargs['text'])
        self.assertFalse(next(iter(self.s._preparing.values())).done())
        gate.set()
        await asyncio.gather(*self.s._preparing.values())
        # Exercise persistence: next worker can deliver the prepared follow-up.
        restarted = ReminderService(self.s.path,self.bot)
        await restarted.tick()
        self.assertEqual(self.bot.send_message.await_count,2)
        self.assertIn('late AI',self.bot.send_message.call_args.kwargs['text'])
        await restarted.tick()
        self.assertEqual(self.bot.send_message.await_count,2)

    async def test_disabled_and_cancelled(self):
        self.s.generate = AsyncMock(return_value='AI')
        self.s.create(self.msg,'literal',self.when,use_ai=False)
        await self.s.tick()
        self.s.generate.assert_not_awaited()
        self.due()
        await self.s.tick()
        self.assertIn('literal',self.bot.send_message.call_args.kwargs['text'])

    async def test_cancel_while_preparing(self):
        gate = asyncio.Event()
        async def generate(row):
            await gate.wait()
            return 'AI'
        self.s.generate = generate
        self.s.create(self.msg,'reason',self.when)
        await self.s.tick()
        self.s.cancel(self.msg,1)
        gate.set()
        await asyncio.gather(*self.s._preparing.values())
        self.due()
        await self.s.tick()
        self.bot.send_message.assert_not_awaited()
