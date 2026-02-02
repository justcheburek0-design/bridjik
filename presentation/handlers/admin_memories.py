"""Admin handlers for memory management."""

import logging
from collections import defaultdict

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

    waiting_for_search_query = State()
    waiting_for_delete_id = State()
    waiting_for_restore_file = State()
    waiting_for_chat_selection = State()


def _format_memory_item(memory: dict, truncate_length: int = 200) -> str:
    """Format single memory item for display."""
    content = memory["content"]
    if len(content) > truncate_length:
        content = content[:truncate_length] + "..."

    memory_id = memory["id"]  # Show first 8 chars of ID
    tags_str = ", ".join(memory.get("tags", [])) if memory.get("tags") else "нет тегов"

    return f"  • ID: <code>{memory_id}</code>\n    └ {content}\n    └ Теги: {tags_str}\n"


def _get_main_keyboard() -> types.InlineKeyboardMarkup:
    """Get main menu keyboard."""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="📋 Просмотр всех", callback_data="memory_list")],
            [types.InlineKeyboardButton(text="🔍 Поиск", callback_data="memory_search")],
            [types.InlineKeyboardButton(text="❌ Удалить", callback_data="memory_delete")],
            [types.InlineKeyboardButton(text="📊 Статистика", callback_data="memory_stats")],
            [
                types.InlineKeyboardButton(text="💾 Бэкап", callback_data="memory_backup"),
                types.InlineKeyboardButton(text="🔄 Восстановить", callback_data="memory_restore"),
            ],
        ]
    )


@router.message(Command("memories"))
async def list_memories(message: types.Message, config: Config, memory_repo: MemoryRepository):
    """Show memory management menu."""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    await message.answer("<b>Управление памятью бота</b>", reply_markup=_get_main_keyboard())


@router.callback_query(F.data == "memory_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Return to main menu."""
    await callback.message.edit_text(
        "<b>Управление памятью бота</b>", reply_markup=_get_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "memory_list")
async def show_memory_list(
    callback: types.CallbackQuery, config: Config, memory_repo: MemoryRepository
):
    """Show all memories organized by chat and category."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    # Get all chats with memories
    all_memories = memory_repo._memories
    if not all_memories:
        await callback.message.edit_text(
            "🔍 Память пуста. Записей пока нет.",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]
                ]
            ),
        )
        await callback.answer()
        return

    # Build message for each chat
    text = "<b>📋 Память бота</b>\n\n"

    for chat_id, memories in all_memories.items():
        if not memories:
            continue

        text += f"💬 <b>Чат ID:</b> <code>{chat_id}</code>\n"
        text += f"   Всего записей: {len(memories)}\n\n"

        # Group by category
        categories = memory_repo.get_memory_categories(chat_id)
        for category, items in categories.items():
            text += f"📁 <b>{category}</b> ({len(items)} зап.):\n"
            for memory in items[:3]:  # Show first 3 per category
                text += _format_memory_item(memory, truncate_length=200)

            if len(items) > 3:
                text += f"   ... ещё {len(items) - 3} записей\n"
            text += "\n"

    # Truncate if too long
    if len(text) > 4000:
        text = text[:3950] + "\n\n... (список обрезан)"

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "memory_stats")
async def show_stats(callback: types.CallbackQuery, config: Config, memory_repo: MemoryRepository):
    """Show memory statistics."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    all_memories = memory_repo._memories
    if not all_memories:
        await callback.answer("Память пуста", show_alert=True)
        return

    text = "<b>📊 Статистика памяти</b>\n\n"

    total_memories = 0
    category_stats = defaultdict(int)

    for chat_id, memories in all_memories.items():
        total_memories += len(memories)
        for memory in memories:
            category_stats[memory["category"]] += 1

    text += f"💾 <b>Всего записей:</b> {total_memories}\n"
    text += f"💬 <b>Чатов с памятью:</b> {len(all_memories)}\n\n"

    text += "<b>По категориям:</b>\n"
    for category, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        text += f"  • {category}: {count}\n"

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "memory_search")
async def start_search(callback: types.CallbackQuery, state: FSMContext, config: Config):
    """Start search flow."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.set_state(MemoryStates.waiting_for_search_query)
    await callback.message.answer(
        "🔍 Введите поисковый запрос:\n"
        "(будет искать в содержимом и тегах)\n\n"
        "Отправьте /cancel для отмены",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="memory_menu")]
            ]
        ),
    )
    await callback.answer()


@router.message(MemoryStates.waiting_for_search_query)
async def process_search(message: types.Message, state: FSMContext, memory_repo: MemoryRepository):
    """Process search query."""
    query = message.text.strip()
    if not query:
        await message.answer("Запрос не может быть пустым. Попробуйте ещё раз.")
        return

    # Search across all chats
    results = []
    for chat_id in memory_repo._memories.keys():
        chat_results = memory_repo.search_memories(chat_id, query)
        for result in chat_results:
            result["chat_id"] = chat_id
            results.append(result)

    if not results:
        await message.answer(
            f'🔍 По запросу "<code>{query}</code>" ничего не найдено.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]
                ]
            ),
        )
    else:
        text = f"🔍 Найдено записей: <b>{len(results)}</b>\n"
        text += f'Запрос: "<code>{query}</code>"\n\n'

        for memory in results[:10]:  # Show first 10 results
            chat_id = memory.get("chat_id", "unknown")
            text += f"💬 Чат: <code>{chat_id}</code>\n"
            text += _format_memory_item(memory, truncate_length=200)

        if len(results) > 10:
            text += f"\n... ещё {len(results) - 10} результатов"

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]
                ]
            ),
        )

    await state.clear()


@router.callback_query(F.data == "memory_delete")
async def start_delete(callback: types.CallbackQuery, state: FSMContext, config: Config):
    """Start delete flow."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.set_state(MemoryStates.waiting_for_delete_id)
    await callback.message.answer(
        "❌ Введите ID записи для удаления\n"
        "(первые 8+ символов ID достаточно)\n\n"
        "Отправьте /cancel для отмены",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="memory_menu")]
            ]
        ),
    )
    await callback.answer()


@router.message(MemoryStates.waiting_for_delete_id)
async def process_delete(message: types.Message, state: FSMContext, memory_repo: MemoryRepository):
    """Process delete by ID."""
    partial_id = message.text.strip()
    if not partial_id:
        await message.answer("ID не может быть пустым. Попробуйте ещё раз.")
        return

    # Search for matching ID across all chats
    found = False
    for chat_id in memory_repo._memories.keys():
        memories = memory_repo.get_all_memories(chat_id)
        for memory in memories:
            if memory["id"].startswith(partial_id):
                # Found matching memory
                if memory_repo.delete_memory(chat_id, memory["id"]):
                    await message.answer(
                        f"✅ Запись удалена!\n"
                        f"ID: <code>{memory['id']}</code>\n"
                        f"Чат: <code>{chat_id}</code>\n"
                        f"Категория: {memory['category']}",
                        reply_markup=types.InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    types.InlineKeyboardButton(
                                        text="🔙 Назад", callback_data="memory_menu"
                                    )
                                ]
                            ]
                        ),
                    )
                    found = True
                    break
        if found:
            break

    if not found:
        await message.answer(
            f'❌ Запись с ID "<code>{partial_id}</code>" не найдена.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]
                ]
            ),
        )

    await state.clear()


@router.callback_query(F.data == "memory_backup")
async def backup_memories(
    callback: types.CallbackQuery, config: Config, memory_repo: MemoryRepository
):
    """Send backup file."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    file_path = config.MEMORIES_FILE
    if not file_path.exists():
        await callback.answer("Файл памяти не найден.", show_alert=True)
        return

    await callback.message.answer_document(FSInputFile(file_path), caption="💾 Бэкап памяти бота")
    await callback.answer()


@router.callback_query(F.data == "memory_restore")
async def start_restore(callback: types.CallbackQuery, state: FSMContext, config: Config):
    """Start restore flow."""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.set_state(MemoryStates.waiting_for_restore_file)
    await callback.message.answer(
        "⚠️ <b>Внимание!</b> Восстановление перезапишет текущую память.\n"
        "Отправьте файл <code>memories.json</code> для восстановления:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="memory_menu")]
            ]
        ),
    )
    await callback.answer()


@router.message(MemoryStates.waiting_for_restore_file, F.document)
async def process_restore_file(
    message: types.Message, state: FSMContext, memory_repo: MemoryRepository, bot: Bot
):
    """Process restore file."""
    if not message.document.file_name.endswith(".json"):
        await message.answer("❌ Пожалуйста, отправьте файл с расширением .json")
        return

    try:
        file = await bot.get_file(message.document.file_id)
        file_content = await bot.download_file(file.file_path)
        json_content = file_content.read().decode("utf-8")

        if memory_repo.restore_from_json(json_content):
            await message.answer(
                "✅ Память успешно восстановлена!",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]
                    ]
                ),
            )
        else:
            await message.answer("❌ Ошибка при восстановлении. Проверьте формат файла.")

    except Exception as e:
        logger.error(f"Error restoring memories: {e}")
        await message.answer("❌ Произошла ошибка при обработке файла.")

    await state.clear()


@router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    """Cancel current operation."""
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer(
        "Операция отменена.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 Назад", callback_data="memory_menu")]
            ]
        ),
    )
