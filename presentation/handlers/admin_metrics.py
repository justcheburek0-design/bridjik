"""metrics admin handlers for telemetry."""

import logging
from io import BytesIO

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.config import Config
from infrastructure.repositories.telemetry import TelemetryRepository

logger = logging.getLogger(__name__)

router = Router()


class metricsStates(StatesGroup):
    waiting_for_restore_file = State()


@router.message(Command("metrics"))
async def cmd_metrics(message: types.Message, config: Config, telemetry_repo: TelemetryRepository):
    """Display telemetry metrics for admins."""

    if message.from_user.id not in config.ADMIN_IDS:
        return

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📊 Общая статистика", callback_data="metrics_overview"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="👥 Топ пользователей", callback_data="metrics_top_users"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🤖 Статистика моделей", callback_data="metrics_models"
                )
            ],
            [
                types.InlineKeyboardButton(text="💾 Бэкап", callback_data="metrics_backup"),
                types.InlineKeyboardButton(text="🔄 Восстановить", callback_data="metrics_restore"),
            ],
        ]
    )

    await message.answer("<b>📈 Аналитика телеметрии</b>", reply_markup=kb)


@router.callback_query(F.data == "metrics_menu")
async def back_to_menu(callback: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📊 Общая статистика", callback_data="metrics_overview"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="👥 Топ пользователей", callback_data="metrics_top_users"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🤖 Статистика моделей", callback_data="metrics_models"
                )
            ],
            [
                types.InlineKeyboardButton(text="💾 Бэкап", callback_data="metrics_backup"),
                types.InlineKeyboardButton(text="🔄 Восстановить", callback_data="metrics_restore"),
            ],
        ]
    )
    await callback.message.edit_text("<b>📈 Аналитика телеметрии</b>", reply_markup=kb)


@router.callback_query(F.data == "metrics_overview")
async def show_overview(callback: types.CallbackQuery, telemetry_repo: TelemetryRepository):
    """Display overall statistics."""

    # Get stats for 3 hours and 24 hours
    stats_3h = telemetry_repo.get_overall_stats(hours=3)
    stats_24h = telemetry_repo.get_overall_stats(hours=24)

    text = "<b>📊 Общая статистика</b>\n\n"

    # 3 hours stats
    text += "<b>За последние 3 часа:</b>\n"
    text += f"📨 Запросов: {stats_3h['requests']:,}\n"
    text += f"🪙 Токенов: {stats_3h['tokens_total']:,}\n"
    text += f"💵 Стоимость: ${stats_3h['cost_usd']:.6f}\n"
    text += f"👥 Пользователей: {stats_3h['unique_users']}\n"
    text += f"📊 Среднее токенов/запрос: {stats_3h['avg_tokens_per_request']:,}\n"
    text += f"⏱ Средняя latency: {stats_3h['avg_latency_ms']}ms\n"

    text += "\n<b>За последние 24 часа:</b>\n"
    text += f"📨 Запросов: {stats_24h['requests']:,}\n"
    text += f"🪙 Токенов: {stats_24h['tokens_total']:,}\n"
    text += f"💵 Стоимость: ${stats_24h['cost_usd']:.6f}\n"
    text += f"👥 Пользователей: {stats_24h['unique_users']}\n"
    text += f"📊 Среднее токенов/запрос: {stats_24h['avg_tokens_per_request']:,}\n"
    text += f"⏱ Средняя latency: {stats_24h['avg_latency_ms']}ms\n"

    # Back button
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="metrics_menu")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "metrics_top_users")
async def show_top_users(callback: types.CallbackQuery, telemetry_repo: TelemetryRepository):
    """Display top users by token usage and cost."""

    top_by_tokens = telemetry_repo.get_top_offenders(limit=10, hours=3, by="tokens")
    top_by_cost = telemetry_repo.get_top_offenders(limit=10, hours=3, by="cost")

    text = "<b>👥 Топ пользователей (за 3 часа)</b>\n\n"

    text += "<b>По токенам:</b>\n"
    if top_by_tokens:
        for i, user in enumerate(top_by_tokens, 1):
            text += (
                f"{i}. ID {user['user_id']}: {user['tokens_total']:,} токенов "
                f"(${user['cost_usd']:.4f}, {user['requests']} запросов)\n"
            )
    else:
        text += "Нет данных\n"

    text += "\n<b>По стоимости:</b>\n"
    if top_by_cost:
        for i, user in enumerate(top_by_cost, 1):
            text += (
                f"{i}. ID {user['user_id']}: ${user['cost_usd']:.4f} "
                f"({user['tokens_total']:,} токенов, {user['requests']} запросов)\n"
            )
    else:
        text += "Нет данных\n"

    # Back button
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="metrics_menu")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "metrics_models")
async def show_models(callback: types.CallbackQuery, telemetry_repo: TelemetryRepository):
    """Display statistics by model."""

    models = telemetry_repo.get_model_stats(hours=3)

    text = "<b>🤖 Статистика по моделям (за 3 часа)</b>\n\n"

    if models:
        for model in models:
            text += f"<b>{model['model']}</b>\n"
            text += f"  📨 Запросов: {model['requests']}\n"
            text += f"  🪙 Токенов: {model['tokens_total']:,}\n"
            text += f"  💵 Стоимость: ${model['cost_usd']:.6f}\n"
            text += f"  ⏱ Средняя latency: {model['avg_latency_ms']}ms\n\n"
    else:
        text += "Нет данных"

    # Back button
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="metrics_menu")]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "metrics_backup")
async def backup_telemetry(callback: types.CallbackQuery, telemetry_repo: TelemetryRepository):
    """Export telemetry data as JSON."""

    import json

    try:
        metrics = telemetry_repo.get_all_metrics()

        # Create JSON file in memory
        json_data = json.dumps(metrics, ensure_ascii=False, indent=2)
        file_bytes = BytesIO(json_data.encode("utf-8"))
        file_bytes.name = "telemetry.json"

        await callback.message.answer_document(
            types.BufferedInputFile(file_bytes.getvalue(), filename="telemetry.json"),
            caption=f"💾 Бэкап телеметрии ({len(metrics)} записей)",
        )
        await callback.answer("Бэкап создан!")
    except Exception as e:
        logger.exception("Failed to create telemetry backup")
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data == "metrics_restore")
async def start_restore_telemetry(callback: types.CallbackQuery, state: FSMContext):
    """Start telemetry restore flow."""

    await state.set_state(metricsStates.waiting_for_restore_file)
    await callback.message.answer(
        "⚠️ <b>Внимание!</b> Восстановление перезапишет текущие данные телеметрии.\n"
        "Отправьте файл <code>telemetry.json</code> для восстановления:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="metrics_menu")]
            ]
        ),
    )
    await callback.answer()


@router.message(metricsStates.waiting_for_restore_file, F.document)
async def process_restore_file(
    message: types.Message, state: FSMContext, telemetry_repo: TelemetryRepository, bot: Bot
):
    """Process restore file."""

    if not message.document.file_name.endswith(".json"):
        await message.answer("❌ Пожалуйста, отправьте файл с расширением .json")
        return

    try:
        file = await bot.get_file(message.document.file_id)
        file_content = await bot.download_file(file.file_path)
        json_content = file_content.read().decode("utf-8")

        if telemetry_repo.restore_from_json(json_content):
            await message.answer("✅ Телеметрия успешно восстановлена!")
        else:
            await message.answer("❌ Ошибка при восстановлении. Проверьте формат файла.")

    except Exception as e:
        logger.error(f"Error restoring telemetry: {e}")
        await message.answer("❌ Произошла ошибка при обработке файла.")

    await state.clear()
