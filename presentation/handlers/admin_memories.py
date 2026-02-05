"""Handlers for memory viewing and management."""

import logging

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile

from core.config import Config
from infrastructure.repositories.memories import MemoryRepository

logger = logging.getLogger(__name__)
router = Router()


class MemoryStates(StatesGroup):
    """FSM states for memory management."""

    # Admin states
    admin_viewing = State()  # scope: "chats"/"users", index: int
    waiting_for_search_query = State()
    waiting_for_delete_id = State()
    waiting_for_restore_file = State()

    # User states
    user_viewing = State()  # scope: "chat"/"me"


def _format_memory_list(memories: list, max_show: int = 100) -> str:
    """Format memories as numbered list."""
    if not memories:
        return "📭 Записей нет\n"

    text = ""
    for idx, memory in enumerate(memories[:max_show], 1):
        content = memory["content"]
        if len(content) > 100:
            content = content[:97] + "..."
        text += f"{idx}. {content}\n"

    if len(memories) > max_show:
        text += f"\n... ещё {len(memories) - max_show} записей"

    return text


@router.message(Command("memories"))
async def show_memories(
    message: types.Message, config: Config, memory_repo: MemoryRepository, state: FSMContext
):
    """Show memories based on user role."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    is_admin = user_id in config.ADMIN_IDS

    if is_admin:
        # Admin view: show first chat
        await state.update_data(scope="chats", index=0)
        await state.set_state(MemoryStates.admin_viewing)
        await _show_admin_view(message, memory_repo, state, edit=False)
    else:
        # Regular user view: show chat memory by default
        await state.update_data(scope="chat", chat_id=chat_id, user_id=user_id)
        await state.set_state(MemoryStates.user_viewing)
        await _show_user_view(message, memory_repo, state, edit=False)


async def _show_admin_view(
    message_or_callback, memory_repo: MemoryRepository, state: FSMContext, edit: bool = True
):
    """Show admin memory view with slider [<] [Toggle] [>]."""
    data = await state.get_data()
    scope = data.get("scope", "chats")
    index = data.get("index", 0)

    if scope == "chats":
        items = list(memory_repo._memories.get("chats", {}).items())
        scope_icon = "💬"
        scope_label = "Чаты"
        toggle_text = "Пользователи"
        toggle_callback = "admin_toggle_users"
    else:  # users
        items = list(memory_repo._memories.get("users", {}).items())
        scope_icon = "👤"
        scope_label = "Пользователи"
        toggle_text = "Чаты"
        toggle_callback = "admin_toggle_chats"

    if not items:
        text = f"<b>{scope_icon} {scope_label}</b>\n\n📭 Нет записей"
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback)]
            ]
        )
    else:
        # Ensure index is in bounds
        if index >= len(items):
            index = len(items) - 1
        if index < 0:
            index = 0

        scope_id, memories = items[index]

        text = f"<b>{scope_icon} ID: <code>{scope_id}</code></b>\n"
        text += f"<i>{index + 1} из {len(items)}</i>\n\n"
        text += _format_memory_list(memories)

        # Build navigation buttons
        nav_buttons = []

        # Left arrow
        if len(items) > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="←", callback_data="admin_prev"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="noop"))

        # Toggle center
        nav_buttons.append(
            types.InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback)
        )

        # Right arrow
        if len(items) > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="→", callback_data="admin_next"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="noop"))

        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                nav_buttons,
                [
                    types.InlineKeyboardButton(text="🔍 Поиск", callback_data="memory_search"),
                    types.InlineKeyboardButton(text="❌ Удалить", callback_data="memory_delete"),
                ],
                [
                    types.InlineKeyboardButton(text="💾 Бэкап", callback_data="memory_backup"),
                    types.InlineKeyboardButton(
                        text="🔄 Восстановить", callback_data="memory_restore"
                    ),
                ],
            ]
        )

        # Update index in state
        await state.update_data(index=index)

    if edit and isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await message_or_callback.answer()
    else:
        msg = (
            message_or_callback
            if isinstance(message_or_callback, types.Message)
            else message_or_callback.message
        )
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


async def _show_user_view(
    message_or_callback, memory_repo: MemoryRepository, state: FSMContext, edit: bool = True
):
    """Show regular user memory view with toggle."""
    data = await state.get_data()
    scope = data.get("scope", "chat")
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")

    if scope == "chat":
        memories = memory_repo.get_chat_memories(chat_id)
        text = f"<b>💬 Память чата <code>{chat_id}</code></b>\n\n"
        text += _format_memory_list(memories)
        toggle_text = "Обо мне"
        toggle_callback = "user_toggle_me"
    else:  # me
        memories = memory_repo.get_user_memories(user_id)
        text = f"<b>👤 Ваш ID: <code>{user_id}</code></b>\n\n"
        text += _format_memory_list(memories)
        toggle_text = "Память чата"
        toggle_callback = "user_toggle_chat"

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback)]
        ]
    )

    if edit and isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await message_or_callback.answer()
    else:
        msg = (
            message_or_callback
            if isinstance(message_or_callback, types.Message)
            else message_or_callback.message
        )
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


# Admin navigation callbacks
@router.callback_query(F.data == "admin_prev", MemoryStates.admin_viewing)
async def admin_prev(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Navigate to previous item."""
    data = await state.get_data()
    index = data.get("index", 0)
    scope = data.get("scope", "chats")

    items = list(memory_repo._memories.get(scope, {}).items())
    new_index = (index - 1) % len(items) if items else 0

    await state.update_data(index=new_index)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.callback_query(F.data == "admin_next", MemoryStates.admin_viewing)
async def admin_next(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Navigate to next item."""
    data = await state.get_data()
    index = data.get("index", 0)
    scope = data.get("scope", "chats")

    items = list(memory_repo._memories.get(scope, {}).items())
    new_index = (index + 1) % len(items) if items else 0

    await state.update_data(index=new_index)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.callback_query(F.data == "admin_toggle_chats")
async def admin_toggle_chats(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Toggle to chats view."""
    await state.update_data(scope="chats", index=0)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.callback_query(F.data == "admin_toggle_users")
async def admin_toggle_users(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Toggle to users view."""
    await state.update_data(scope="users", index=0)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    """No-op callback for disabled buttons."""
    await callback.answer()


# User toggle callbacks
@router.callback_query(F.data == "user_toggle_chat", MemoryStates.user_viewing)
async def user_toggle_chat(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Toggle to chat view."""
    await state.update_data(scope="chat")
    await _show_user_view(callback, memory_repo, state, edit=True)


@router.callback_query(F.data == "user_toggle_me", MemoryStates.user_viewing)
async def user_toggle_me(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Toggle to user view."""
    await state.update_data(scope="me")
    await _show_user_view(callback, memory_repo, state, edit=True)


# Admin actions
@router.callback_query(F.data == "memory_search")
async def start_search(callback: types.CallbackQuery, state: FSMContext, config: Config):
    """Start search flow."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.set_state(MemoryStates.waiting_for_search_query)
    await callback.message.answer(
        "🔍 <b>Поиск</b>\nВведите запрос:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_search")
async def cancel_search(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Cancel search."""
    await state.set_state(MemoryStates.admin_viewing)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.message(MemoryStates.waiting_for_search_query)
async def process_search(message: types.Message, state: FSMContext, memory_repo: MemoryRepository):
    """Process search query."""
    query = message.text.strip()

    results = []

    # Search in chats
    for chat_id in memory_repo._memories.get("chats", {}).keys():
        matches = memory_repo.search_memories("chat", chat_id, query)
        for m in matches:
            results.append((f"💬 {chat_id}", m))

    # Search in users
    for user_id in memory_repo._memories.get("users", {}).keys():
        matches = memory_repo.search_memories("user", user_id, query)
        for m in matches:
            results.append((f"👤 {user_id}", m))

    if not results:
        text = f"Ничего не найдено по запросу '<code>{query}</code>'"
    else:
        text = f"🔍 <b>Найдено {len(results)} записей</b>:\n\n"
        for label, m in results[:15]:
            content = m["content"]
            if len(content) > 80:
                content = content[:77] + "..."
            text += f"{label}: {content}\n"

        if len(results) > 15:
            text += f"\n... ещё {len(results) - 15}"

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_view")]
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await state.set_state(MemoryStates.admin_viewing)


@router.callback_query(F.data == "back_to_view")
async def back_to_view(
    callback: types.CallbackQuery, memory_repo: MemoryRepository, state: FSMContext
):
    """Return to admin view."""
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.callback_query(F.data == "memory_delete")
async def start_delete(callback: types.CallbackQuery, state: FSMContext, config: Config):
    """Start delete flow."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.set_state(MemoryStates.waiting_for_delete_id)
    await callback.message.answer(
        "❌ <b>Удаление</b>\nВведите ID записи:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Cancel delete."""
    await state.set_state(MemoryStates.admin_viewing)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.message(MemoryStates.waiting_for_delete_id)
async def process_delete(message: types.Message, state: FSMContext, memory_repo: MemoryRepository):
    """Process delete by ID."""
    mem_id = message.text.strip()
    deleted = False

    # Try delete from chats
    for chat_id in list(memory_repo._memories.get("chats", {}).keys()):
        for m in memory_repo.get_chat_memories(chat_id):
            if m["id"].startswith(mem_id):
                memory_repo.delete_memory("chat", chat_id, m["id"])
                deleted = True
                break

    # Try delete from users
    if not deleted:
        for user_id in list(memory_repo._memories.get("users", {}).keys()):
            for m in memory_repo.get_user_memories(user_id):
                if m["id"].startswith(mem_id):
                    memory_repo.delete_memory("user", user_id, m["id"])
                    deleted = True
                    break

    text = "✅ Удалено" if deleted else f"❌ ID '{mem_id}' не найден"

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_view")]
        ]
    )

    await message.answer(text, reply_markup=kb)
    await state.set_state(MemoryStates.admin_viewing)


@router.callback_query(F.data == "memory_backup")
async def backup_memories(callback: types.CallbackQuery, config: Config):
    """Send backup file."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    if not config.MEMORIES_FILE.exists():
        await callback.answer("Файл не найден", show_alert=True)
        return

    await callback.message.answer_document(FSInputFile(config.MEMORIES_FILE), caption="💾 Бэкап")
    await callback.answer()


@router.callback_query(F.data == "memory_restore")
async def start_restore(callback: types.CallbackQuery, state: FSMContext, config: Config):
    """Start restore flow."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.set_state(MemoryStates.waiting_for_restore_file)
    await callback.message.answer(
        "⚠️ <b>Восстановление</b>\nОтправьте файл .json:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_restore")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_restore")
async def cancel_restore(
    callback: types.CallbackQuery, state: FSMContext, memory_repo: MemoryRepository
):
    """Cancel restore."""
    await state.set_state(MemoryStates.admin_viewing)
    await _show_admin_view(callback, memory_repo, state, edit=True)


@router.message(MemoryStates.waiting_for_restore_file, F.document)
async def process_restore_file(
    message: types.Message, state: FSMContext, memory_repo: MemoryRepository, bot: Bot
):
    """Process restore file."""
    if not message.document.file_name.endswith(".json"):
        await message.answer("❌ Нужен .json файл")
        return

    try:
        file = await bot.get_file(message.document.file_id)
        file_content = await bot.download_file(file.file_path)
        json_content = file_content.read().decode("utf-8")

        if memory_repo.restore_from_json(json_content):
            text = "✅ Восстановлено"
        else:
            text = "❌ Ошибка"

    except Exception as e:
        logger.error(f"Restore error: {e}")
        text = "❌ Ошибка"

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_view")]
        ]
    )

    await message.answer(text, reply_markup=kb)
    await state.set_state(MemoryStates.admin_viewing)
