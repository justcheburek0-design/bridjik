import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from application.services.reminders import ReminderService


def message(uid=11, chat=-123):
    return SimpleNamespace(chat=SimpleNamespace(id=chat), from_user=SimpleNamespace(id=uid), message_thread_id=8, message_id=100)


class RemindersTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.service = ReminderService(Path(self.temp.name)/'reminders.sqlite3', self.bot)
        self.when = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()

    async def asyncTearDown(self):
        self.temp.cleanup()

    def create(self, text='test <b>'):
        return self.service.create(message(), text, self.when)

    async def test_persistence_scope_cancel_and_dedupe(self):
        self.assertIn('#1', self.create())
        self.assertIn('уже создано', self.create())
        service = ReminderService(self.service.path, self.bot)
        self.assertIn('Europe/Moscow', service.listing(message()))
        self.assertNotIn('#1', service.listing(message(uid=12)))
        self.assertIn('не найдено', service.cancel(message(uid=12), 1))
        self.assertIn('не найдено', service.cancel(message(chat=-124), 1))
        self.assertIn('отменено', service.cancel(message(), 1))
        await service.tick()
        self.bot.send_message.assert_not_awaited()

    async def test_validation_timezone(self):
        for when, zone in [('invalid','Europe/Moscow'),(self.when,'invalid'),('2020-01-01','Europe/Moscow'),('2027-03-28T02:30:00','Europe/Berlin')]:
            self.assertIn('Ошибка', self.service.create(message(),'test',when,zone))
        self.assertIn('Ошибка', self.service.create(message(),'',self.when))
        self.assertIn('Asia/Vladivostok', self.service.create(message(), 'local', self.when, 'Asia/Vladivostok'))
        self.assertIn('+0300', self.service.create(message(), 'naive', (datetime.now()+timedelta(days=1)).isoformat()))

    async def test_delivery_and_no_duplicate(self):
        self.create()
        with self.service.connect() as db:
            db.execute('UPDATE reminders SET due=?',(time.time()-10,))
        await self.service.tick()
        self.bot.send_message.assert_awaited_once()
        args = self.bot.send_message.call_args.kwargs
        self.assertEqual(args['message_thread_id'],8)
        self.assertIn('&lt;b&gt;', args['text'])
        self.assertIn('tg://user?id=11',args['text'])
        await self.service.tick()
        self.bot.send_message.assert_awaited_once()

    async def test_retry_and_permanent_failure(self):
        self.create()
        with self.service.connect() as db:
            db.execute('UPDATE reminders SET due=?',(time.time()-1,))
        self.bot.send_message.side_effect = TelegramRetryAfter(method=SendMessage(chat_id=-123,text='x'),message='retry',retry_after=10)
        await self.service.tick()
        with self.service.connect() as db:
            row=db.execute('SELECT * FROM reminders').fetchone()
            self.assertGreater(row['next_try'],time.time())
            self.assertEqual(row['status'],'active')
            db.execute('UPDATE reminders SET next_try=0')
        self.bot.send_message.side_effect = TelegramForbiddenError(method=SendMessage(chat_id=-123,text='x'),message='blocked')
        await self.service.tick()
        with self.service.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM reminders').fetchone()[0],'failed')


if __name__ == '__main__':
    unittest.main()
