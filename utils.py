# utils.py
from html import escape
import re
import hashlib
import logging
import json
from pathlib import Path
from typing import Tuple, Deque, Dict, List
from collections import defaultdict, deque
import time
from typing import Dict, Optional

from aiogram import types
from aiogram.enums import ChatType

import strings
import config
from bot_init import *

# ===== Per-user short history (диалоги пользователь↔ассистент) =====
HistoryKey = Tuple[int, int]  # (chat_id, user_id)
HISTORY: Dict[HistoryKey, Deque[Tuple[str, str]]] = defaultdict(
    lambda: deque(maxlen=config.DM_MAX_MESSAGES)
)

# ===== Guessing game memory (per chat) =====
# Store by chat only, so multiple users in a chat share the same guess state.
_GUESSES: dict[str, str] = {}  # key as chat_id (str) -> object

def _chat_key(key_or_chat: "HistoryKey | int") -> str:
    """Return canonical string key for chat-based storage.

    Accepts either a `(chat_id, user_id)` tuple (legacy calls) or an `int` chat_id.
    """
    try:
        if isinstance(key_or_chat, tuple):
            return str(int(key_or_chat[0]))
        return str(int(key_or_chat))
    except Exception:
        # Fallback to string; ensures we don't crash on odd inputs
        return str(key_or_chat)

def _save_guesses() -> None:
    try:
        config.GUESSES_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.GUESSES_FILE.write_text(
            json.dumps(_GUESSES, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    except Exception:
        logging.exception('Failed to save GUESSES to JSON')

def _load_guesses() -> None:
    try:
        if not config.GUESSES_FILE.exists():
            return
        raw = config.GUESSES_FILE.read_text(encoding='utf-8') or '{}'
        data = json.loads(raw)
        if isinstance(data, dict):
            _GUESSES.clear()
            for k, v in data.items():
                if not isinstance(v, str) or not v:
                    continue
                # Backward compat: previously keys were 'chat:user'.
                if isinstance(k, str) and ":" in k:
                    chat, _sep, _user = k.partition(":")
                    k = chat
                # Normalize to string chat id
                try:
                    chat_key = str(int(k))
                except Exception:
                    chat_key = str(k)
                _GUESSES[chat_key] = v
    except Exception:
        logging.exception('Failed to load GUESSES from JSON')

def set_user_guess(key_or_chat: "HistoryKey | int", obj: str) -> None:
    """Remember guessed object for a chat.

    Accepts either a `(chat_id, user_id)` tuple (legacy) or `chat_id` int.
    """
    _GUESSES[_chat_key(key_or_chat)] = (obj or '').strip()
    _save_guesses()

def get_user_guess(key_or_chat: "HistoryKey | int"):
    return _GUESSES.get(_chat_key(key_or_chat))

def clear_user_guess(key_or_chat: "HistoryKey | int") -> None:
    _GUESSES.pop(_chat_key(key_or_chat), None)
    _save_guesses()


# JSON-персист для HISTORY
def _hist_key_str(key: HistoryKey) -> str:
    return f"{key[0]}:{key[1]}"

def _hist_key_parse(s: str) -> Optional[HistoryKey]:
    try:
        a, b = str(s).split(":", 1)
        return (int(a), int(b))
    except Exception:
        return None

def _save_history() -> None:
    try:
        out: Dict[str, list[list[str]]] = {}
        for key, dq in HISTORY.items():
            out[_hist_key_str(key)] = [[role, msg] for role, msg in dq]
        # ensure dir exists
        path = config.HISTORY_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logging.exception("Failed to save HISTORY to JSON")

def _load_history() -> None:
    try:
        p = config.HISTORY_FILE
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
        for k, items in data.items():
            key = _hist_key_parse(k)
            if not key:
                continue
            dq: Deque[Tuple[str, str]] = deque(maxlen=config.DM_MAX_MESSAGES)
            for row in items:
                try:
                    role, msg = row
                    dq.append((str(role), _shorten(str(msg))))
                except Exception:
                    continue
            HISTORY[key] = dq
    except Exception:
        logging.exception("Failed to load HISTORY from JSON")

# ===== Per-chat raw history (последние сообщения чата) =====
# Храним только необходимые поля, чтобы не тащить целый Message.
# (author, is_bot, text)
ChatLine = Tuple[str, bool, str]
CHAT_LOGS: Dict[int, Deque[ChatLine]] = defaultdict(
    lambda: deque(maxlen=config.GROUP_MAX_MESSAGES)
)

# JSON-персист для CHAT_LOGS
def _save_chat_logs() -> None:
    try:
        out: Dict[str, list[list[object]]] = {}
        for chat_id, dq in CHAT_LOGS.items():
            out[str(chat_id)] = [[author, bool(is_bot), msg] for (author, is_bot, msg) in dq]
        path = config.CHAT_LOGS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logging.exception("Failed to save CHAT_LOGS to JSON")

def _load_chat_logs() -> None:
    try:
        p = config.CHAT_LOGS_FILE
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
        for k, items in data.items():
            try:
                chat_id = int(k)
            except Exception:
                continue
            dq: Deque[ChatLine] = deque(maxlen=config.GROUP_MAX_MESSAGES)
            for row in items:
                try:
                    author, is_bot, msg = row
                    dq.append((str(author), bool(is_bot), _shorten(str(msg))))
                except Exception:
                    continue
            CHAT_LOGS[chat_id] = dq
    except Exception:
        logging.exception("Failed to load CHAT_LOGS from JSON")


def _shorten(s: str, limit: int = 700) -> str:
    s = (s or "").strip()
    return (s[:limit] + "...") if len(s) > limit else s

def make_key(msg: types.Message) -> HistoryKey:
    return (msg.chat.id, msg.from_user.id)

def remember_user(key: HistoryKey, text: str) -> None:
    HISTORY[key].append(("user", _shorten(text)))
    _save_history()

def remember_assistant(key: HistoryKey, text: str) -> None:
    HISTORY[key].append(("assistant", _shorten(text)))
    _save_history()


def build_input_with_history(key: HistoryKey, user_text: str, name: str) -> str:
    lines: List[str] = []
    hist = HISTORY.get(key)
    if hist:
        lines.append(strings.text("history_header", limit=config.DM_MAX_MESSAGES))
        for role, text in hist:
            who = strings.text("history_user_label") if role == "user" else strings.text("history_assistant_label")
            lines.append(f"{who}: {text}")
        lines.append(strings.text("history_footer"))
    lines.append(strings.text("history_user_line", name=name, text=user_text))
    lines.append(strings.text("history_question_header"))
    return "\n".join(lines)

def _author_from(msg: types.Message) -> str:
    user = getattr(msg, "from_user", None)
    if not user:
        return "???"
    return (getattr(user, "username", None) or getattr(user, "first_name", "") or "???")

def save_incoming_message(message: types.Message, text: str) -> None:
    chat_id = message.chat.id
    author = _author_from(message)
    is_bot = bool(getattr(message.from_user, "is_bot", False))
    if not text:
        if message.photo:
            text = strings.text("log_photo", id=message.photo[-1].file_id)
        elif message.document:
            text = strings.text("log_document", id=message.document.file_id)
        elif message.voice:
            text = strings.text("log_voice", id=message.voice.file_id)
        elif message.video:
            text = strings.text("log_video", id=message.video.file_id)
        elif message.audio:
            text = strings.text("log_audio", id=message.audio.file_id)
        elif message.sticker:
            text = strings.text("log_sticker", emoji=(message.sticker.emoji or ""), id=message.sticker.file_id)
        else:
            return
    CHAT_LOGS[chat_id].append((author, is_bot, _shorten(text)))
    _save_chat_logs()
def save_outgoing_message(chat_id: int, text: str, bot_display_name: str = strings.text("assistant_display_name")) -> None:
    """Track what the bot answered so the transcript stays balanced."""
    if not text:
        return
    CHAT_LOGS[chat_id].append((bot_display_name, True, _shorten(text)))
    _save_chat_logs()


async def build_input_from_chat_thread(
    message: types.Message,
    user_text: str,
    name: str
) -> str:
    """Builds a short group-thread transcript for LLM context."""
    import strings as _strings
    lines: List[str] = []
    chat_id = message.chat.id
    thread: List[ChatLine] = list(CHAT_LOGS.get(chat_id, deque()))[-config.GROUP_MAX_MESSAGES:]
    if thread:
        lines.append(_strings.text("thread_header"))
        for author, is_bot, text in thread:
            if not text:
                continue
            role = _strings.text("assistant_display_name") if is_bot else author
            lines.append(f"{role}: {text}")
        lines.append(_strings.text("thread_footer"))
    lines.append(_strings.text("history_user_line", name=name, text=user_text))
    lines.append(_strings.text("history_question_header"))
    return "\n".join(lines)
def hash(s: str) -> str:
    """Helper that keeps short, deterministic hashes for filenames and IDs."""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]

# system prompt loader
_PROMPT_CACHE: dict = {}

def _read_txt_prompt(path: Path) -> str:
    """Cache-aware reader for prompt override files stored on disk."""
    mtime = path.stat().st_mtime
    cache_key = str(path)
    cached = _PROMPT_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    _PROMPT_CACHE[cache_key] = (mtime, text)
    
    return text

def load_system_prompt_for_chat(chat: types.Chat) -> str:
    """Load chat-specific system prompt text, falling back to default file."""
    try:
        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            group_path = config.PROMPTS_DIR / f"{chat.id}.txt"
            if group_path.exists():
                return _read_txt_prompt(group_path)
        default_path = config.PROMPTS_DIR / "default.txt"
        return _read_txt_prompt(default_path)
    except FileNotFoundError:
        logging.warning("Prompt .txt file not found; using builtin fallback")
    except Exception as e:
        logging.exception("Failed to load .txt prompt: %s", e)
    return "Пиши что я сегодня не смогу помочь, мой системный промт сломался."

def should_answer(message: types.Message) -> bool:
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()

    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
        replied_username = getattr(message.reply_to_message.from_user, "username", "") or ""
        if bot_username and replied_username == (bot_username or ""):
            return True
        return False
    if message.entities and text:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = text[entity.offset: entity.offset + entity.length]
                if bot_username and mention_text.lstrip("@").lower() == bot_username:
                    return True
    BOT_ADDRESS_RE = re.compile(r'(?i)(?<!\w)(?:нейро-?бот(?:ик|яра)?|бот(?:ик|яра)?|бридж(?:ик)?)(?!\w)')
    if BOT_ADDRESS_RE.search(text):
        return True
    QUESTION_MARK_RE = re.compile(r'\?')
    INTERROGATIVE_RE = re.compile(
        r'(?i)\b('
        r'можно ли|кто может помочь|кто поможет|подскаж(?:и|ите)|помогите|нужна помощь|help|помощь'
        r')\b'
    )
    COMMAND_RE = re.compile(
        r'(?i)\b('
        r'объясни|расскажи|скажи|подскажи|помоги|проверь|сделай|напиши|создай|найди|покажи|настрой'
        r')\b'
    )
    NOISE_RE = re.compile(r'^\s*(?:[^\w\s]|[\w]{1,2})\s*$')
    if NOISE_RE.match(text):
        return False
    score = 0
    if QUESTION_MARK_RE.search(text):
        score += 1
    if INTERROGATIVE_RE.search(text):
        score += 2
    if COMMAND_RE.search(text):
        score += 1
    if len(text) >= 25:
        score += 1
    return score >= 3

_USER_FREEZES: Dict[int, float] = {}

def _save_freezes() -> None:
    try:
        data = {str(uid): ts for uid, ts in _USER_FREEZES.items()}
        path = config.FREEZES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logging.exception("Failed to save FREEZES to JSON")

def _load_freezes() -> None:
    try:
        p = config.FREEZES_FILE
        if not p.exists():
            return
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
        _USER_FREEZES.clear()
        now = time.time()
        for k, ts in data.items():
            try:
                uid = int(k)
                tsv = float(ts)
                if tsv > now:
                    _USER_FREEZES[uid] = tsv
            except Exception:
                continue
    except Exception:
        logging.exception("Failed to load FREEZES from JSON")

def _cleanup_freezes(now: Optional[float] = None) -> None:
    if now is None:
        now = time.time()
    expired = [uid for uid, ts in _USER_FREEZES.items() if ts <= now]
    changed = False
    for uid in expired:
        if _USER_FREEZES.pop(uid, None) is not None:
            changed = True
    if changed:
        _save_freezes()

def set_user_freeze(user_id: int, hours: int) -> float:
    expires_at = time.time() + hours * 3600
    _USER_FREEZES[user_id] = expires_at
    _save_freezes()
    return expires_at

def clear_user_freeze(user_id: int) -> bool:
    removed = _USER_FREEZES.pop(user_id, None) is not None
    if removed:
        _save_freezes()
    return removed

def get_user_freeze(user_id: int) -> Optional[float]:
    _cleanup_freezes()
    expires_at = _USER_FREEZES.get(user_id)
    if expires_at is None:
        return None
    if expires_at <= time.time():
        _USER_FREEZES.pop(user_id, None)
        return None
    return expires_at

def is_user_frozen(user_id: int) -> bool:
    return get_user_freeze(user_id) is not None


def get_hour_string(hours: int) -> str:
    return f"{hours} час" if hours == 1 else f"{hours} часа"


def format_player_info(info: dict) -> str:
    # Порядок полей
    lines = []
    
    for key, value in info.items():
        if key == "Роли":
            roles_lines = "\n".join(f"вЂў {escape(str(r))}" for r in value)
            lines.append(f"{escape(key)}:\n{roles_lines}")

        else:
            # прочие простые поля и ссылки
            lines.append(f"{escape(key)}: <code>{escape(str(value))}</code>")

    return "\n".join(lines)

# ===== User psevdos (local persistent mapping) =====
_PSEVDOS: Dict[int, str] = {}

def _load_psevdos() -> None:
    """Load persisted user psevdos from disk into memory."""
    global _PSEVDOS
    try:
        path = config.PSEVDO_FILE
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            _PSEVDOS = {int(k): str(v) for k, v in data.items() if str(v).strip()}
    except Exception as e:
        logging.exception("Failed to load psevdos: %s", e)
        _PSEVDOS = {}

def _save_psevdos() -> None:
    """Persist the in-memory psevdos map to disk."""
    try:
        path = config.PSEVDO_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {str(k): v for k, v in _PSEVDOS.items()}
        txt = json.dumps(data, ensure_ascii=False, indent=2)
        path.write_text(txt, encoding="utf-8")
    except Exception as e:
        logging.exception("Failed to save psevdos: %s", e)

def set_user_psevdo(user_id: int, name: str) -> str:
    """Set user's personal psevdonym and persist it. Returns normalized name."""
    name = (name or "").strip()
    # normalize whitespace and length
    name = re.sub(r"\s+", " ", name)
    if len(name) > 100:
        name = name[:100]
    _PSEVDOS[user_id] = name
    _save_psevdos()
    return name

def get_user_psevdo(user_id: int) -> Optional[str]:
    """Return user's psevdonym if set."""
    return _PSEVDOS.get(user_id)

# Initialize on import
_load_history()
_load_chat_logs()
_load_guesses()
_load_freezes()
_load_psevdos()


def display_name(user: types.User, prefer_username: bool = False) -> str:
    """Return best display name for addressing a user.

    Priority:
    - saved psevdonym (/psevdo)
    - first_name (if available and prefer_username is False)
    - username (without @)
    - generic fallback
    """
    try:
        if user is None:
            return "Пользователь"
        uid = getattr(user, "id", None)
        if uid is not None:
            pn = get_user_psevdo(int(uid))
            if pn:
                return pn
        if not prefer_username:
            name = getattr(user, "first_name", None)
            if name:
                return str(name)
        uname = getattr(user, "username", None)
        if uname:
            return str(uname)
        # fallback to first_name if username missing and prefer_username True
        name = getattr(user, "first_name", None)
        if name:
            return str(name)
    except Exception:
        pass
    return "Пользователь"






