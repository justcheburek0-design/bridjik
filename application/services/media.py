"""Media handling service."""
import logging
import re
import asyncio
import mimetypes
import uuid
import random
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse, unquote
from aiogram import types, Bot
from aiogram.types import FSInputFile, BufferedInputFile
import httpx

from core.config import Config
from domain.interfaces import IGuessesRepository


logger = logging.getLogger(__name__)


# Media tag regex
MEDIA_TAG_RE = re.compile(r"\[\[(photo|sticker|kb|guess):([^\]]+)\]\]", re.IGNORECASE)

_MAX_IMAGE_BYTES = 9.5 * 1024 * 1024
_IMAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
_IMAGE_TIMEOUT = httpx.Timeout(15.0, connect=10.0, read=15.0)
_ALLOWED_IMAGE_EXTS = {".jpg", ".png", ".gif", ".webp"}
_IMAGE_RESULT_ATTEMPTS = 3
_PIXABAY_API_URL = "https://pixabay.com/api/"
_PIXABAY_LANG = "ru"


class MediaService:
    """Service for handling media (images, voice, etc.)."""
    
    def __init__(self, bot: Bot, bot_token: str, config: Config, guesses_repo: Optional[IGuessesRepository] = None):
        self.bot = bot
        self.bot_token = bot_token
        self.config = config
        self.guesses_repo = guesses_repo
    
    async def download_image(self, message: types.Message) -> Optional[tuple[bytes, str]]:
        """Download image from message. Returns (bytes, mime_type) or None."""
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                mime = "image/jpeg"
            elif message.document:
                file_id = message.document.file_id
                mime = message.document.mime_type or "image/jpeg"
            else:
                return None
            
            fobj = await self.bot.get_file(file_id)
            file_path = getattr(fobj, "file_path", None)
            if not file_path:
                raise RuntimeError("missing file_path")
            
            url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            timeout = httpx.Timeout(20.0, connect=10.0, read=20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return (resp.content, mime)
        except Exception:
            logger.exception("Failed to download image")
            return None
    
    async def download_voice(self, message: types.Message) -> Optional[tuple[bytes, str]]:
        """Download voice from message. Returns (bytes, mime_type) or None."""
        try:
            if not message.voice:
                return None
            
            file_id = message.voice.file_id
            mime = getattr(message.voice, "mime_type", None) or "audio/ogg"
            
            fobj = await self.bot.get_file(file_id)
            file_path = getattr(fobj, "file_path", None)
            if not file_path:
                raise RuntimeError("missing voice file_path")
            
            url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            timeout = httpx.Timeout(30.0, connect=10.0, read=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return (resp.content, mime)
        except Exception:
            logger.exception("Failed to download voice")
            return None
    
    async def send_typing_action(self, chat_id: int) -> None:
        """Send typing action."""
        try:
            await self.bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
    
    def _find_photo_file(self, name: str) -> Optional[Path]:
        """Find local file in photos directory by base name."""
        base = (name or "").strip()
        base = re.sub(r"[\\/]+", "", base)
        photos_dir = Path("photos")
        if not photos_dir.exists():
            return None
        exts = ["jpg", "jpeg", "png", "webp", "gif"]
        for ext in exts:
            p = photos_dir / f"{base}.{ext}"
            if p.exists():
                return p
        try:
            for p in photos_dir.iterdir():
                if p.is_file() and p.stem.lower() == base.lower():
                    return p
        except Exception:
            pass
        return None
    
    def _normalise_ext(self, ext: Optional[str]) -> str:
        """Normalize image extension to supported format."""
        if not ext:
            return ""
        ext = ext.lower()
        if ext in {".jpeg", ".jpe"}:
            return ".jpg"
        if ext in {".jfif"}:
            return ".jpg"
        if ext in {".bmp"}:
            return ".jpg"
        return ext
    
    def _guess_image_extension(self, url: str, content_type: Optional[str]) -> str:
        """Try to determine correct image extension by MIME and URL."""
        primary = (content_type or "").split(";")[0].strip().lower()
        ext = ""
        if primary:
            ext = mimetypes.guess_extension(primary) or ""
        if not ext:
            path = unquote(urlparse(url).path)
            ext = Path(path).suffix
        ext = self._normalise_ext(ext)
        if not ext or ext not in _ALLOWED_IMAGE_EXTS:
            return ".jpg"
        return ext
    
    def _build_image_filename(self, query: str, url: str, content_type: Optional[str]) -> str:
        """Build safe filename for saving image."""
        ext = self._guess_image_extension(url, content_type)
        base = re.sub(r"[^a-z0-9_-]+", "_", (query or "image").strip().lower())
        base = base.strip("_") or "image"
        return f"{base}_{uuid.uuid4().hex[:8]}{ext}"
    
    async def _fetch_pixabay_hits(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        """Request search results from Pixabay by query."""
        api_key = (self.config.PIXABAY_API_KEY or "").strip()
        if not api_key:
            logger.warning("image search skipped for %s: missing PIXABAY_API_KEY", query)
            return []
        
        params = {
            "key": api_key,
            "q": query,
            "lang": _PIXABAY_LANG,
            "image_type": "photo",
            "safesearch": "true",
            "per_page": 50,
            "order": "popular",
        }
        try:
            resp = await client.get(_PIXABAY_API_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("image search results failed for %s: %s", query, exc)
            return []
        except Exception as exc:
            logger.warning("image search results failed for %s: %s", query, exc)
            return []
        
        data = resp.json()
        hits = data.get("hits")
        if not isinstance(hits, list):
            logger.debug("image search: unexpected response payload for %s", query)
            return []
        return hits
    
    def _is_url(self, s: str) -> bool:
        """Check if string looks like URL (http/https)."""
        s = (s or "").strip().lower()
        return s.startswith("http://") or s.startswith("https://")
    
    async def _search_image_online(self, query: str) -> Optional[BufferedInputFile]:
        """Search and download image from Pixabay."""
        q = (query or "").strip()
        if not q:
            return None
        api_key = (self.config.PIXABAY_API_KEY or "").strip()
        if not api_key:
            logger.warning("image search skipped for %s: missing PIXABAY_API_KEY", q)
            return None
        try:
            async with httpx.AsyncClient(headers=_IMAGE_HEADERS, timeout=_IMAGE_TIMEOUT, follow_redirects=True) as client:
                for attempt in range(_IMAGE_RESULT_ATTEMPTS):
                    hits = await self._fetch_pixabay_hits(client, q)
                    if not hits:
                        if attempt < _IMAGE_RESULT_ATTEMPTS - 1:
                            await asyncio.sleep(0.5 + attempt * 0.5)
                            continue
                        return None
                    random.shuffle(hits)
                    for item in hits:
                        image_url = (
                            item.get("largeImageURL")
                            or item.get("fullHDURL")
                            or item.get("imageURL")
                            or item.get("webformatURL")
                            or item.get("previewURL")
                        )
                        if not image_url:
                            continue
                        declared_size = item.get("imageSize")
                        if declared_size:
                            try:
                                if int(declared_size) > _MAX_IMAGE_BYTES:
                                    logger.debug("image search: skip %s (declared size %s bytes)", image_url, declared_size)
                                    continue
                            except (TypeError, ValueError):
                                pass
                        try:
                            img_resp = await client.get(image_url, headers=_IMAGE_HEADERS)
                            img_resp.raise_for_status()
                            content = img_resp.content
                            if not content:
                                continue
                            if len(content) > _MAX_IMAGE_BYTES:
                                logger.debug("image search: skip %s (downloaded %d bytes)", image_url, len(content))
                                continue
                            filename = self._build_image_filename(q, image_url, img_resp.headers.get("Content-Type"))
                            return BufferedInputFile(content, filename=filename)
                        except Exception as exc:
                            logger.debug("image search download failed for %s: %s", image_url, exc)
                            continue
                    if attempt < _IMAGE_RESULT_ATTEMPTS - 1:
                        await asyncio.sleep(0.5 + attempt * 0.5)
            return None
        except Exception:
            logger.exception("image search failed for query: %s", q)
        return None
    
    async def _resolve_photo_payload(self, payload: str) -> Optional[Union[str, FSInputFile, BufferedInputFile]]:
        """Convert [[photo:...]] placeholder to URL or file for sending."""
        target = (payload or "").strip()
        if not target:
            return None
        if self._is_url(target):
            return target
        path = self._find_photo_file(target)
        if path is not None:
            return FSInputFile(str(path))
        return await self._search_image_online(target)
    
    async def _resolve_sticker_payload(self, payload: str, chat_id: int) -> Optional[str]:
        """Resolve sticker payload: last/alias/file_id -> file_id."""
        p = (payload or "").strip()
        if not p:
            return None
        if isinstance(getattr(self.config, "STICKERS", None), dict):
            if p in self.config.STICKERS:
                return self.config.STICKERS[p]
        return p
    
    def _parse_keyboard_payload(self, payload: str) -> Optional[types.InlineKeyboardMarkup]:
        """Parse [[kb:...]] payload into InlineKeyboardMarkup."""
        s = (payload or "").strip()
        if not s:
            return None
        rows: list[list[types.InlineKeyboardButton]] = []
        for row_str in re.split(r"\s*;\s*", s):
            if not row_str:
                continue
            buttons: list[types.InlineKeyboardButton] = []
            for btn_str in [b for b in re.split(r"\s*,\s*", row_str) if b]:
                if "|" in btn_str:
                    text, action = btn_str.split("|", 1)
                else:
                    continue
                text = text.strip()
                action = action.strip()
                if not text or not action:
                    continue
                buttons.append(types.InlineKeyboardButton(text=text, url=action))
            if buttons:
                rows.append(buttons)
        if not rows:
            return None
        return types.InlineKeyboardMarkup(inline_keyboard=rows)
    
    async def long_text(self, msg: types.Message, user_msg: types.Message, text: str):
        """Send long text in parts with embedded photos by [[photo:...]] tags."""
        CHUNK = 4000
        if text is None:
            text = ""
        
        actions: list[tuple[str, str]] = []
        pos = 0
        for m in MEDIA_TAG_RE.finditer(text):
            if m.start() > pos:
                actions.append(("text", text[pos:m.start()]))
            kind = m.group(1).lower()
            payload = m.group(2)
            if kind == "photo":
                actions.append(("photo", payload))
            elif kind == "sticker":
                actions.append(("sticker", payload))
            elif kind == "kb":
                actions.append(("kb", payload))
            elif kind == "guess":
                actions.append(("guess", payload))
            pos = m.end()
        if pos < len(text):
            actions.append(("text", text[pos:]))
        
        sent_any_text = False
        last_text_msg: Optional[types.Message] = None
        pending_kb: Optional[types.InlineKeyboardMarkup] = None
        
        async def send_text_blocks(s: str, first_edit: bool):
            nonlocal sent_any_text, last_text_msg, pending_kb
            s = s.strip()
            if not s:
                return
            parts = [s[i:i + CHUNK] for i in range(0, len(s), CHUNK)]
            if first_edit:
                try:
                    if pending_kb is not None:
                        last_text_msg = await msg.edit_text(parts[0], reply_markup=pending_kb)
                        pending_kb = None
                    else:
                        last_text_msg = await msg.edit_text(parts[0])
                    sent_any_text = True
                except Exception:
                    logger.exception("failed to edit initial message with text")
                    last_text_msg = await user_msg.answer(parts[0])
                    if pending_kb is not None:
                        try:
                            await last_text_msg.edit_reply_markup(reply_markup=pending_kb)
                        except Exception:
                            logger.exception("failed to set pending keyboard on fallback message")
                        pending_kb = None
                    sent_any_text = True
                for part in parts[1:]:
                    last_text_msg = await user_msg.answer(part)
            else:
                for part in parts:
                    last_text_msg = await user_msg.answer(part)
                    sent_any_text = True
        
        first_text_pending = True
        for kind, payload in actions:
            if kind == "text":
                await send_text_blocks(payload, first_edit=first_text_pending)
                if first_text_pending and payload.strip():
                    first_text_pending = False
            elif kind == "photo":
                photo_arg = await self._resolve_photo_payload(payload)
                if photo_arg is None:
                    logger.warning("photo not found or unsupported: %s", payload)
                    continue
                try:
                    await user_msg.answer_photo(photo=photo_arg)
                except Exception:
                    logger.exception("failed to send photo: %s", payload)
            elif kind == "sticker":
                sticker_id = await self._resolve_sticker_payload(payload, user_msg.chat.id)
                if not sticker_id:
                    logger.warning("sticker not found or unsupported: %s", payload)
                    continue
                try:
                    await user_msg.answer_sticker(sticker=sticker_id)
                except Exception:
                    logger.exception("failed to send sticker: %s", payload)
            elif kind == "kb":
                kb = self._parse_keyboard_payload(payload)
                if not kb:
                    logger.warning("keyboard payload invalid: %s", payload)
                    continue
                try:
                    if last_text_msg is not None:
                        await last_text_msg.edit_reply_markup(reply_markup=kb)
                    else:
                        pending_kb = kb
                except Exception:
                    logger.exception("failed to set reply markup (keyboard)")
            elif kind == "guess":
                try:
                    chat_id = user_msg.chat.id
                    pl = (payload or "").strip()
                    if self.guesses_repo:
                        if pl.lower() in ("forgot", "forget", "stop"):
                            self.guesses_repo.clear_guess(chat_id)
                        else:
                            self.guesses_repo.set_guess(chat_id, pl)
                except Exception:
                    logger.exception("failed to process [[guess:...]] tag")
        
        if first_text_pending:
            try:
                await msg.delete()
            except Exception:
                pass

