# handlers.py
import logging
import asyncio
import time
import re
import httpx

from aiogram import types
from aiogram.filters import Command

from bot_init import *
import config
import utils
import mc
import mb_api
import rag
import handlers_helpers
import msgs

# Проверка подписки пользователя на обязательный канал (использует объект bot)
async def is_subscribed(id: int) -> bool:
    """RU: Проверяет, подписан ли пользователь на обязательный канал."""
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL, user_id=id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception:
        logging.exception("Error checking subscription")
        return False

def _build_freeze_keyboard(id: int, hot: bool = True) -> types.InlineKeyboardMarkup:
    """RU: Формирует инлайн-клавиатуру для заморозки/разморозки автоответов."""
    buttons = [
        types.InlineKeyboardButton(text=utils.get_hour_string(hours), callback_data=f"freeze:{id}:{hours}")
        for hours in config.FREEZE_OPTIONS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if hot:
        rows.append([types.InlineKeyboardButton(text="🔥 Разморозка 🔥", callback_data=f"unfreeze:{id}")])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("psevdo"))
async def cmd_psevdo(message: types.Message):
    """RU: /psevdo [прозвище] — сохранить личное прозвище локально (id -> прозвище).
    Без аргумента показывает текущее и пример использования."""
    try:
        if not message.from_user:
            return
        uid = message.from_user.id
        raw = (message.text or "").strip()
        # extract everything after command token (supports "/psevdo@botname")
        m = re.match(r"^/psevdo(?:@\w+)?\s+(.+)$", raw, flags=re.IGNORECASE)
        if not m:
            current = utils.get_user_psevdo(uid)
            if current:
                await message.reply(
                    f"Ваше текущее прозвище: <b>{current}</b>\n" \
                    f"Чтобы изменить: <code>/psevdo [Прозвище]</code>"
                )
            else:
                await message.reply("Задайте прозвище: <code>/psevdo [Прозвище]</code>")
            return
        name = m.group(1).strip()
        if not name:
            await message.reply("Пустое прозвище не сохраняю. Пример: <code>/psevdo Вася</code>")
            return
        name = utils.set_user_psevdo(uid, name)
        await message.reply(f"Готово. Ваше прозвище: <b>{name}</b>")
    except Exception:
        logging.exception("/psevdo handler failed")
        try:
            await message.reply("Не получилось сохранить прозвище, попробуйте позже.")
        except Exception:
            pass

@dp.message(Command("id"))
async def cmd_id(message: types.Message):
    """RU: Ответить ID текущего чата."""
    try:
        chat_id = getattr(message.chat, "id", None)
        if chat_id is None:
            await message.reply("Не удалось определить ID чата")
            return
        await message.reply(f"ID чата: <code>{chat_id}</code>")
    except Exception:
        logging.exception("/id handler failed")
        try:
            await message.reply("Произошла ошибка при получении ID чата")
        except Exception:
            pass

@dp.message(Command("freeze"))
async def cmd_freeze(message: types.Message):
    """RU: Показывает кнопки для включения/отключения временной заморозки автоответов."""
    if not message.from_user:
        return

    id = message.from_user.id

    current_freeze = utils.get_user_freeze(id)
    if current_freeze:
        minites_unfreeze = round((current_freeze - time.time()) / 60)
        current_freeze = f"\n⏳ Текущая заморозка действует ещё <b>{minites_unfreeze} мин</b>"
    else:
        current_freeze = ""

    text_body = f"❄️ Выбери <b>длительность заморозки автоответов</b>" + current_freeze

    await message.reply(text_body, reply_markup=_build_freeze_keyboard(id, hot=bool(current_freeze)))


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """RU: Приветствие и предложение подписаться при необходимости."""
    id = message.from_user.id
    # Имя для приветствия: псевдоним (если есть), иначе @username, иначе имя
    _p = utils.get_user_psevdo(id)
    if _p:
        greet_name = _p
    else:
        _u = getattr(message.from_user, "username", None)
        greet_name = f"@{_u}" if _u else (message.from_user.first_name or "")
    if await is_subscribed(id):
        await message.reply(f"Привет, {greet_name}!\nМожешь писать мне свои вопросы\nОбращайся ко мне - бриджик")
        return

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{config.CHANNEL.lstrip('@')}")],
        [types.InlineKeyboardButton(text="Проверить подписку", callback_data="check_subscription")]
    ])
    await message.answer(
        "Для доступа нужен канал @MineBridgeOfficial — подпишитесь и нажмите «<b>Проверить подписку</b>»",
        reply_markup=kb
    )


@dp.message(Command("support"))
async def cmd_support(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Техподдержка", url=config.SUPPORT_URL)]
    ])
    await message.reply(
        "Отвечаем от пары минут до пары часов, пишите всё в одно сообщение!",
        reply_markup=kb
    )

@dp.message(Command("donate"))
async def cmd_donate(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Купить мостики", url=config.DONATE_URL)]
    ])
    await message.reply(
        "На сервере действует валюта мостики, 1 мостик = 1 рубль",
        reply_markup=kb
    )

@dp.message(Command("status"))
# RU: Возвращает текущий статус Minecraft-сервера (через публичное API)
async def cmd_status(message: types.Message):
    msg = await message.reply("🔎 Проверяю статус сервера...")
    try:
        payload = await mc.fetch_status()
        text = mc.format_status_text(payload)
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"⚠️ Не удалось получить статус: `{utils._shorten(str(e), 300)}`")

@dp.message(Command("rag_reindex"))
# RU: Пересборка локального RAG-индекса по запросу администратора
async def cmd_rag_reindex(message: types.Message):
    msg = await message.reply("🔄 <b>Перестраиваю индекс</b>...")
    try:
        global RAG_CHUNKS
        rag.RAG_LOADED = False
        await rag._ensure_rag_index()
        await msg.edit_text(f"✅ <b>Готово</b>\nЧанков: {len(rag.RAG_CHUNKS)}")
    except Exception as e:
        logging.exception("RAG reindex error")
        await msg.edit_text(f"⚠️ Ошибка перестройки: {e}")


@dp.callback_query()
async def callback_any(query: types.CallbackQuery):
    """RU: Обрабатывает коллбеки: freeze/unfreeze и проверку подписки."""
    username = utils.get_user_psevdo(getattr(query.from_user, "id", 0)) or (
        getattr(query.from_user, "first_name", None) or getattr(query.from_user, "username", "")
    )
    data = (query.data or "").strip()

    if data.startswith("freeze:"):
        parts = data.split(":")
        if len(parts) != 3:
            await query.answer("Не удалось заморозить", show_alert=True)
            return
        _, id, hours = parts
        if id != str(query.from_user.id):
            await query.answer("Не твоё сообщение!", show_alert=True)
            return
        try:
            id = int(id)
            hours = int(hours)
        except ValueError:
            await query.answer("Недопустимые параметры", show_alert=True)
            return
        if hours not in config.FREEZE_OPTIONS:
            await query.answer("Недопустимая длительность", show_alert=True)
            return

        id = query.from_user.id
        utils.set_user_freeze(id, hours)
        try:
            if query.message:
                await query.message.edit_text(
                    f"🔐 Авто-ответы <b>выключены</b> для <b>{username}</b> на <b>{utils.get_hour_string(hours)}</b>",
                    reply_markup=_build_freeze_keyboard(id),
                )
        except Exception:
            logging.exception("freeze: failed to edit confirmation message")
        await query.answer(f"🔐 Авто-ответы <b>выключены</b> для <b>{username}</b> на <b>{utils.get_hour_string(hours)}</b>")
        return

    if data.startswith("unfreeze:"):
        parts = data.split(":")
        if len(parts) != 2:
            await query.answer("Не удалось разморозить", show_alert=True)
            return
        _, id = parts
        if id != str(query.from_user.id):
            await query.answer("Это не твоё сообщение!", show_alert=True)
            return

        id = query.from_user.id
        utils.clear_user_freeze(id)
        
        try:
            if query.message:
                await query.message.edit_text(
                    f"🔑 Авто-ответы <b>включены</b> для <b>{username}</b>",
                    reply_markup=_build_freeze_keyboard(id, hot=False),
                )
        except Exception:
            logging.exception("unfreeze: failed to edit confirmation message")
        await query.answer(f"🔑 Авто-ответы <b>включены</b> для <b>{username}</b>")
        return

    if data != "check_subscription":
        await query.answer()
        return

    if await is_subscribed(query.from_user.id):
        await query.message.reply(f"Привет, {username}!\nМожешь писать мне свои вопросы\nОбращайся ко мне - бриджик")
    else:
        await query.message.reply("Подписка не найдена! Убедитесь, что подписаны на канал", show_alert=True)

@dp.message(Command("player"))
 # RU: Команда /player — получить данные игрока по нику (или @username)
async def cmd_player(message: types.Message):
    """/player — получить данные игрока из MineBridge API.
    Если ник не указан, пробуем использовать Telegram @username отправителя."""
    id = message.from_user.id
    text = (message.text or "").strip()
    if not await is_subscribed(id):
        await message.reply("Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком")
        utils.save_incoming_message(message, text)
        return
    
    text = (message.text or "").strip()

    msg = await message.reply("🔎 Проверяю тебя...")
    try:
        player_info = await mb_api.fetch_player_by_id(str(id))
        if not player_info:
            await msg.edit_text(f"😕 Игрок <code>{(id)}</code> не найден или произошла ошибка API.")
            return
        text = utils.format_player_info(player_info)
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при запросе: {utils._shorten(str(e), 300)}")

@dp.message()
async def auto_reply(message: types.Message):
    """RU: Автоответ ИИ — отвечает, когда сообщение адресовано боту."""
    prompt = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    has_photo = bool(getattr(message, "photo", None))
    has_image_doc = bool(getattr(message, "document", None) and str(getattr(message.document, "mime_type", "")).startswith("image/"))
    has_image = has_photo or has_image_doc
    has_voice = bool(getattr(message, "voice", None)) or bool(getattr(message, "audio", None) and str(getattr(message.audio, "mime_type", "")).startswith("audio/"))

    # Voice transcription (runs even if bot is not addressed)
    if has_voice:
        try:
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")
            except Exception:
                pass
            fid = message.voice.file_id
            mime = (getattr(message.voice, "mime_type", None) or "audio/ogg")
            fobj = await bot.get_file(fid)
            file_path = getattr(fobj, "file_path", None)
            if not file_path:
                raise RuntimeError("missing voice file_path")
            url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file_path}"
            timeout = httpx.Timeout(30.0, connect=10.0, read=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                audio_bytes = resp.content
            prompt = await handlers_helpers.transcribe_voice_gemini(audio_bytes, mime)
        except Exception:
            logging.exception("voice transcription flow failed")
    if not prompt and not has_image:
        # RU: Сохраняем известные нетекстовые данные (в т.ч. стикеры), но не отвечаем
        utils.save_incoming_message(message, prompt)
        return
    
    id = getattr(message.from_user, "id", None)
    if id is not None and utils.is_user_frozen(id):
        logging.info("Auto replies are temporarily frozen for user %s", id)
        utils.save_incoming_message(message, prompt)
        return

    # RU: Надёжно определяем тип чата (aiogram может вернуть enum или строку)
    chat_type = getattr(message.chat, "type", None)
    if isinstance(chat_type, str):
        ct_name = chat_type.upper()
    else:
        # RU: chat_type может быть Enum с .name или чем-то иным
        ct_name = getattr(chat_type, "name", str(chat_type)).upper()
    is_group = ct_name in ("GROUP", "SUPERGROUP")

    if is_group and not utils.should_answer(message):
        logging.info("Пропущено (но сохранено) сообщение без упоминания бриджика или ответа на бриджик (группа)")
        utils.save_incoming_message(message, prompt)
        return
    
    if not await is_subscribed(id):
        await message.reply("Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком")
        utils.save_incoming_message(message, prompt)
        return

    try:
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
        msg = None
        if has_image:
            msg = await message.reply("🖼️ <b>Распознаю изображение...</b>")
        elif has_voice:
            msg = await message.reply("🎙️ <b>Распознаю голосовое...</b>")
        else:
            msg = await message.reply("⏳ <b>Думаю...</b>")
        # Имя для LLM контекста: псевдоним, иначе first_name/username (без @)
        username = utils.get_user_psevdo(id) or (
            getattr(message.from_user, "first_name", None) or getattr(message.from_user, "username", "")
        )
        conv_key = utils.make_key(message)

        sys_prompt = utils.load_system_prompt_for_chat(message.chat)
        sys_prompt += "\n\nВажно: Используй HTML-разметку для форматирования ответа (<b>, <i>, <code>, <s>, <u>, <pre>). MarkDown НЕЛЬЗЯ! Все ссылки вставляй сразу в текст <a href=""></a>"

        rag_ctx = ""
        
        # call OpenAI: vision for images, plain for text
        if has_image:
            try:
                if message.photo:
                    file_id = message.photo[-1].file_id
                    mime = "image/jpeg"
                else:
                    file_id = message.document.file_id
                    mime = (message.document.mime_type or "image/jpeg")
                async def _download_image() -> bytes:
                    fobj = await bot.get_file(file_id)
                    file_path = getattr(fobj, "file_path", None)
                    if not file_path:
                        raise RuntimeError("missing file_path")
                    url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file_path}"
                    timeout = httpx.Timeout(20.0, connect=10.0, read=20.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        return resp.content

                # Run image download and RAG in parallel
                tasks = [
                    asyncio.create_task(rag.build_full_context(prompt, id)),
                    asyncio.create_task(_download_image())
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                rag_ctx, image_bytes = results
                if isinstance(image_bytes, Exception):
                    raise image_bytes
                if isinstance(rag_ctx, Exception):
                    logging.exception(f"RAG: failed to build context. {rag_ctx}")
                    rag_ctx = ""

                answer = await handlers_helpers.complete_openai(
                    prompt,
                    username,
                    conv_key,
                    sys_prompt,
                    rag_ctx,
                    message,
                    image_bytes=image_bytes,
                    mime_type=mime
                )
            except Exception:
                logging.exception("vision flow failed")
                answer = "Не удалось обработать изображение. Попробуй ещё раз прислать фото или добавь подпись."
        else:
            try:
                # Получаем RAG контекст (если включён)
                rag_ctx = await rag.build_full_context(prompt, id)
            except Exception:
                logging.exception("RAG: failed to build context")
            
            answer = await handlers_helpers.complete_openai(
                prompt,
                username,
                conv_key,
                sys_prompt,
                rag_ctx,
                message
            )

        await msgs.long_text(msg, message, answer)
    except Exception as e:
        logging.exception("Ошибка в auto_reply")
        try:
            await msg.edit_text(f"<b>Что-то пошло не так</b> ⚠️\n{str(e)}")
        except Exception:
            pass
