"""Persistent per-chat semantic archive and throttled MTProto backfill."""
import asyncio
import json
import logging
import sqlite3
import time

import numpy as np
from fastembed import TextEmbedding
from telethon import functions, types, utils
from telethon.errors import FloodWaitError

from utils.time import timestamp_message

log = logging.getLogger(__name__)
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


class SearchArchive:
    def __init__(self, path, history, local):
        self.history, self.local = history, local
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS messages(
                chat INTEGER, id INTEGER, author TEXT, text TEXT, vector BLOB,
                PRIMARY KEY(chat,id));
            CREATE TABLE IF NOT EXISTS coverage(
                chat INTEGER PRIMARY KEY, cursor INTEGER, scanned INTEGER DEFAULT 0);
        ''')
        self.model = None
        self.busy = asyncio.Lock()
        self.retry_at = 0

    async def initialize(self):
        self.model = await asyncio.to_thread(
            TextEmbedding, model_name=MODEL,
            cache_dir=str(self.history.config.DATA_DIR / 'embedding-models'), threads=2)

    def seed(self):
        for chat, rows in self.local._logs.items():
            self.ingest(chat, rows)

    def ingest(self, chat, rows):
        ids = [r[0] for r in rows if r[0]]
        if not ids:
            return
        self.db.execute('INSERT OR IGNORE INTO coverage(chat,cursor) VALUES (?,?)', (chat, max(ids)))
        for r in rows:
            if not r[0] or not r[3]:
                continue
            self.db.execute('''INSERT INTO messages(chat,id,author,text) VALUES (?,?,?,?)
                ON CONFLICT(chat,id) DO UPDATE SET author=excluded.author,
                vector=CASE WHEN text=excluded.text THEN vector ELSE NULL END,text=excluded.text''',
                (chat, r[0], r[1], r[3]))
        self.db.commit()

    async def embed_pending(self):
        rows = self.db.execute('SELECT chat,id,text FROM messages WHERE vector IS NULL LIMIT 32').fetchall()
        if not rows:
            return
        async with self.busy:
            vectors = await asyncio.to_thread(lambda: list(self.model.embed(
                [r[2][:6000] for r in rows])))
        self.db.executemany('UPDATE messages SET vector=? WHERE chat=? AND id=?',
                            [(np.asarray(v, dtype=np.float32).tobytes(), r[0], r[1])
                             for r, v in zip(rows, vectors)])
        self.db.commit()

    async def search(self, chat, query, limit=8):
        if not query.strip():
            return {'error': 'Empty query'}
        if not self.model:
            return {'error': 'Search index is initializing'}
        async with self.busy:
            vector = await asyncio.to_thread(lambda: next(iter(self.model.embed([query[:2000]]))))
        # Stream rows to bound memory independently of total archive size.
        best = []
        for mid, author, text, blob in self.db.execute(
                'SELECT id,author,text,vector FROM messages WHERE chat=? AND vector IS NOT NULL', (chat,)):
            v = np.frombuffer(blob, dtype=np.float32)
            score = float(np.dot(v, vector) / max(float(np.linalg.norm(v)*np.linalg.norm(vector)), 1e-12))
            best.append((score, mid, author, text))
            best = sorted(best, reverse=True)[:max(1, min(limit, 15))]
        total, indexed, oldest = self.db.execute(
            'SELECT count(*),count(vector),min(id) FROM messages WHERE chat=?', (chat,)).fetchone()
        coverage = self.db.execute('SELECT cursor,scanned FROM coverage WHERE chat=?', (chat,)).fetchone()
        results = []
        for score, mid, author, text in best:
            link = f'https://t.me/c/{str(chat)[4:]}/{mid}' if str(chat).startswith('-100') else None
            neighbors = self.db.execute('SELECT id,author,text FROM messages WHERE chat=? AND id BETWEEN ? AND ? ORDER BY id',
                                        (chat, mid-2, mid+2)).fetchall()
            results.append(dict(message_id=mid, author=author, text=text[:3500], score=round(score, 4),
                                link=link, neighbors=[dict(message_id=i, author=a, text=t[:1000]) for i,a,t in neighbors]))
        return dict(results=results, stored=total, indexed=indexed, oldest_message_id=oldest,
                    next_scan_id=coverage[0] if coverage else None,
                    scanned_id_count=coverage[1] if coverage else 0,
                    coverage='Available messages only; ID gaps and inaccessible messages are not recoverable')

    async def backfill(self):
        h = self.history
        if not h.client or time.monotonic() < max(h.blocked_until, self.retry_at):
            return
        row = self.db.execute('SELECT chat,cursor FROM coverage WHERE cursor>0 ORDER BY scanned LIMIT 1').fetchone()
        if not row:
            return
        chat, cursor = row
        try:
            async with h.lock:
                ids = [types.InputMessageID(i) for i in range(max(1, cursor-99), cursor+1)]
                if str(chat).startswith('-100'):
                    entity = await h.client.get_entity(types.PeerChannel(int(str(chat)[4:])))
                    request = functions.channels.GetMessagesRequest(types.InputChannel(entity.id, entity.access_hash), ids)
                else:
                    request = functions.messages.GetMessagesRequest(ids)
                response = await asyncio.wait_for(h.client(request), 15)
            rows = []
            users = {u.id: u for u in response.users}
            for m in response.messages:
                if not isinstance(m, types.Message) or utils.get_peer_id(m.peer_id) != chat:
                    continue
                sender = utils.get_peer_id(m.from_id) if m.from_id else chat
                u = users.get(sender)
                author = getattr(u, 'first_name', None) or str(sender)
                rows.append((m.id, author, sender == h.bot_id,
                             timestamp_message(m.message or '[медиа]', m.date), None, None, None, {}))
            self.ingest(chat, rows)
            self.db.execute('UPDATE coverage SET cursor=?,scanned=scanned+? WHERE chat=?',
                            (max(0,cursor-100), len(ids), chat))
            self.db.commit()
        except FloodWaitError as exc:
            h.blocked_until = time.monotonic() + exc.seconds
            log.warning('search.backfill_flood_wait seconds=%s', exc.seconds)
        except Exception as exc:
            self.retry_at = time.monotonic() + 60
            log.warning('search.backfill_failed error=%s', type(exc).__name__)

    async def run(self):
        while True:
            try:
                if not self.model:
                    await self.initialize()
                self.seed()
                await self.embed_pending()
                await self.backfill()
            except Exception as exc:
                log.warning('search.worker_failed error=%s', type(exc).__name__)
            await asyncio.sleep(10)
