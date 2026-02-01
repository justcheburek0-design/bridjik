"""Media handling service."""

import asyncio
import logging
import mimetypes
import random
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional, Union
from urllib.parse import unquote, urlparse

import httpx
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, FSInputFile
from PIL import Image

from core.config import Config
from domain.interfaces import IGuessesRepository
from infrastructure.repositories.stickers import StickersRepository
from utils.markdown_to_html import markdown_to_telegram_html

logger = logging.getLogger(__name__)


# Media tag regex
MEDIA_TAG_RE = re.compile(
    r"\[(find_photo|gen_photo|sticker|kb|guess|voice):([^\]]+)\]", re.IGNORECASE
)

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

    def __init__(
        self,
        bot: Bot,
        bot_token: str,
        config: Config,
        stickers_repo: StickersRepository,
        guesses_repo: Optional[IGuessesRepository] = None,
        openai_client=None,
    ):
        self.bot = bot
        self.bot_token = bot_token
        self.config = config
        self.stickers_repo = stickers_repo
        self.guesses_repo = guesses_repo
        self.openai_client = openai_client

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

    async def download_sticker(self, message: types.Message) -> Optional[tuple[bytes, str]]:
        """Download sticker from message. Returns (bytes, mime_type) or None."""
        try:
            if not message.sticker:
                return None

            file_id = message.sticker.file_id
            mime = getattr(message.sticker, "mime_type", None) or "image/webp"

            # Check if sticker is animated (TGS format - JSON-based animation)
            is_animated = getattr(message.sticker, "is_animated", False)
            is_video = getattr(message.sticker, "is_video", False)

            fobj = await self.bot.get_file(file_id)
            file_path = getattr(fobj, "file_path", None)
            if not file_path:
                raise RuntimeError("missing sticker file_path")

            url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            timeout = httpx.Timeout(20.0, connect=10.0, read=20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content = resp.content

                # Handle video stickers by extracting first frame
                if is_video:
                    logger.info("Converting video sticker to image (extracting first frame)")
                    extracted = await self._extract_video_sticker_frame(content)
                    if extracted:
                        return (extracted, "image/png")
                    logger.warning("Failed to extract video sticker frame")
                    return None

                # Handle animated TGS stickers - they are JSON-based, try to convert
                if is_animated and mime == "application/gzip":
                    logger.info("Processing animated TGS sticker")
                    converted = await self._convert_tgs_to_image(content)
                    if converted:
                        return (converted, "image/png")
                    logger.warning("Failed to convert TGS sticker")
                    return None

                # Handle regular WebP stickers
                if mime == "image/webp":
                    converted = self._convert_webp_to_png(content)
                    if converted:
                        return (converted, "image/png")
                    logger.warning("Failed to convert WebP sticker to PNG")
                    return None

                # For other MIME types, try general image extraction
                logger.debug("Sticker has MIME type: %s, attempting extraction", mime)
                extracted = self._extract_gif_important_frame(content)
                if extracted:
                    return (extracted, "image/png")

                logger.warning("Could not process sticker with MIME type: %s", mime)
                return None
        except Exception:
            logger.exception("Failed to download sticker")
            return None

    async def download_animation(self, message: types.Message) -> Optional[tuple[bytes, str]]:
        """Download animation/GIF from message. Returns (bytes, mime_type) or None."""
        try:
            # Check for animation or video/mp4 document (GIFs sent as files)
            if message.animation:
                file_id = message.animation.file_id
                mime = getattr(message.animation, "mime_type", None) or "video/mp4"
            elif message.document:
                doc = message.document
                doc_mime = str(getattr(doc, "mime_type", "")).lower()
                filename = str(getattr(doc, "file_name", "")).lower()
                # Check if it's a video/gif document
                if doc_mime in ("video/mp4", "video/mpeg", "image/gif") or filename.endswith(
                    (".gif", ".mp4", ".webm")
                ):
                    file_id = doc.file_id
                    mime = doc_mime or "video/mp4"
                else:
                    return None
            else:
                return None

            fobj = await self.bot.get_file(file_id)
            file_path = getattr(fobj, "file_path", None)
            if not file_path:
                raise RuntimeError("missing animation file_path")

            url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            timeout = httpx.Timeout(30.0, connect=10.0, read=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content = resp.content

                # Try to extract important frame from any animation/video
                if mime == "image/gif":
                    # For GIF, extract middle frame for better representation
                    extracted = self._extract_gif_important_frame(content)
                    if extracted:
                        return (extracted, "image/png")
                    logger.warning("Failed to extract GIF frame, skipping")
                    return None
                elif mime.startswith("video/"):
                    # For video files (MP4, WebM, etc.), try to extract first frame
                    logger.info("Attempting to extract first frame from video animation")
                    extracted = await self._extract_video_sticker_frame(content)
                    if extracted:
                        return (extracted, "image/png")
                    logger.warning("Failed to extract video first frame, skipping")
                    return None

                # For other types, try to treat as image
                logger.debug(
                    "Animation has MIME type: %s, attempting general image extraction",
                    mime,
                )
                extracted = self._extract_gif_important_frame(content)
                if extracted:
                    return (extracted, "image/png")

                logger.warning("Could not process animation with MIME type: %s", mime)
                return None
        except Exception:
            logger.exception("Failed to download animation")
            return None

    async def _extract_sent_photo(
        self, message: types.Message
    ) -> tuple[Optional[bytes], Optional[str]]:
        """Extract image bytes from a photo message that bot sent.

        Args:
            message: Message with photo

        Returns:
            Tuple of (image_bytes, mime_type) or (None, None)
        """
        try:
            if not message.photo:
                return (None, None)

            # Get the largest photo size
            photo = message.photo[-1]
            file_id = photo.file_id

            fobj = await self.bot.get_file(file_id)
            file_path = getattr(fobj, "file_path", None)
            if not file_path:
                logger.warning("missing photo file_path")
                return (None, None)

            url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            timeout = httpx.Timeout(30.0, connect=10.0, read=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return (resp.content, "image/jpeg")
        except Exception:
            logger.exception("Failed to extract sent photo")
            return (None, None)

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

    def _convert_webp_to_png(self, webp_bytes: bytes) -> Optional[bytes]:
        """Convert WebP image to PNG bytes."""
        try:
            img = Image.open(BytesIO(webp_bytes))
            # Convert RGBA to RGB if needed for JPEG compatibility
            if img.mode in ("RGBA", "LA", "P"):
                # Create white background for transparent images
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = rgb_img

            output = BytesIO()
            img.save(output, format="PNG")
            return output.getvalue()
        except Exception as exc:
            logger.warning("Failed to convert WebP to PNG: %s", exc)
            return None

    def _extract_gif_important_frame(self, gif_bytes: bytes) -> Optional[bytes]:
        """Extract important frame (middle) from GIF/animation and convert to PNG."""
        try:
            # Check if it's a valid image file (TGS stickers are not valid images)
            if gif_bytes[:4] == b"\x00\x00\x00\x14ftypheic":
                logger.warning("Skipping HEIC format (not supported)")
                return None

            img = Image.open(BytesIO(gif_bytes))

            # Handle animated images
            if hasattr(img, "is_animated") and img.is_animated:
                # Get the middle frame for better representation
                try:
                    n_frames = getattr(img, "n_frames", 1)
                    middle_frame = n_frames // 2
                    logger.debug(
                        f"Extracting middle frame ({middle_frame}/{n_frames}) from animated image"
                    )
                    img.seek(middle_frame)
                except Exception as e:
                    logger.debug(f"Failed to seek middle frame, using first: {e}")
                    img.seek(0)

            # Convert to RGB for consistency
            if img.mode in ("RGBA", "LA", "P"):
                # Create white background for transparent images
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = rgb_img

            output = BytesIO()
            img.save(output, format="PNG")
            return output.getvalue()
        except Exception as exc:
            logger.warning("Failed to extract frame from animation: %s", exc)
            return None

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
            async with httpx.AsyncClient(
                headers=_IMAGE_HEADERS, timeout=_IMAGE_TIMEOUT, follow_redirects=True
            ) as client:
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
                                    logger.debug(
                                        "image search: skip %s (declared size %s bytes)",
                                        image_url,
                                        declared_size,
                                    )
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
                                logger.debug(
                                    "image search: skip %s (downloaded %d bytes)",
                                    image_url,
                                    len(content),
                                )
                                continue
                            filename = self._build_image_filename(
                                q, image_url, img_resp.headers.get("Content-Type")
                            )
                            return BufferedInputFile(content, filename=filename)
                        except Exception as exc:
                            logger.debug(
                                "image search download failed for %s: %s",
                                image_url,
                                exc,
                            )
                            continue
                    if attempt < _IMAGE_RESULT_ATTEMPTS - 1:
                        await asyncio.sleep(0.5 + attempt * 0.5)
            return None
        except Exception:
            logger.exception("image search failed for query: %s", q)
        return None

    async def generate_image_via_ai(self, prompt: str) -> Optional[BufferedInputFile]:
        """Generate image using AI model from IMAGE_MODEL config.

        Args:
            prompt: Text description of the image to generate

        Returns:
            BufferedInputFile with generated image or None on error
        """
        if not prompt or not prompt.strip():
            logger.warning("Empty prompt provided for image generation")
            return None

        if not self.openai_client:
            logger.error("OpenAI client not available for image generation")
            return None

        try:
            logger.info(f"Generating image with prompt: {prompt[:100]}")

            # Use chat completions for OpenRouter compatibility
            # According to OpenRouter docs, modalities should be a top-level parameter
            response = await self.openai_client.chat.completions.create(
                model=self.config.IMAGE_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt.strip(),
                    }
                ],
            )

            if not response.choices or len(response.choices) == 0:
                logger.error("No choices returned from AI")
                return None

            # Extract image from response
            message = response.choices[0].message

            # Check if message has images attribute
            image_bytes = None

            # Method 1: Check for images attribute (OpenRouter returns list of dicts)
            if hasattr(message, "images") and message.images:
                logger.info(f"Found images attribute with {len(message.images)} image(s)")
                image_data = message.images[0]  # This is a dict, not an object!

                # Access as dictionary
                if isinstance(image_data, dict) and "image_url" in image_data:
                    image_url_dict = image_data["image_url"]
                    if isinstance(image_url_dict, dict) and "url" in image_url_dict:
                        image_url = image_url_dict["url"]

                        # Check if it's base64 data URL
                        if image_url.startswith("data:"):
                            logger.info("Converting base64 data URL to bytes")
                            import base64

                            try:
                                # Format: data:image/jpeg;base64,<base64_data>
                                base64_data = image_url.split(",", 1)[1]
                                image_bytes = base64.b64decode(base64_data)
                                logger.info(
                                    f"Successfully decoded base64, size: {len(image_bytes)} bytes"
                                )
                            except Exception as e:
                                logger.error(f"Failed to decode base64: {e}")
                                return None
                        else:
                            # Regular URL - download
                            logger.info(f"Downloading from URL: {image_url[:100]}")
                            async with httpx.AsyncClient(timeout=_IMAGE_TIMEOUT) as client:
                                img_resp = await client.get(image_url)
                                img_resp.raise_for_status()
                                image_bytes = img_resp.content
                    else:
                        logger.error(f"Unexpected image_url structure: {image_url_dict}")
                        return None
                else:
                    logger.error(f"Unexpected image_data structure: {type(image_data)}")
                    return None

            # Method 2: Check content for markdown with URL or base64
            elif message.content:
                logger.info("Trying to extract from message.content")

                # Try markdown format first
                markdown_pattern = r"!\[.*?\]\((data:image/[^;]+;base64,[^\)]+)\)"
                matches = re.findall(markdown_pattern, message.content)

                if matches:
                    logger.info("Found base64 in markdown format")
                    import base64

                    try:
                        base64_data = matches[0].split(",", 1)[1]
                        image_bytes = base64.b64decode(base64_data)
                    except Exception as e:
                        logger.error(f"Failed to decode base64 from markdown: {e}")
                        return None
                else:
                    # Try to find URL in markdown
                    url_markdown_pattern = r"!\[.*?\]\((https?://[^\)]+)\)"
                    url_matches = re.findall(url_markdown_pattern, message.content)

                    if url_matches:
                        image_url = url_matches[0]
                        logger.info(f"Found URL in markdown: {image_url[:100]}")
                        async with httpx.AsyncClient(timeout=_IMAGE_TIMEOUT) as client:
                            img_resp = await client.get(image_url)
                            img_resp.raise_for_status()
                            image_bytes = img_resp.content

            if not image_bytes:
                logger.error("Could not extract image from response")
                logger.info(f"Message has images attr: {hasattr(message, 'images')}")
                logger.info(
                    f"Message content preview: {str(message.content)[:200] if message.content else 'None'}"
                )
                return None

            # Return as BufferedInputFile
            filename = f"generated_{uuid.uuid4().hex[:8]}.png"
            logger.info(f"Image extraction successful, size: {len(image_bytes)} bytes")
            return BufferedInputFile(image_bytes, filename=filename)

        except Exception as exc:
            logger.exception(f"Failed to generate image: {exc}")
            return None

    async def _resolve_photo_payload(
        self, payload: str
    ) -> Optional[Union[str, FSInputFile, BufferedInputFile]]:
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

        # Try to get from repository
        sticker_id = self.stickers_repo.get_sticker(p)
        if sticker_id:
            return sticker_id

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

    async def long_text(
        self,
        msg: types.Message,
        user_msg: types.Message,
        text: str,
        tts_callback: Optional[callable] = None,
    ) -> list[tuple[int, str]]:
        """Send long text in parts with embedded photos by [[photo:...]] tags.

        Returns list of (message_id, text_content) for all sent messages.
        """
        chunk_size = 4000
        if text is None:
            text = ""

        matches = list(MEDIA_TAG_RE.finditer(text))
        logger.info(f"Found {len(matches)} media tags")

        actions: list[tuple[str, str]] = []
        pos = 0
        for m in matches:
            if m.start() > pos:
                actions.append(("text", text[pos : m.start()]))
            kind = m.group(1).lower()
            payload = m.group(2)
            if kind == "find_photo":
                actions.append(("find_photo", payload))
            elif kind == "gen_photo":
                actions.append(("gen_photo", payload))
            elif kind == "sticker":
                actions.append(("sticker", payload))
            elif kind == "kb":
                actions.append(("kb", payload))
            elif kind == "guess":
                actions.append(("guess", payload))
            elif kind == "voice":
                actions.append(("voice", payload))
            pos = m.end()
        if pos < len(text):
            actions.append(("text", text[pos:]))

        sent_messages: list[tuple[int, str]] = []
        last_text_msg: Optional[types.Message] = None
        pending_kb: Optional[types.InlineKeyboardMarkup] = None

        async def send_text_blocks(s: str, first_edit: bool):
            nonlocal last_text_msg, pending_kb
            s = s.strip()
            if not s:
                return
            # Convert markdown to Telegram HTML
            s = markdown_to_telegram_html(s)
            parts = [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]

            async def safe_edit(text, reply_markup=None):
                try:
                    return await msg.edit_text(text, reply_markup=reply_markup)
                except TelegramBadRequest as e:
                    s_e = str(e)
                    if "can't parse entities" in s_e:
                        logger.warning("HTML parse error in edit, retrying with plain text")
                        return await msg.edit_text(text, reply_markup=reply_markup, parse_mode=None)
                    if "message is not modified" in s_e:
                        return msg
                    raise

            async def safe_answer(text, reply_markup=None):
                try:
                    return await user_msg.answer(text, reply_markup=reply_markup)
                except TelegramBadRequest as e:
                    if "can't parse entities" in str(e):
                        logger.warning("HTML parse error in answer, retrying with plain text")
                        return await user_msg.answer(
                            text, reply_markup=reply_markup, parse_mode=None
                        )
                    raise

            if first_edit:
                try:
                    if pending_kb is not None:
                        last_text_msg = await safe_edit(parts[0], reply_markup=pending_kb)
                        pending_kb = None
                    else:
                        last_text_msg = await safe_edit(parts[0])

                    if last_text_msg:
                        sent_messages.append((last_text_msg.message_id, parts[0], None, None))
                except Exception:
                    logger.exception("failed to edit initial message with text")
                    try:
                        last_text_msg = await safe_answer(parts[0])
                        if pending_kb is not None:
                            try:
                                await last_text_msg.edit_reply_markup(reply_markup=pending_kb)
                            except Exception:
                                logger.exception(
                                    "failed to set pending keyboard on fallback message"
                                )
                            pending_kb = None

                        if last_text_msg:
                            sent_messages.append((last_text_msg.message_id, parts[0], None, None))
                    except Exception:
                        logger.exception("failed to send fallback message")

            else:
                for part in parts:
                    try:
                        last_text_msg = await safe_answer(part)
                        if last_text_msg:
                            sent_messages.append((last_text_msg.message_id, part))
                    except Exception:
                        logger.exception("failed to send message part")

        first_text_pending = True
        for kind, payload in actions:
            if kind == "text":
                await send_text_blocks(payload, first_edit=first_text_pending)
                if first_text_pending and payload.strip():
                    first_text_pending = False
            elif kind == "find_photo":
                photo_arg = await self._resolve_photo_payload(payload)
                if photo_arg is None:
                    logger.warning("photo not found or unsupported: %s", payload)
                    continue
                try:
                    m = await user_msg.answer_photo(photo=photo_arg)
                    if m:
                        # Extract image bytes from sent photo
                        image_bytes, mime_type = await self._extract_sent_photo(m)
                        sent_messages.append(
                            (m.message_id, f"[find_photo:{payload}]", image_bytes, mime_type)
                        )
                except Exception as exc:
                    logger.warning(
                        "failed to send photo directly: %s. Trying manual download.", exc
                    )
                    # Fallback: if it was a URL, try to download valid image manually
                    if isinstance(photo_arg, str) and self._is_url(photo_arg):
                        try:
                            # Use existing online search helper which handles downloading
                            # But we need direct download from URL, not search
                            async with httpx.AsyncClient(
                                timeout=_IMAGE_TIMEOUT,
                                headers=_IMAGE_HEADERS,
                                follow_redirects=True,
                            ) as client:
                                resp = await client.get(photo_arg)
                                resp.raise_for_status()
                                content = resp.content
                                if content:
                                    filename = self._build_image_filename(
                                        "url_image", photo_arg, resp.headers.get("Content-Type")
                                    )
                                    fallback_file = BufferedInputFile(content, filename=filename)
                                    m_fallback = await user_msg.answer_photo(photo=fallback_file)
                                    if m_fallback:
                                        sent_messages.append(
                                            (
                                                m_fallback.message_id,
                                                f"[find_photo:{payload}]",
                                                content,
                                                "image/jpeg",
                                            )
                                        )
                                else:
                                    logger.warning("Empty content from fallback download")
                        except Exception as fb_exc:
                            logger.exception("fallback download failed for %s: %s", payload, fb_exc)
                    else:
                        logger.exception("failed to send photo: %s", payload)
            elif kind == "gen_photo":
                photo_arg = await self.generate_image_via_ai(payload)
                if photo_arg is None:
                    logger.warning("image generation failed: %s", payload)
                    continue
                try:
                    m = await user_msg.answer_photo(photo=photo_arg)
                    if m:
                        # Extract image bytes from sent photo
                        image_bytes, mime_type = await self._extract_sent_photo(m)
                        sent_messages.append(
                            (m.message_id, f"[gen_photo:{payload}]", image_bytes, mime_type)
                        )
                except Exception:
                    logger.exception("failed to send generated photo: %s", payload)
            elif kind == "sticker":
                sticker_id = await self._resolve_sticker_payload(payload, user_msg.chat.id)
                if not sticker_id:
                    logger.warning("sticker not found or unsupported: %s", payload)
                    continue
                try:
                    m = await user_msg.answer_sticker(sticker=sticker_id)
                    if m:
                        # Use sticker name from database for logging
                        sent_messages.append((m.message_id, f"[sticker:{payload}]", None, None))
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
            elif kind == "voice":
                if tts_callback:
                    try:
                        voice_text = (payload or "").strip()
                        if voice_text:
                            await self.send_typing_action(user_msg.chat.id)
                            voice_bytes = await tts_callback(voice_text)
                            if voice_bytes:
                                m = await user_msg.answer_voice(
                                    voice=BufferedInputFile(voice_bytes, filename="voice.mp3"),
                                    caption=None,
                                )
                                if m:
                                    sent_messages.append(
                                        (m.message_id, f"[Голосовое: {voice_text}]", None, None)
                                    )
                    except Exception:
                        logger.exception("failed to send voice message")

        if first_text_pending:
            try:
                await msg.delete()
            except Exception:
                pass

        return sent_messages

    async def _extract_video_sticker_frame(self, video_bytes: bytes) -> Optional[bytes]:
        """Extract first frame from video sticker."""
        try:
            import shutil
            import subprocess
            import tempfile

            # Check if ffmpeg is available
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                logger.warning("ffmpeg not found in PATH, attempting PIL extraction")
                # Try PIL as fallback for MP4 (some MP4 files can be read by PIL)
                try:
                    img = Image.open(BytesIO(video_bytes))
                    if img.mode in ("RGBA", "LA", "P"):
                        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "P":
                            img = img.convert("RGBA")
                        rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                        img = rgb_img

                    output = BytesIO()
                    img.save(output, format="PNG")
                    return output.getvalue()
                except Exception:
                    logger.debug("PIL extraction failed, video format not directly supported")
                    return None

            # Use ffmpeg to extract first frame
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
                tmp_video.write(video_bytes)
                tmp_video_path = tmp_video.name

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_frame:
                tmp_frame_path = tmp_frame.name

            try:
                # Run ffmpeg with additional error suppression
                result = subprocess.run(
                    [
                        ffmpeg_path,
                        "-y",
                        "-i",
                        tmp_video_path,
                        "-vframes",
                        "1",
                        "-q:v",
                        "2",
                        "-f",
                        "image2",
                        tmp_frame_path,
                    ],
                    capture_output=True,
                    timeout=15,
                    text=False,
                )

                if result.returncode == 0 and Path(tmp_frame_path).exists():
                    with open(tmp_frame_path, "rb") as f:
                        frame_bytes = f.read()
                    if frame_bytes:
                        logger.info("Successfully extracted video sticker frame")
                        return frame_bytes
                else:
                    logger.debug(
                        "ffmpeg extraction failed with return code %d",
                        result.returncode,
                    )
                    if result.stderr:
                        logger.debug(
                            "ffmpeg stderr: %s",
                            result.stderr.decode("utf-8", errors="ignore")[:200],
                        )
            except subprocess.TimeoutExpired:
                logger.warning("ffmpeg timeout while extracting frame")
            except Exception as exc:
                logger.warning("ffmpeg extraction error: %s", exc)
            finally:
                try:
                    Path(tmp_video_path).unlink()
                    Path(tmp_frame_path).unlink()
                except Exception:
                    pass

            return None
        except Exception as exc:
            logger.warning("Failed to extract video sticker frame: %s", exc)
            return None

    async def _convert_tgs_to_image(self, tgs_bytes: bytes) -> Optional[bytes]:
        """Convert TGS animated sticker to static image."""
        try:
            import gzip
            import json
            import tempfile

            # TGS files are gzipped JSON (Lottie format)
            try:
                decompressed = gzip.decompress(tgs_bytes)
                logger.debug(
                    "Successfully decompressed TGS sticker (%d bytes)",
                    len(decompressed),
                )
            except Exception as exc:
                logger.warning("Failed to decompress TGS: %s", exc)
                return None

            # Try to use rlottie for rendering (if available)
            rlottie_available = False
            try:
                from rlottie import LottieAnimation  # noqa: F401

                rlottie_available = True
            except ImportError:
                logger.info("rlottie library not available for TGS conversion")

            if rlottie_available:
                try:
                    from rlottie import LottieAnimation  # noqa: F811

                    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_json:
                        tmp_json.write(decompressed)
                        tmp_json_path = tmp_json.name

                    try:
                        # Render first frame
                        animation = LottieAnimation(tmp_json_path)
                        width, height = animation.size()

                        if width <= 0 or height <= 0:
                            logger.warning("Invalid animation size: %dx%d", width, height)
                            return None

                        # Render first frame to PNG
                        frame_buffer = animation.render_frame(0)

                        # Convert buffer to PIL Image
                        img = Image.frombytes("RGBA", (width, height), frame_buffer)

                        # Convert RGBA to RGB with white background
                        rgb_img = Image.new("RGB", (width, height), (255, 255, 255))
                        rgb_img.paste(img, mask=img.split()[-1])

                        output = BytesIO()
                        rgb_img.save(output, format="PNG")
                        logger.info("Successfully converted TGS sticker with rlottie")
                        return output.getvalue()
                    finally:
                        try:
                            Path(tmp_json_path).unlink()
                        except Exception:
                            pass
                except ImportError:
                    logger.info("rlottie not available for TGS conversion")
                except Exception as exc:
                    logger.warning("Failed to render TGS with rlottie: %s", exc)

            # Fallback: Try to create a placeholder from Lottie metadata
            try:
                data = json.loads(decompressed.decode("utf-8"))

                # Extract animation info from Lottie JSON
                width = int(data.get("w", 512))
                height = int(data.get("h", 512))

                # Ensure reasonable dimensions
                if width <= 0 or width > 4096:
                    width = 512
                if height <= 0 or height > 4096:
                    height = 512

                # Create a placeholder image with animation info
                img = Image.new("RGB", (width, height), (100, 100, 100))

                output = BytesIO()
                img.save(output, format="PNG")
                logger.info("Created placeholder PNG for TGS sticker (%dx%d)", width, height)
                return output.getvalue()
            except Exception as exc:
                logger.warning("Failed to create TGS placeholder: %s", exc)

            return None
        except Exception as exc:
            logger.warning("Failed to convert TGS sticker: %s", exc)
            return None
