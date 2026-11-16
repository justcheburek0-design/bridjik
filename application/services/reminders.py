"""Persistent, owner-scoped reminders and Telegram delivery worker."""
from __future__ import annotations

import asyncio
import html
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

log = logging.getLogger(__name__)


class ReminderService:
    def __init__(self, path: Path, bot):
        self.path = path
        self.bot = bot
        self.generate = None
        self._preparing = {}
        self._generation_slots = asyncio.Semaphore(4)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                thread_id INTEGER, text TEXT NOT NULL, due REAL NOT NULL, zone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', attempts INTEGER NOT NULL DEFAULT 0,
                next_try REAL NOT NULL DEFAULT 0, error TEXT, source_id INTEGER NOT NULL,
                UNIQUE(chat_id, user_id, source_id, text, due))""")
            columns = {r[1] for r in db.execute("PRAGMA table_info(reminders)")}
            for name, definition in {"use_ai": "INTEGER NOT NULL DEFAULT 1", "prepared": "TEXT", "initial_ai": "INTEGER NOT NULL DEFAULT 0", "followup_sent": "INTEGER NOT NULL DEFAULT 0"}.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE reminders ADD COLUMN {name} {definition}")
            db.execute("CREATE INDEX IF NOT EXISTS reminders_due ON reminders(status, due, next_try)")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def create(self, message, text: str, when: str, zone: str = "Europe/Moscow", use_ai: bool = True) -> str:
        try:
            tz = ZoneInfo(zone)
            date = datetime.fromisoformat(when)
            if date.tzinfo is None:
                # Reject nonexistent/ambiguous local times rather than silently shifting them.
                a, b = date.replace(tzinfo=tz, fold=0), date.replace(tzinfo=tz, fold=1)
                if a.utcoffset() != b.utcoffset():
                    return "Ошибка: неоднозначное или несуществующее местное время. Укажи ISO-время с UTC-смещением."
                date = a
            due = date.timestamp()
        except (ValueError, ZoneInfoNotFoundError):
            return "Ошибка: нужны дата ISO 8601 и часовой пояс IANA, например Europe/Moscow."
        text = text.strip()
        if not text or len(text) > 2000:
            return "Ошибка: текст должен содержать от 1 до 2000 символов."
        if not time.time() < due <= time.time() + 366 * 86400:
            return "Ошибка: время должно быть в будущем, не дальше года."
        with self.connect() as db:
            existing = db.execute("SELECT id FROM reminders WHERE chat_id=? AND user_id=? AND source_id=? AND text=? AND due=?", (message.chat.id, message.from_user.id, message.message_id, text, due)).fetchone()
            if existing:
                return f"Напоминание #{existing['id']} уже создано."
            count = db.execute("SELECT count(*) FROM reminders WHERE user_id=? AND status='active'", (message.from_user.id,)).fetchone()[0]
            if count >= 50:
                return "Ошибка: лимит 50 активных напоминаний."
            cur = db.execute("INSERT INTO reminders(chat_id,user_id,thread_id,text,due,zone,source_id) VALUES(?,?,?,?,?,?,?)", (message.chat.id, message.from_user.id, message.message_thread_id, text, due, zone, message.message_id))
            rid = cur.lastrowid
            db.execute("UPDATE reminders SET use_ai=? WHERE id=?", (int(use_ai), rid))
        local = date.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S %z')
        return f"Создано напоминание #{rid}: {local} ({zone}), нейронка: {'да' if use_ai else 'нет'} — {text}"

    def listing(self, message) -> str:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM reminders WHERE chat_id=? AND user_id=? AND (status IN ('active','failed') OR (status='sent' AND use_ai=1 AND initial_ai=0 AND followup_sent=0)) ORDER BY due", (message.chat.id, message.from_user.id)).fetchall()
        return '\n'.join(f"#{r['id']} [{'ошибка доставки' if r['status'] == 'failed' else 'активно'}] — {datetime.fromtimestamp(r['due'], ZoneInfo(r['zone'])).strftime('%Y-%m-%d %H:%M %z')} ({r['zone']}, AI: {'да' if r['use_ai'] else 'нет'}): {r['text']}" for r in rows) or "Активных напоминаний в этом чате нет."

    def cancel(self, message, reminder_id: int) -> str:
        with self.connect() as db:
            cur = db.execute("UPDATE reminders SET status='cancelled' WHERE id=? AND chat_id=? AND user_id=? AND (status IN ('active','failed') OR (status='sent' AND use_ai=1 AND initial_ai=0 AND followup_sent=0))", (reminder_id, message.chat.id, message.from_user.id))
        return f"Напоминание #{reminder_id} отменено." if cur.rowcount else "Активное напоминание не найдено (можно отменять только свои в этом чате)."

    async def tick(self):
        self._preparing = {k: v for k, v in self._preparing.items() if not v.done()}
        now = time.time()
        with self.connect() as db:
            upcoming = db.execute("SELECT * FROM reminders WHERE (status='active' OR (status='sent' AND initial_ai=0 AND followup_sent=0)) AND use_ai=1 AND prepared IS NULL AND due<=? AND next_try<=?", (now + 30, now)).fetchall()
        for row in upcoming:
            if self.generate and row["id"] not in self._preparing:
                self._preparing[row["id"]] = asyncio.create_task(self.prepare(dict(row)))
        with self.connect() as db:
            rows = db.execute("SELECT * FROM reminders WHERE status='active' AND due<=? AND next_try<=? ORDER BY due LIMIT 20", (now, now)).fetchall()
            rows += db.execute("SELECT * FROM reminders WHERE status='sent' AND use_ai=1 AND initial_ai=0 AND followup_sent=0 AND prepared IS NOT NULL AND next_try<=? ORDER BY due LIMIT 20", (now,)).fetchall()
        for row in rows:
            # Recheck because another coroutine may cancel while previous sends await.
            with self.connect() as db:
                if not db.execute("SELECT 1 FROM reminders WHERE id=? AND status=?", (row['id'], row['status'])).fetchone():
                    continue
            try:
                await self.bot.send_message(
                    chat_id=row['chat_id'], message_thread_id=row['thread_id'],
                    text=f'⏰ <a href="tg://user?id={row["user_id"]}">Напоминание #{row["id"]}</a>\n{html.escape(row["prepared"] or row["text"])}',
                    parse_mode='HTML',
                )
            except TelegramRetryAfter as exc:
                self.retry(row, str(exc), exc.retry_after + 1)
            except (TelegramForbiddenError, TelegramBadRequest) as exc:
                with self.connect() as db:
                    db.execute("UPDATE reminders SET status='failed',error=? WHERE id=?", (str(exc)[:500], row['id']))
                log.warning('reminder.delivery_failed id=%s error=%s', row['id'], exc)
            except Exception as exc:
                self.retry(row, str(exc), min(3600, 30 * 2 ** min(row['attempts'], 7)))
                log.warning('reminder.delivery_retry id=%s error=%s', row['id'], exc)
            else:
                with self.connect() as db:
                    if row["status"] == "sent":
                        db.execute("UPDATE reminders SET followup_sent=1,error=NULL WHERE id=?", (row["id"],))
                    else:
                        db.execute("UPDATE reminders SET status='sent',error=NULL,initial_ai=? WHERE id=?", (int(bool(row["prepared"])), row["id"]))
                log.info('reminder.sent id=%s', row['id'])

    def retry(self, row, error, delay):
        with self.connect() as db:
            db.execute("UPDATE reminders SET attempts=attempts+1,next_try=?,error=? WHERE id=?", (time.time()+delay, error[:500], row['id']))

    async def prepare(self, row):
        try:
            if not self.generate:
                return
            async def generate():
                async with self._generation_slots:
                    return await self.generate(row)
            text = await asyncio.wait_for(generate(), timeout=180)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty generated reminder")
            with self.connect() as db:
                db.execute("UPDATE reminders SET prepared=? WHERE id=? AND status IN ('active','sent')", (text.strip()[:3000], row["id"]))
            log.info("reminder.prepared id=%s", row["id"])
        except asyncio.TimeoutError:
            self.generation_failed(row)
            log.warning("reminder.generation_timeout id=%s", row["id"])
        except Exception:
            self.generation_failed(row)
            log.exception("reminder.generation_failed id=%s", row["id"])

    def generation_failed(self, row):
        # Retain literal delivery; do not repeatedly invoke a failing provider.
        with self.connect() as db:
            db.execute("UPDATE reminders SET use_ai=0 WHERE id=?", (row["id"],))

    async def close(self):
        tasks = list(self._preparing.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception('reminder.worker_error')
            # Never send early; poll near deadlines without blocking on generation.
            with self.connect() as db:
                due = db.execute("SELECT MIN(due) FROM reminders WHERE status='active' AND next_try<=?", (time.time(),)).fetchone()[0]
            delay = 0.5 if due is None else min(0.5, max(0.01, due - time.time()))
            await asyncio.sleep(delay)
