"""Bounded read-only MTProto context with a local fallback.

Private/basic-group message IDs are account-wide: never return another peer's data.
"""
import asyncio
import logging
import time

from telethon import TelegramClient, functions, types, utils
from telethon.errors import FloodWaitError

from utils.time import timestamp_message

log = logging.getLogger(__name__)


class TelegramHistory:
    def __init__(self, config, local):
        self.config = config
        self.local = local
        self.client = None
        self.bot_id = None
        self.lock = asyncio.Lock()
        self.blocked_until = 0.0
        self.cache = {}

    async def start(self):
        if not self.config.TELEGRAM_API_ID or not self.config.TELEGRAM_API_HASH:
            log.warning('telegram_history.disabled: missing API credentials')
            return
        path = self.config.DATA_DIR / 'mtproto' / 'bot'
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.client = TelegramClient(
            str(path), self.config.TELEGRAM_API_ID, self.config.TELEGRAM_API_HASH,
            receive_updates=False, request_retries=0, flood_sleep_threshold=0,
            timeout=10,
        )
        try:
            await asyncio.wait_for(self.client.start(bot_token=self.config.BOT_TOKEN), 25)
            me = await self.client.get_me()
            if not me.bot or me.id != int(self.config.BOT_TOKEN.split(':')[0]):
                raise ValueError('MTProto session does not match configured bot')
            self.bot_id = me.id
            path.with_suffix('.session').chmod(0o600)
            log.info('telegram_history.connected bot_id=%s', me.id)
        except Exception:
            await self.close()
            log.exception('telegram_history.start_failed; using local fallback')

    async def close(self):
        client, self.client = self.client, None
        if client:
            try:
                await client.disconnect()
            except Exception as exc:
                log.warning('telegram_history.disconnect_failed error=%s', type(exc).__name__)

    async def recent(self, chat_id, limit=200, anchor_id=None):
        local = self.local.get_recent_messages(chat_id, limit)
        anchor = anchor_id or max((r[0] or 0 for r in local), default=0)
        cached = self.cache.get(chat_id)
        if cached and time.monotonic() - cached[0] < 15:
            merged = {r[0]: r for r in cached[1]}
            merged.update({r[0]: r for r in local})
            return [merged[mid] for mid in sorted(merged) if mid <= anchor][-limit:]
        if not self.client or not anchor or time.monotonic() < self.blocked_until:
            return local
        try:
            async with self.lock:
                if time.monotonic() < self.blocked_until:
                    return local
                rows = await asyncio.wait_for(self._fetch(chat_id, anchor, limit), 12)
            if not rows:
                raise ValueError('No accessible messages returned')
            # Keep local media/file IDs for existing features; remote text/date wins.
            cached = {r[0]: r for r in local}
            result = []
            for row in rows:
                old = cached.get(row[0])
                if old:
                    row = row[:4] + tuple(old[4:])
                result.append(row)
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[chat_id] = (time.monotonic(), result)
            log.info('telegram_history.remote chat_id=%s messages=%s', chat_id, len(result))
            return result
        except FloodWaitError as exc:
            self.blocked_until = time.monotonic() + exc.seconds
            log.warning('telegram_history.flood_wait seconds=%s', exc.seconds)
        except Exception as exc:
            log.warning('telegram_history.fallback chat_id=%s error=%s', chat_id, type(exc).__name__)
        return local

    async def _fetch(self, chat_id, anchor, limit):
        channel = None
        if str(chat_id).startswith('-100'):
            entity = await self.client.get_entity(types.PeerChannel(int(str(chat_id)[4:])))
            channel = types.InputChannel(entity.id, entity.access_hash)
        rows = {}
        # Bounded scan: gaps and account-wide DM IDs can require more than 200 IDs.
        for end in range(anchor, max(0, anchor - 2000), -100):
            ids = [types.InputMessageID(i) for i in range(max(1, end - 99), end + 1)]
            request = (functions.channels.GetMessagesRequest(channel, ids) if channel
                       else functions.messages.GetMessagesRequest(ids))
            response = await self.client(request)
            users = {u.id: u for u in response.users}
            for message in response.messages:
                if not isinstance(message, types.Message):
                    continue
                if utils.get_peer_id(message.peer_id) != chat_id:
                    continue
                sender_id = utils.get_peer_id(message.from_id) if message.from_id else None
                sender = users.get(sender_id)
                author = (' '.join(filter(None, [getattr(sender, 'first_name', None),
                                                getattr(sender, 'last_name', None)]))
                          or getattr(sender, 'username', None) or str(sender_id or chat_id))
                text = message.message or ('[медиа]' if message.media else '')
                rows[message.id] = (
                    message.id, author, sender_id == self.bot_id,
                    timestamp_message(text, message.date), None, None, None, {},
                )
            if len(rows) >= limit:
                break
        return [rows[mid] for mid in sorted(rows)[-limit:]]
