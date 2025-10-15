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

import config
from bot_init import *

# ===== Per-user short history (РґРёР°Р»РѕРіРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЊв†”Р°СЃСЃРёСЃС‚РµРЅС‚) =====
HistoryKey = Tuple[int, int]  # (chat_id, user_id)
HISTORY: Dict[HistoryKey, Deque[Tuple[str, str]]] = defaultdict(
    lambda: deque(maxlen=config.DM_MAX_MESSAGES)
)

# ===== Guessing game memory (per chat+user) =====
_GUESSES: dict[str, str] = {}  # key as 'chat:user' -> object

def _save_guesses() -> None:
    try:
        path = config.DATA_DIR / 'guesses.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_GUESSES, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        logging.exception('Failed to save GUESSES to JSON')

def _load_guesses() -> None:
    try:
        path = config.DATA_DIR / 'guesses.json'
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding='utf-8') or '{}')
        if isinstance(data, dict):
            _GUESSES.clear()
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, str) and k and v:
                    _GUESSES[k] = v
    except Exception:
        logging.exception('Failed to load GUESSES from JSON')

def set_user_guess(key: HistoryKey, obj: str) -> None:
    _GUESSES[_hist_key_str(key)] = (obj or '').strip()
    _save_guesses()

def get_user_guess(key: HistoryKey):
    return _GUESSES.get(_hist_key_str(key))

def clear_user_guess(key: HistoryKey) -> None:
    _GUESSES.pop(_hist_key_str(key), None)
    _save_guesses()


# JSON-РїРµСЂСЃРёСЃС‚ РґР»СЏ HISTORY
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

# ===== Per-chat raw history (РїРѕСЃР»РµРґРЅРёРµ СЃРѕРѕР±С‰РµРЅРёСЏ С‡Р°С‚Р°) =====
# РҐСЂР°РЅРёРј С‚РѕР»СЊРєРѕ РЅРµРѕР±С…РѕРґРёРјС‹Рµ РїРѕР»СЏ, С‡С‚РѕР±С‹ РЅРµ С‚Р°С‰РёС‚СЊ С†РµР»С‹Р№ Message.
# (author, is_bot, text)
ChatLine = Tuple[str, bool, str]
CHAT_LOGS: Dict[int, Deque[ChatLine]] = defaultdict(
    lambda: deque(maxlen=config.GROUP_MAX_MESSAGES)
)

# JSON-РїРµСЂСЃРёСЃС‚ РґР»СЏ CHAT_LOGS
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
    """RU: РћР±СЂРµР·Р°РµС‚ РїСЂРѕР±РµР»С‹ Рё РґР»РёРЅРЅС‹Рµ СЃС‚СЂРѕРєРё, РґРѕР±Р°РІР»СЏСЏ РјРЅРѕРіРѕС‚РѕС‡РёРµ."""
    s = (s or "").strip()
    return (s[:limit] + "...") if len(s) > limit else s

def make_key(msg: types.Message) -> HistoryKey:
    """RU: Р¤РѕСЂРјРёСЂСѓРµС‚ РєР»СЋС‡ РёСЃС‚РѕСЂРёРё РЅР° РѕСЃРЅРѕРІРµ chat_id Рё user_id."""
    return (msg.chat.id, msg.from_user.id)

def remember_user(key: HistoryKey, text: str) -> None:
    """RU: РЎРѕС…СЂР°РЅСЏРµС‚ РєСЂР°С‚РєСѓСЋ РІРµСЂСЃРёСЋ РїРѕСЃР»РµРґРЅРµРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ."""
    HISTORY[key].append(("user", _shorten(text)))
    _save_history()

def remember_assistant(key: HistoryKey, text: str) -> None:
    """RU: РЎРѕС…СЂР°РЅСЏРµС‚ РєСЂР°С‚РєРёР№ РѕС‚РІРµС‚ Р°СЃСЃРёСЃС‚РµРЅС‚Р° РґР»СЏ РєРѕРЅС‚РµРєСЃС‚Р°."""
    HISTORY[key].append(("assistant", _shorten(text)))
    _save_history()

def build_input_with_history(key: HistoryKey, user_text: str, name: str) -> str:
    """РЎРѕР±РёСЂР°РµС‚ РІС…РѕРґ СЃ РєРѕСЂРѕС‚РєРѕР№ РёСЃС‚РѕСЂРёРµР№ РїРµСЂРµРїРёСЃРєРё (РґР»СЏ Р»РёС‡РєРё)."""
    lines: List[str] = []
    hist = HISTORY.get(key)
    if hist:
        lines.append(f"РСЃС‚РѕСЂРёСЏ: РїРѕСЃР»РµРґРЅРёРµ (РґРѕ {config.DM_MAX_MESSAGES}):")
        for role, text in hist:
            who = "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ" if role == "user" else "РђСЃСЃРёСЃС‚РµРЅС‚"
            lines.append(f"{who}: {text}")
        lines.append("РљРѕРЅРµС† РёСЃС‚РѕСЂРёРё")
    # Inject guessing game state
    try:
        _g = get_user_guess(key)
        if _g:
            lines.append("РРіСЂР° 'РЈРіР°РґР°Р№ РѕР±СЉРµРєС‚' Р°РєС‚РёРІРЅР°. Р—Р°РіР°РґР°РЅРЅС‹Р№ РѕР±СЉРµРєС‚: " + _g + ". РќРµ СЂР°СЃРєСЂС‹РІР°Р№ РѕС‚РІРµС‚ РЅР°РїСЂСЏРјСѓСЋ Рё РѕС†РµРЅРёРІР°Р№ РїРѕРїС‹С‚РєРё.")
    except Exception:
        pass
    lines.append(f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ ({name}): {user_text}")
    lines.append("РћС‚РІРµС‚:")
    return "\n".join(lines)

def _author_from(msg: types.Message) -> str:
    """RU: РџРѕР»СѓС‡Р°РµС‚ РѕС‚РѕР±СЂР°Р¶Р°РµРјРѕРµ РёРјСЏ Р°РІС‚РѕСЂР° РёР· РІС…РѕРґСЏС‰РµРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ."""
    user = getattr(msg, "from_user", None)
    if not user:
        return "РЅРµРёР·РІРµСЃС‚РЅРѕ"
    return (getattr(user, "username", None) or getattr(user, "first_name", "") or "Р±РµР·С‹РјСЏРЅРЅС‹Р№")

def save_incoming_message(message: types.Message, text: str) -> None:
    """RU: Р—Р°РїРёСЃС‹РІР°РµС‚ СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІ Р±СѓС„РµСЂ С‚СЂР°РЅСЃРєСЂРёРїС‚Р° С‡Р°С‚Р°."""
    chat_id = message.chat.id
    author = _author_from(message)
    is_bot = bool(getattr(message.from_user, "is_bot", False))
    if not text:
        if message.photo:
            text = f"Р¤РѕС‚Рѕ: {message.photo[-1].file_id}"
        elif message.document:
            text = f"Р”РѕРєСѓРјРµРЅС‚: {message.document.file_id}"
        elif message.voice:
            text = f"Р“РѕР»РѕСЃРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ (С‚РµРєСЃС‚ РЅРµ СЂР°СЃРїРѕР·РЅР°РЅ): {message.voice.file_id}"
        elif message.video:
            text = f"Р’РёРґРµРѕ: {message.video.file_id}"
        elif message.audio:
            text = f"РђСѓРґРёРѕ: {message.audio.file_id}"
        elif message.sticker:
            text = f"РЎС‚РёРєРµСЂ {message.sticker.emoji}: {message.sticker.file_id}"
        else:
            return
    CHAT_LOGS[chat_id].append((author, is_bot, _shorten(text)))
    _save_chat_logs()

def save_outgoing_message(chat_id: int, text: str, bot_display_name: str = "РђСЃСЃРёСЃС‚РµРЅС‚") -> None:
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
    """Собирает вход из нитки чата (группы) с недавними репликами."""
    lines: List[str] = []
    chat_id = message.chat.id
    thread: List[ChatLine] = list(CHAT_LOGS.get(chat_id, deque()))[-config.GROUP_MAX_MESSAGES:]
    if thread:
        lines.append("Контекст чата: последние сообщения:")
        for author, is_bot, text in thread:
            if not text:
                continue
            role = "Ассистент" if is_bot else author
            lines.append(f"{role}: {text}")
        lines.append("Конец контекста")
    # Inject guessing game state for group threads
    try:
        key = (message.chat.id, message.from_user.id)
        _g = get_user_guess(key)
        if _g:
            lines.append("Игра 'Угадай объект' активна. Загаданный объект: " + _g + ". Не раскрывай ответ напрямую и оценивай попытки.")
    except Exception:
        pass
    lines.append(f"Пользователь ({name}): {user_text}")
    lines.append("Ответ:")
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
    return "РџРёС€Рё С‡С‚Рѕ СЏ СЃРµРіРѕРґРЅСЏ РЅРµ СЃРјРѕРіСѓ РїРѕРјРѕС‡СЊ, РјРѕР№ СЃРёСЃС‚РµРјРЅС‹Р№ РїСЂРѕРјС‚ СЃР»РѕРјР°Р»СЃСЏ."

def should_answer(message: types.Message) -> bool:
    """RU: Р­РІСЂРёСЃС‚РёС‡РµСЃРєРё СЂРµС€Р°РµС‚, РЅСѓР¶РЅРѕ Р»Рё Р±РѕС‚Сѓ РѕС‚РІРµС‡Р°С‚СЊ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё."""
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    # RU: Р•СЃР»Рё СЌС‚Рѕ reply вЂ” СЂРµР°РіРёСЂСѓРµРј С‚РѕР»СЊРєРѕ РµСЃР»Рё РѕС‚РІРµС‚ Р°РґСЂРµСЃРѕРІР°РЅ РЅР°С€РµРјСѓ Р±РѕС‚Сѓ
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
    BOT_ADDRESS_RE = re.compile(r'(?i)(?<!\w)(?:РЅРµР№СЂРѕ-?Р±РѕС‚(?:РёРє|СЏСЂР°)?|Р±РѕС‚(?:РёРє|СЏСЂР°)?|Р±СЂРёРґР¶(?:РёРє)?)(?!\w)')
    if BOT_ADDRESS_RE.search(text):
        return True
    QUESTION_MARK_RE = re.compile(r'\?')
    INTERROGATIVE_RE = re.compile(
        r'(?i)\b('
        r'РјРѕР¶РЅРѕ Р»Рё|РєС‚Рѕ РјРѕР¶РµС‚ РїРѕРјРѕС‡СЊ|РєС‚Рѕ РїРѕРјРѕР¶РµС‚|РїРѕРґСЃРєР°Р¶(?:Рё|РёС‚Рµ)|РїРѕРјРѕРіРёС‚Рµ|РЅСѓР¶РЅР° РїРѕРјРѕС‰СЊ|help|РїРѕРјРѕС‰СЊ'
        r')\b'
    )
    COMMAND_RE = re.compile(
        r'(?i)\b('
        r'РѕР±СЉСЏСЃРЅРё|СЂР°СЃСЃРєР°Р¶Рё|СЃРєР°Р¶Рё|РїРѕРґСЃРєР°Р¶Рё|РїРѕРјРѕРіРё|РїСЂРѕРІРµСЂСЊ|СЃРґРµР»Р°Р№|РЅР°РїРёС€Рё|СЃРѕР·РґР°Р№|РЅР°Р№РґРё|РїРѕРєР°Р¶Рё|РЅР°СЃС‚СЂРѕР№'
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
    """RU: РЈРґР°Р»СЏРµС‚ РёСЃС‚С‘РєС€РёРµ Р·Р°РїРёСЃРё Р·Р°РјРѕСЂРѕР·РєРё, РїРѕРґРґРµСЂР¶РёРІР°СЏ РєСЌС€ РІ Р°РєС‚СѓР°Р»СЊРЅРѕРј СЃРѕСЃС‚РѕСЏРЅРёРё."""
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
    """RU: Р’РєР»СЋС‡Р°РµС‚ Р·Р°РјРѕСЂРѕР·РєСѓ Р°РІС‚РѕРѕС‚РІРµС‚РѕРІ РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РЅР° СѓРєР°Р·Р°РЅРЅРѕРµ С‡РёСЃР»Рѕ С‡Р°СЃРѕРІ."""
    expires_at = time.time() + hours * 3600
    _USER_FREEZES[user_id] = expires_at
    _save_freezes()
    return expires_at

def clear_user_freeze(user_id: int) -> bool:
    """RU: РЎРЅРёРјР°РµС‚ Р·Р°РјРѕСЂРѕР·РєСѓ, РµСЃР»Рё РѕРЅР° Р±С‹Р»Р°; РІРѕР·РІСЂР°С‰Р°РµС‚ С„Р°РєС‚ РёР·РјРµРЅРµРЅРёСЏ."""
    removed = _USER_FREEZES.pop(user_id, None) is not None
    if removed:
        _save_freezes()
    return removed

def get_user_freeze(user_id: int) -> Optional[float]:
    """RU: Р’РѕР·РІСЂР°С‰Р°РµС‚ UNIX-РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РјРѕСЂРѕР·РєРё (РёР»Рё None)."""
    _cleanup_freezes()
    expires_at = _USER_FREEZES.get(user_id)
    if expires_at is None:
        return None
    if expires_at <= time.time():
        _USER_FREEZES.pop(user_id, None)
        return None
    return expires_at

def is_user_frozen(user_id: int) -> bool:
    """RU: РџСЂРѕРІРµСЂСЏРµС‚, РµСЃС‚СЊ Р»Рё Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Р°РєС‚РёРІРЅР°СЏ Р·Р°РјРѕСЂРѕР·РєР°."""
    return get_user_freeze(user_id) is not None


def get_hour_string(hours: int) -> str:
    """RU: Р¤РѕСЂРјР°С‚РёСЂСѓРµС‚ РєРѕР»РёС‡РµСЃС‚РІРѕ С‡Р°СЃРѕРІ С‡РµР»РѕРІРµРєРѕС‡РёС‚Р°РµРјРѕР№ СЃС‚СЂРѕРєРѕР№."""
    return f"{hours} С‡Р°СЃ" if hours == 1 else f"{hours} С‡Р°СЃР°"


def format_player_info(info: dict) -> str:
    """RU: Р¤РѕСЂРјР°С‚РёСЂСѓРµС‚ РїСЂРѕС„РёР»СЊ MineBridge РІ Р±РµР·РѕРїР°СЃРЅС‹Р№ РґР»СЏ Telegram HTML."""
    # РџРѕСЂСЏРґРѕРє РїРѕР»РµР№
    lines = []
    
    for key, value in info.items():
        if key == "Р РѕР»Рё":
            roles_lines = "\n".join(f"вЂў {escape(str(r))}" for r in value)
            lines.append(f"{escape(key)}:\n{roles_lines}")

        else:
            # РїСЂРѕС‡РёРµ РїСЂРѕСЃС‚С‹Рµ РїРѕР»СЏ Рё СЃСЃС‹Р»РєРё
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
            return "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ"
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
    return "РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ"


