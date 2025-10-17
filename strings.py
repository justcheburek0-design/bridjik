import json
import logging
from pathlib import Path
import config

_STRINGS: dict | None = None
_STRINGS_MTIME: float | None = None

DEFAULT_STRINGS: dict[str, str] = {
    # System/helper
    "system_html_note": "\n\nВнимание: используй только HTML-теги Telegram (<b>, <i>, <code>, <s>, <u>, <pre>). Markdown запрещён. Не добавляй ссылки, кроме <a href=\"\"></a>.",
    # Start/version
    "start_subscribed_greeting": "Привет, {name}!\nМожешь писать мне свои вопросы\nОбращайся ко мне — бриджик",
    "start_subscribe_cta": "Этот бот доступен только подписчикам. Нажми «{cta_button}» после подписки.",
    "version_subscribed_info": "Версия бота: <b>{version}</b>\nПоследнее обновление: <b>{last_update}</b>",
    # Buttons
    "subscribe_button": "Подписаться",
    "subscription_cta_button": "Проверить подписку",
    "support_button": "Связаться с поддержкой",
    "donate_button": "Задонатить",
    "game_start_button": "Да, сыграем",
    "game_stop_button": "Остановить игру",
    "unfreeze_button": "Разморозить",
    # Simple messages
    "support_message": "Напишите нам, если нужна помощь — мы рядом!",
    "donate_message": "Вы можете поддержать проект донатом. 1 донат = 1 кирпич 😊",
    "game_menu_title": "Давай играть:",
    "status_waiting": "⏳ Запрашиваю статус сервера...",
    "status_error": "⚠️ Не удалось получить статус: {error}",
    "rag_reindex_wait": "⏳ <b>Пересобираю индекс</b>...",
    "rag_reindex_done": "✅ <b>Готово</b>\nЧанков: {count}",
    "rag_reindex_error": "⚠️ Ошибка пересборки: {error}",
    "must_subscribe": "Подпишитесь на @MineBridgeOfficial, иначе бот недоступен",
    "image_processing": "🖼️ <b>Анализирую изображение...</b>",
    "voice_processing": "🎤 <b>Распознаю голос...</b>",
    "thinking": "🤔 <b>Думаю...</b>",
    "vision_flow_failed": "Не удалось обработать изображение. Пожалуйста, пришлите картинку ещё раз без сжатия.",
    "auto_reply_exception": "Что-то пошло не так. {error}",
    # Freeze controls
    "freeze_applied_edit": "🔐 Авто-ответы <b>выключены</b> для <b>{name}</b> на <b>{duration}</b>",
    "freeze_applied_answer": "🔐 Авто-ответы <b>выключены</b> для <b>{name}</b> на <b>{duration}</b>",
    "unfreeze_applied_edit": "🔑 Авто-ответы <b>включены</b> для <b>{name}</b>",
    "unfreeze_applied_answer": "🔑 Авто-ответы <b>включены</b> для <b>{name}</b>",
    "freeze_invalid": "Некорректные параметры",
    "freeze_unauthorized": "Это не ваш запрос!",
    # Player
    "player_wait": "⏳ Запрашиваю профиль...",
    "player_not_found": "Игрок <code>{user_id}</code> не найден в API. Авторизуйтесь на сайте.",
    "player_error": "Ошибка при получении профиля: {error}",
    # Callback subscription
    "callback_greeting_subscribed": "Отлично, {name}! Доступ открыт.",
    "callback_greeting_not_subscribed": "Подписка не найдена! Убедитесь, что вы подписались.",
    # Guess game
    "guess_prompt_user": "У вас активна игра ‘Да/Нет’. Чтобы остановить — [[guess:stop]]. Если забыли объект — напишите [[guess:forgot]].\n\n",
    "guess_prompt_system": "У пользователя активна игра ‘Да/Нет’. Загаданный объект: {obj}. Отвечай строго ‘да’/‘нет’.",
    # ASR
    "transcribe_prefix": "Распознанное сообщение: {text}",
}


def _load_strings() -> None:
    global _STRINGS, _STRINGS_MTIME
    try:
        p = config.PROMPTS_DIR / "strings.json"
        if not p.exists():
            _STRINGS = {}
            _STRINGS_MTIME = None
            return
        mtime = p.stat().st_mtime
        if _STRINGS is not None and _STRINGS_MTIME == mtime:
            return
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
        if isinstance(data, dict):
            _STRINGS = {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
            _STRINGS_MTIME = mtime
        else:
            _STRINGS = {}
            _STRINGS_MTIME = mtime
    except Exception:
        logging.exception("Failed to load strings.json")
        _STRINGS = {}
        _STRINGS_MTIME = None


def text(key: str, /, **kwargs) -> str:
    # Reload if file changed (cheap mtime check)
    _load_strings()
    s = None
    try:
        if _STRINGS and key in _STRINGS:
            s = _STRINGS[key]
        elif key in DEFAULT_STRINGS:
            s = DEFAULT_STRINGS[key]
        else:
            s = key
        if kwargs:
            return s.format(**kwargs)
        return s
    except Exception:
        try:
            return (s or key)
        except Exception:
            return key
