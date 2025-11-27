"""Admin handlers for sticker management."""
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.config import Config
from infrastructure.repositories.stickers import StickersRepository
from presentation.keyboards import KeyboardBuilder

logger = logging.getLogger(__name__)

router = Router()


class StickerStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_sticker = State()


@router.message(Command("stickers"))
async def list_stickers(message: types.Message, config: Config, stickers_repo: StickersRepository):
    """List all stickers with management buttons."""
    
    if message.from_user.id not in config.ADMIN_IDS:
        return

    stickers = stickers_repo.get_all_stickers()
    
    if not stickers:
        await message.answer(
            "Список стикеров пуст.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Добавить стикер", callback_data="add_sticker")]
            ])
        )
        return
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить", callback_data="sticker_add")],
        [types.InlineKeyboardButton(text="✏️ Изменить", callback_data="sticker_edit_menu")],
        [types.InlineKeyboardButton(text="❌ Удалить", callback_data="sticker_delete_menu")],
        [types.InlineKeyboardButton(text="📋 Список", callback_data="sticker_list")]
    ])
    
    await message.answer("Управление стикерами:", reply_markup=kb)


@router.callback_query(F.data == "sticker_list")
async def show_sticker_list(callback: types.CallbackQuery, stickers_repo: StickersRepository):
    stickers = stickers_repo.get_all_stickers()
    if not stickers:
        await callback.message.edit_text("Список стикеров пуст.", reply_markup=callback.message.reply_markup)
        return

    text = "📋 **Список стикеров:**\n\n"
    # Sort by name
    for name in sorted(stickers.keys()):
        text += f"• <code>{name}</code>\n"
    
    # Split into chunks if too long
    if len(text) > 4000:
        # Simple truncation for now, or send as file
        text = text[:4000] + "\n...(truncated)"
    
    # Add back button
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="sticker_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "sticker_menu")
async def back_to_menu(callback: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить", callback_data="sticker_add")],
        [types.InlineKeyboardButton(text="✏️ Изменить", callback_data="sticker_edit_menu")],
        [types.InlineKeyboardButton(text="❌ Удалить", callback_data="sticker_delete_menu")],
        [types.InlineKeyboardButton(text="📋 Список", callback_data="sticker_list")]
    ])
    await callback.message.edit_text("Управление стикерами:", reply_markup=kb)


@router.callback_query(F.data == "sticker_add")
async def start_add_sticker(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(StickerStates.waiting_for_name)
    await callback.message.answer("Введите название для нового стикера:")
    await callback.answer()


@router.message(StickerStates.waiting_for_name)
async def process_sticker_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуйте еще раз.")
        return
    
    await state.update_data(name=name)
    await state.set_state(StickerStates.waiting_for_sticker)
    await message.answer(f"Отправьте стикер для названия <code>{name}</code>:")


@router.message(StickerStates.waiting_for_sticker, F.sticker)
async def process_sticker_file(message: types.Message, state: FSMContext, stickers_repo: StickersRepository):
    data = await state.get_data()
    name = data['name']
    file_id = message.sticker.file_id
    
    stickers_repo.add_sticker(name, file_id)
    await message.answer(f"✅ Стикер <code>{name}</code> успешно сохранен!")
    await state.clear()


@router.callback_query(F.data == "sticker_delete_menu")
async def delete_menu(callback: types.CallbackQuery, stickers_repo: StickersRepository):
    # Show list of stickers as buttons to delete?
    # Or ask for name?
    # If there are too many, buttons won't work well.
    # Let's ask for name for now, or maybe show top 10?
    # Let's ask for name with a message.
    
    # Actually, let's use a simple way: "Send me the name of the sticker to delete"
    # But we need a state for that.
    pass 
    # For now, let's implement a simple "Enter name to delete" flow?
    # Or maybe we can use inline query?
    
    # Let's stick to a simple state flow for deletion too.
    await callback.answer("Функция удаления пока через ввод имени.")
    # We need another state for deletion.


class StickerDeleteStates(StatesGroup):
    waiting_for_name = State()


@router.callback_query(F.data == "sticker_delete_menu")
async def start_delete_sticker(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(StickerDeleteStates.waiting_for_name)
    await callback.message.answer("Введите название стикера, который нужно удалить:")
    await callback.answer()


@router.message(StickerDeleteStates.waiting_for_name)
async def process_delete_name(message: types.Message, state: FSMContext, stickers_repo: StickersRepository):
    name = message.text.strip()
    if stickers_repo.delete_sticker(name):
        await message.answer(f"✅ Стикер <code>{name}</code> удален.")
    else:
        await message.answer(f"❌ Стикер <code>{name}</code> не найден.")
    await state.clear()


class StickerEditStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_new_sticker = State()


@router.callback_query(F.data == "sticker_edit_menu")
async def start_edit_sticker(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(StickerEditStates.waiting_for_name)
    await callback.message.answer("Введите название стикера, который нужно изменить:")
    await callback.answer()


@router.message(StickerEditStates.waiting_for_name)
async def process_edit_name(message: types.Message, state: FSMContext, stickers_repo: StickersRepository):
    name = message.text.strip()
    if not stickers_repo.get_sticker(name):
        await message.answer(f"❌ Стикер <code>{name}</code> не найден.")
        await state.clear()
        return
    
    await state.update_data(name=name)
    await state.set_state(StickerEditStates.waiting_for_new_sticker)
    await message.answer(f"Отправьте новый стикер для <code>{name}</code>:")


@router.message(StickerEditStates.waiting_for_new_sticker, F.sticker)
async def process_edit_file(message: types.Message, state: FSMContext, stickers_repo: StickersRepository):
    data = await state.get_data()
    name = data['name']
    file_id = message.sticker.file_id
    
    stickers_repo.add_sticker(name, file_id)
    await message.answer(f"✅ Стикер <code>{name}</code> обновлен!")
    await state.clear()
