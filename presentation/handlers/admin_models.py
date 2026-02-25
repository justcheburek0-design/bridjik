"""Handlers for AI model pricing management via /models command."""

import json
import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.config import Config
from infrastructure.repositories.telemetry import TelemetryRepository

logger = logging.getLogger(__name__)
router = Router()


class ModelStates(StatesGroup):
    """FSM states for model pricing management."""

    viewing = State()
    waiting_for_add = State()
    waiting_for_edit_value = State()
    waiting_for_confirm_overwrite = State()
    waiting_for_confirm_delete = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_pricing(config: Config) -> dict:
    """Load pricing data from JSON file."""
    try:
        with open(config.PRICING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_pricing(config: Config, pricing: dict) -> None:
    """Save pricing data to JSON file."""
    with open(config.PRICING_FILE, "w", encoding="utf-8") as f:
        json.dump(pricing, f, ensure_ascii=False, indent=2)


def _format_model_text(name: str, data: dict, index: int, total: int) -> str:
    """Format model info for display."""
    input_price = data.get("input_per_1m", 0)
    output_price = data.get("output_per_1m", 0)
    cache_read = data.get("cache_read_per_1m", 0)

    text = f"<b>🤖 {name}</b>\n"
    text += f"<i>{index} из {total}</i>\n\n"
    text += f"📥 Input:      <code>${input_price:.4f}</code> / 1M токенов\n"
    text += f"📤 Output:     <code>${output_price:.4f}</code> / 1M токенов\n"
    text += f"💾 Cache Read: <code>${cache_read:.4f}</code> / 1M токенов\n"
    return text


def _build_viewer_keyboard(total: int) -> types.InlineKeyboardMarkup:
    """Build navigation keyboard for model viewer."""
    nav_row = []
    if total > 1:
        nav_row.append(types.InlineKeyboardButton(text="←", callback_data="models_prev"))
    else:
        nav_row.append(types.InlineKeyboardButton(text=" ", callback_data="models_noop"))

    if total > 1:
        nav_row.append(types.InlineKeyboardButton(text="→", callback_data="models_next"))
    else:
        nav_row.append(types.InlineKeyboardButton(text=" ", callback_data="models_noop"))

    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            nav_row,
            [
                types.InlineKeyboardButton(text="✏️ Изменить", callback_data="models_edit"),
                types.InlineKeyboardButton(text="🗑️ Удалить", callback_data="models_delete"),
            ],
            [
                types.InlineKeyboardButton(text="➕ Добавить", callback_data="models_add"),
            ],
        ]
    )


def _build_empty_keyboard() -> types.InlineKeyboardMarkup:
    """Keyboard when no models exist."""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить", callback_data="models_add")]
        ]
    )


async def _show_models_view(
    message_or_callback,
    config: Config,
    state: FSMContext,
    edit: bool = True,
) -> None:
    """Show model slider view."""
    data = await state.get_data()
    index = data.get("models_index", 0)

    pricing = _load_pricing(config)
    items = list(pricing.items())

    if not items:
        text = "<b>🤖 Модели прайсинга</b>\n\n📭 Нет моделей"
        kb = _build_empty_keyboard()
    else:
        index = max(0, min(index, len(items) - 1))
        await state.update_data(models_index=index)
        name, model_data = items[index]
        text = _format_model_text(name, model_data, index + 1, len(items))
        kb = _build_viewer_keyboard(len(items))

    await state.set_state(ModelStates.viewing)

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


def _parse_model_input(parts: list) -> tuple | None:
    """Parse model input: name input output cache_read.
    Returns (name, input, output, cache_read) or None on error.
    """
    if len(parts) != 4:
        return None
    try:
        return parts[0], float(parts[1]), float(parts[2]), float(parts[3])
    except ValueError:
        return None


def _build_model_dict(input_price, output_price, cache_read) -> dict:
    return {
        "input_per_1m": input_price,
        "output_per_1m": output_price,
        "cache_read_per_1m": cache_read,
    }


ADD_HELP = (
    "Введите одной строкой:\n"
    "<code>название input output cache_read</code>\n\n"
    "<b>Пример:</b>\n"
    "<code>x-ai/grok-4.1-fast 0.2 0.5 0.05</code>\n\n"
    "• <code>cache_read</code> — цена за кэш-чтение ($/1M токенов)"
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@router.message(Command("models"))
async def cmd_models(message: types.Message, config: Config, state: FSMContext):
    """Show model pricing manager (admin only)."""
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.update_data(models_index=0)
    await _show_models_view(message, config, state, edit=False)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "models_prev", ModelStates.viewing)
async def models_prev(callback: types.CallbackQuery, config: Config, state: FSMContext):
    data = await state.get_data()
    index = data.get("models_index", 0)
    pricing = _load_pricing(config)
    total = len(pricing)
    if total > 0:
        await state.update_data(models_index=(index - 1) % total)
    await _show_models_view(callback, config, state, edit=True)


@router.callback_query(F.data == "models_next", ModelStates.viewing)
async def models_next(callback: types.CallbackQuery, config: Config, state: FSMContext):
    data = await state.get_data()
    index = data.get("models_index", 0)
    pricing = _load_pricing(config)
    total = len(pricing)
    if total > 0:
        await state.update_data(models_index=(index + 1) % total)
    await _show_models_view(callback, config, state, edit=True)


@router.callback_query(F.data == "models_noop")
async def models_noop(callback: types.CallbackQuery):
    await callback.answer()


# ---------------------------------------------------------------------------
# Add model
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "models_add", ModelStates.viewing)
async def models_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ModelStates.waiting_for_add)
    await callback.message.answer(
        f"➕ <b>Добавить модель</b>\n\n{ADD_HELP}",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отмена", callback_data="models_cancel_add")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "models_cancel_add")
async def models_cancel_add(callback: types.CallbackQuery, config: Config, state: FSMContext):
    await _show_models_view(callback, config, state, edit=True)


@router.message(ModelStates.waiting_for_add)
async def models_process_add(
    message: types.Message,
    config: Config,
    state: FSMContext,
    telemetry_repo: TelemetryRepository,
):
    parsed = _parse_model_input(message.text.strip().split())
    if not parsed:
        await message.answer(f"❌ Неверный формат.\n\n{ADD_HELP}", parse_mode="HTML")
        return

    name, input_price, output_price, cache_read = parsed
    pricing = _load_pricing(config)

    if name in pricing:
        existing = pricing[name]
        await state.update_data(
            pending_model_name=name,
            pending_input=input_price,
            pending_output=output_price,
            pending_cache_read=cache_read,
        )
        await state.set_state(ModelStates.waiting_for_confirm_overwrite)
        await message.answer(
            f"⚠️ Модель <b>{name}</b> уже существует.\n\n"
            f"Текущие цены:\n"
            f"📥 Input: <code>${existing.get('input_per_1m', 0):.4f}</code>\n"
            f"📤 Output: <code>${existing.get('output_per_1m', 0):.4f}</code>\n"
            f"💾 Cache Read: <code>${existing.get('cache_read_per_1m', 0):.4f}</code>\n\n"
            f"Обновить цены?",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="✅ Да, обновить", callback_data="models_confirm_overwrite"
                        ),
                        types.InlineKeyboardButton(
                            text="❌ Нет", callback_data="models_cancel_overwrite"
                        ),
                    ]
                ]
            ),
        )
        return

    pricing[name] = _build_model_dict(input_price, output_price, cache_read)
    _save_pricing(config, pricing)
    telemetry_repo.reload_pricing()
    items = list(pricing.keys())
    await state.update_data(models_index=items.index(name))
    await message.answer(f"✅ Модель <b>{name}</b> добавлена!", parse_mode="HTML")
    await _show_models_view(message, config, state, edit=False)


@router.callback_query(
    F.data == "models_confirm_overwrite", ModelStates.waiting_for_confirm_overwrite
)
async def models_confirm_overwrite(
    callback: types.CallbackQuery,
    config: Config,
    state: FSMContext,
    telemetry_repo: TelemetryRepository,
):
    data = await state.get_data()
    name = data.get("pending_model_name")
    if not name:
        await callback.answer("Ошибка состояния", show_alert=True)
        return

    pricing = _load_pricing(config)
    pricing[name] = _build_model_dict(
        data.get("pending_input", 0),
        data.get("pending_output", 0),
        data.get("pending_cache_read", 0),
    )
    _save_pricing(config, pricing)
    telemetry_repo.reload_pricing()
    items = list(pricing.keys())
    await state.update_data(models_index=items.index(name))
    await callback.message.answer(f"✅ Цены модели <b>{name}</b> обновлены!", parse_mode="HTML")
    await _show_models_view(callback.message, config, state, edit=False)
    await callback.answer()


@router.callback_query(F.data == "models_cancel_overwrite")
async def models_cancel_overwrite(callback: types.CallbackQuery, config: Config, state: FSMContext):
    await callback.message.answer("Добавление отменено.")
    await _show_models_view(callback.message, config, state, edit=False)
    await callback.answer()


# ---------------------------------------------------------------------------
# Edit model
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "models_edit", ModelStates.viewing)
async def models_edit_start(callback: types.CallbackQuery, config: Config, state: FSMContext):
    data = await state.get_data()
    index = data.get("models_index", 0)
    pricing = _load_pricing(config)
    items = list(pricing.items())

    if not items:
        await callback.answer("Нет моделей для редактирования", show_alert=True)
        return

    index = max(0, min(index, len(items) - 1))
    name, model_data = items[index]

    await state.update_data(editing_model_name=name)
    await state.set_state(ModelStates.waiting_for_edit_value)

    await callback.message.answer(
        f"✏️ <b>Редактирование:</b> <code>{name}</code>\n\n"
        f"Текущие значения:\n"
        f"📥 Input: <code>${model_data.get('input_per_1m', 0):.4f}</code>\n"
        f"📤 Output: <code>${model_data.get('output_per_1m', 0):.4f}</code>\n"
        f"💾 Cache Read: <code>${model_data.get('cache_read_per_1m', 0):.4f}</code>\n\n"
        f"Введите новые значения:\n"
        f"<code>{name} input output cache_read</code>",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отмена", callback_data="models_cancel_edit")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "models_cancel_edit")
async def models_cancel_edit(callback: types.CallbackQuery, config: Config, state: FSMContext):
    await _show_models_view(callback, config, state, edit=True)


@router.message(ModelStates.waiting_for_edit_value)
async def models_process_edit(
    message: types.Message,
    config: Config,
    state: FSMContext,
    telemetry_repo: TelemetryRepository,
):
    parsed = _parse_model_input(message.text.strip().split())
    if not parsed:
        await message.answer(f"❌ Неверный формат.\n\n{ADD_HELP}", parse_mode="HTML")
        return

    name, input_price, output_price, cache_read = parsed
    data = await state.get_data()
    editing_name = data.get("editing_model_name")

    pricing = _load_pricing(config)
    if editing_name and editing_name != name and editing_name in pricing:
        del pricing[editing_name]

    pricing[name] = _build_model_dict(input_price, output_price, cache_read)
    _save_pricing(config, pricing)
    telemetry_repo.reload_pricing()

    items = list(pricing.keys())
    await state.update_data(models_index=items.index(name) if name in items else 0)
    await message.answer(f"✅ Модель <b>{name}</b> обновлена!", parse_mode="HTML")
    await _show_models_view(message, config, state, edit=False)


# ---------------------------------------------------------------------------
# Delete model
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "models_delete", ModelStates.viewing)
async def models_delete_start(callback: types.CallbackQuery, config: Config, state: FSMContext):
    data = await state.get_data()
    index = data.get("models_index", 0)
    pricing = _load_pricing(config)
    items = list(pricing.items())

    if not items:
        await callback.answer("Нет моделей для удаления", show_alert=True)
        return

    index = max(0, min(index, len(items) - 1))
    name, model_data = items[index]

    await state.update_data(deleting_model_name=name)
    await state.set_state(ModelStates.waiting_for_confirm_delete)

    await callback.message.answer(
        f"🗑️ Удалить модель <b>{name}</b>?\n\n"
        f"📥 Input: <code>${model_data.get('input_per_1m', 0):.4f}</code>\n"
        f"📤 Output: <code>${model_data.get('output_per_1m', 0):.4f}</code>\n"
        f"💾 Cache Read: <code>${model_data.get('cache_read_per_1m', 0):.4f}</code>",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="✅ Да, удалить", callback_data="models_confirm_delete"
                    ),
                    types.InlineKeyboardButton(text="❌ Нет", callback_data="models_cancel_delete"),
                ]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "models_confirm_delete", ModelStates.waiting_for_confirm_delete)
async def models_confirm_delete(
    callback: types.CallbackQuery,
    config: Config,
    state: FSMContext,
    telemetry_repo: TelemetryRepository,
):
    data = await state.get_data()
    name = data.get("deleting_model_name")
    if not name:
        await callback.answer("Ошибка состояния", show_alert=True)
        return

    pricing = _load_pricing(config)
    if name in pricing:
        del pricing[name]
        _save_pricing(config, pricing)
        telemetry_repo.reload_pricing()
        await callback.message.answer(f"✅ Модель <b>{name}</b> удалена!", parse_mode="HTML")
    else:
        await callback.message.answer(f"⚠️ Модель <b>{name}</b> не найдена.", parse_mode="HTML")

    new_index = max(0, data.get("models_index", 0) - 1)
    await state.update_data(models_index=new_index)
    await _show_models_view(callback.message, config, state, edit=False)
    await callback.answer()


@router.callback_query(F.data == "models_cancel_delete")
async def models_cancel_delete(callback: types.CallbackQuery, config: Config, state: FSMContext):
    await _show_models_view(callback, config, state, edit=True)
