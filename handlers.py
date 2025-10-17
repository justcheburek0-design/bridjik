# Telegram bot handlers
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
import strings

import msgs
from aiogram.enums import ChatType


async def is_subscribed(id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL, user_id=user_id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception:
        logging.exception("Error checking subscription")
        return False

def _build_freeze_keyboard(user_id: int, hot: bool = True) -> types.InlineKeyboardMarkup:
    buttons = [
        types.InlineKeyboardButton(text=utils.get_hour_string(hours), callback_data=f"freeze:{user_id}:{hours}")
        for hours in config.FREEZE_OPTIONS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if hot:
        rows.append([types.InlineKeyboardButton(text=strings.text("unfreeze_button"), callback_data=f"unfreeze:{user_id}")])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("psevdo"))
async def cmd_psevdo(message: types.Message):
    """/psevdo [name] ? set or view personal pseudo (id -> name)."""
    try:
        if not message.from_user:
            return
        uid = message.from_user.id
        raw = (message.text or "").strip()
        # Extract everything after command token (supports "/psevdo@botname")
        m = re.match(r"^/psevdo(?:@\w+)?\s+(.+)$", raw, flags=re.IGNORECASE)
        if not m:
            current = utils.get_user_psevdo(uid)
            if current:
                await message.reply(strings.text("psevdo_current", name=current))
            else:
                await message.reply(strings.text("psevdo_set_prompt"))
            return
        name = m.group(1).strip()
        if not name:
            await message.reply(strings.text("psevdo_invalid"))
            return
        name = utils.set_user_psevdo(uid, name)
        await message.reply(strings.text("psevdo_saved", name=name))
    except Exception:
        logging.exception("/psevdo handler failed")
        try:
            await message.reply(strings.text("psevdo_error"))
        except Exception:
            pass
@dp.message(Command("id"))
async def cmd_id(message: types.Message):
    """/id ? return the chat ID."""
    try:
        chat_id = getattr(message.chat, "id", None)
        if chat_id is None:
            await message.reply(strings.text("id_missing"))
            return
        await message.reply(strings.text("id_reply", chat_id=chat_id))
    except Exception:
        logging.exception("/id handler failed")
        try:
            await message.reply(strings.text("id_error"))
        except Exception:
            pass
@dp.message(Command("freeze"))
async def cmd_freeze(message: types.Message):
    """Open freeze menu for auto-replies."""
    if not message.from_user:
        return

    user_id = message.from_user.id

    current_freeze = utils.get_user_freeze(user_id)
    if current_freeze:
        minites_unfreeze = round((current_freeze - time.time()) / 60)
        current_freeze = strings.text("freeze_current_until", minutes=minites_unfreeze)
    else:
        current_freeze = ""

    await message.reply(strings.text("freeze_menu_header") + current_freeze, reply_markup=_build_freeze_keyboard(user_id, hot=bool(current_freeze)))



@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    name = utils.display_name(message.from_user)
    
    if await is_subscribed(user_id):
        await message.reply(strings.text("start_subscribed_greeting", name=name))
        return

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=strings.text("subscribe_button"), url="https://t.me/" + config.CHANNEL.lstrip("@"))],
        [types.InlineKeyboardButton(text=strings.text("subscription_cta_button"), callback_data="check_subscription")]
    ])
    await message.answer(strings.text("start_subscribe_cta", cta_button=strings.text("subscription_cta_button")),
        reply_markup=kb
    )


@dp.message(Command("version"))
async def cmd_version(message: types.Message):
    user_id = message.from_user.id
    
    if await is_subscribed(user_id):
        await message.reply(strings.text("version_subscribed_info", version=version, last_update=last_update.strftime("%Y-%m-%d %H:%M:%S")))
        return

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=strings.text("subscribe_button"), url="https://t.me/" + config.CHANNEL.lstrip("@"))],
        [types.InlineKeyboardButton(text=strings.text("subscription_cta_button"), callback_data="check_subscription")]
    ])
    await message.answer(strings.text("start_subscribe_cta", cta_button=strings.text("subscription_cta_button")),
        reply_markup=kb
    )


@dp.message(Command("support"))
async def cmd_support(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=strings.text("support_button"), url=config.SUPPORT_URL)]
    ])
    await message.reply(
        strings.text("support_message"),
        reply_markup=kb
    )

@dp.message(Command("donate"))
async def cmd_donate(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=strings.text("donate_button"), url=config.DONATE_URL)]
    ])
    await message.reply(
        strings.text("donate_message"),
        reply_markup=kb
    )

@dp.message(Command("game"))
async def cmd_game(message: types.Message):
    try:
        if not await is_subscribed(message.from_user.id):
            await message.reply(strings.text("must_subscribe"))
            utils.save_incoming_message(message, message.text or "")
            return
        # Build keyboard: always offer to start the game; if active, also offer to stop
        try:
            active = bool(utils.get_user_guess(message.chat.id))
        except Exception:
            active = False
        rows = [[types.InlineKeyboardButton(text=strings.text("game_start_button"), callback_data="game:guess_object")]]
        if active:
            rows.append([types.InlineKeyboardButton(text=strings.text("game_stop_button"), callback_data="game:guess_stop")])
        kb = types.InlineKeyboardMarkup(inline_keyboard=rows)
        await message.reply(strings.text("game_menu_title"), reply_markup=kb)
    except Exception:
        logging.exception("/game handler failed")
        
@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    msg = await message.reply(strings.text("status_waiting"))
    try:
        payload = await mc.fetch_status()
        text = mc.format_status_text(payload)
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(strings.text("status_error", error=utils._shorten(str(e), 300)))

@dp.message(Command("rag_reindex"))
async def cmd_rag_reindex(message: types.Message):
    msg = await message.reply(strings.text("rag_reindex_wait"))
    try:
        global RAG_CHUNKS
        rag.RAG_LOADED = False
        await rag._ensure_rag_index()
        await msg.edit_text(strings.text("rag_reindex_done", count=len(rag.RAG_CHUNKS)))
    except Exception as e:
        logging.exception("RAG reindex error")
        await msg.edit_text(strings.text("rag_reindex_error", error=str(e)))


@dp.callback_query()
async def callback_any(query: types.CallbackQuery):
 
    name = utils.display_name(query.from_user)
    
    data = (query.data or "").strip()
    message = query.message

    if data.startswith("freeze:"):
        parts = data.split(":")
        if len(parts) != 3:
            await query.answer(strings.text("freeze_invalid"), show_alert=True)
            return
        _, target_id, hours = parts
        if target_id != str(query.from_user.id):
            await query.answer(strings.text("freeze_unauthorized"), show_alert=True)
            return
        try:
            target_id = int(target_id)
            hours = int(hours)
        except ValueError:
            await query.answer(strings.text("freeze_invalid"), show_alert=True)
            return
        if hours not in config.FREEZE_OPTIONS:
            await query.answer(strings.text("freeze_invalid"), show_alert=True)
            return

        user_id = query.from_user.id
        utils.set_user_freeze(user_id, hours)
        try:
            if message:
                await message.edit_text(
                    strings.text("freeze_applied_edit", name=name, duration=utils.get_hour_string(hours)),
                    reply_markup=_build_freeze_keyboard(user_id),
                )
        except Exception:
            logging.exception("freeze: failed to edit confirmation message")
        await query.answer(strings.text("freeze_applied_answer", name=name, duration=utils.get_hour_string(hours)))
        return

    if data.startswith("unfreeze:"):
        parts = data.split(":")
        if len(parts) != 2:
            await query.answer(strings.text("freeze_invalid"), show_alert=True)
            return
        _, target_id = parts
        if target_id != str(query.from_user.id):
            await query.answer(strings.text("freeze_unauthorized"), show_alert=True)
            return

        user_id = query.from_user.id
        utils.clear_user_freeze(user_id)
        
        try:
            if message:
                await message.edit_text(
                    strings.text("unfreeze_applied_edit", name=name),
                    reply_markup=_build_freeze_keyboard(user_id, hot=False),
                )
        except Exception:
            logging.exception("unfreeze: failed to edit confirmation message")

        await query.answer(strings.text("unfreeze_applied_answer", name=name))
        return

    if data.startswith("game:"):
        # Game callbacks
        if data == "game:guess_object":
            try:
                try:
                    await query.answer()
                except Exception:
                    pass
                conv_key = (message.chat.id, query.from_user.id)
                sys_prompt = utils.load_system_prompt_for_chat(message.chat)
                prompt = strings.text("guess_game_instructions")
                utils.save_incoming_message(message, prompt)
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")

                tmp = await message.reply(strings.text("thinking")))
                answer = await handlers_helpers.complete_openai(
                    name,
                    conv_key,
                    sys_prompt,
                    None,
                    message,
                    user_id=query.from_user.id,
                )
                await msgs.long_text(tmp, message, answer)
            except Exception as e:
                logging.exception(f"game:guess_object failed\n{e}")
            if message:
                await message.reply(strings.text("game_guess_failed"))
            return

        elif data == "game:guess_stop":
            try:
                await query.answer("Останавливаю игру")
            except Exception:
                pass
            try:
                if message:
                    utils.clear_user_guess(message.chat.id)
                    await message.reply(strings.text("game_stopped"))
                    pass
            except Exception:
                logging.exception("game:guess_stop failed")
            return
        await query.answer()
        return
    if data != "check_subscription":
        await query.answer()
        return

    if await is_subscribed(query.from_user.id):
        await message.reply(strings.text("callback_greeting_subscribed", name=name))
    else:
        await message.reply(strings.text("callback_greeting_not_subscribed"), show_alert=True)

@dp.message(Command("player"))
async def cmd_player(message: types.Message):
    """/player — get player info from MineBridge API. If no nick is provided, use Telegram @username."""
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if not await is_subscribed(user_id):
        await message.reply(strings.text("must_subscribe"))
        utils.save_incoming_message(message, text)
        return
    
    text = (message.text or "").strip()

    msg = await message.reply(strings.text("player_wait"))
    try:
        player_info = await mb_api.fetch_player_by_id(str(user_id))
        if not player_info:
            await msg.edit_text(strings.text("player_not_found", user_id=user_id))
            return
        text = utils.format_player_info(player_info)
        await msg.edit_text(text)
    except Exception as e:
        await msg.edit_text(strings.text("player_error", error=str(e)))


@dp.message()
async def auto_reply(message: types.Message):
    prompt = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    has_photo = bool(getattr(message, "photo", None))
    has_image_doc = bool(getattr(message, "document", None) and str(getattr(message.document, "mime_type", "")).startswith("image/"))
    has_image = has_photo or has_image_doc
    has_voice = bool(getattr(message, "voice", None)) or bool(getattr(message, "audio", None) and str(getattr(message.audio, "mime_type", "")).startswith("audio/"))
    name = utils.display_name(message.from_user)

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
        utils.save_incoming_message(message, prompt)
        return
    
    user_id = getattr(message.from_user, "id", None)
    if user_id is not None and utils.is_user_frozen(user_id):
        logging.info("Auto replies are temporarily frozen for user %s", user_id)
        utils.save_incoming_message(message, prompt)
        return

    chat_type = getattr(message.chat, "type", None)
    if isinstance(chat_type, str):
        ct_name = chat_type.upper()
    else:
        ct_name = getattr(chat_type, "name", str(chat_type)).upper()
    is_group = ct_name in ("GROUP", "SUPERGROUP")

    if is_group and not utils.should_answer(message):
        logging.info("Skipping reply in group: not addressed to bot")
        utils.save_incoming_message(message, prompt)
        return
    
    if not await is_subscribed(user_id):
        await message.reply("Подпишитесь на @MineBridgeOfficial, чтобы пользоваться бриджиком")
        await message.reply(strings.text("must_subscribe"))
        return

    try:
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
        msg = None
        if has_image:
            msg = await message.reply(strings.text("image_processing"))
        elif has_voice:
            msg = await message.reply(strings.text("voice_processing"))
        else:
            msg = await message.reply(strings.text("thinking"))
        
        conv_key = utils.make_key(message)

        sys_prompt = utils.load_system_prompt_for_chat(message.chat)
        
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

                answer = await handlers_helpers.complete_openai(
                    prompt,
                    name,
                    conv_key,
                    sys_prompt,
                    message,
                    image_bytes=image_bytes,
                    mime_type=mime,
                    user_id=user_id,
                )
            except Exception:
                logging.exception("vision flow failed")
                answer = strings.text("vision_flow_failed")
        else:
            answer = await handlers_helpers.complete_openai(
                prompt,
                name,
                conv_key,
                sys_prompt,
                None,
                message,
                user_id=user_id,
            )

        await msgs.long_text(msg, message, answer)
    except Exception as e:
        logging.exception("auto_reply exception")
        try:
            await msg.edit_text(strings.text("auto_reply_exception", error=str(e)))
        except Exception:
            pass










