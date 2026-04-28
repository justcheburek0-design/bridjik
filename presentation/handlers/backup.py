"""Backup and restore handlers for admin."""

import shutil
import tarfile
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message

from core.config import Config

router = Router(name="backup")


class RestoreStates(StatesGroup):
    waiting_for_file = State()


@router.message(Command("backup"))
async def backup_handler(message: Message, config: Config) -> None:
    """Create and send backup of /data directory."""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return

    status_msg = await message.answer("📦 Создаю бэкап...")

    try:
        data_dir = config.DATA_DIR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.tar.gz"
        backup_path = Path(f"/tmp/{backup_name}")

        # Create tar.gz archive
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(data_dir, arcname="data")

        # Send as document
        with open(backup_path, "rb") as f:
            backup_file = BufferedInputFile(f.read(), filename=backup_name)
            await message.answer_document(
                backup_file,
                caption=f"✅ Бэкап создан: {timestamp}\n"
                f"📊 Размер: {backup_path.stat().st_size / 1024:.1f} KB",
            )

        # Cleanup
        backup_path.unlink()
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка создания бэкапа: {e}")


@router.message(Command("restore"))
async def restore_start(message: Message, state: FSMContext, config: Config) -> None:
    """Start restore process."""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return

    await state.set_state(RestoreStates.waiting_for_file)
    await message.answer("📥 Отправь файл бэкапа (.tar.gz)\n\n" "Для отмены отправь /cancel")


@router.message(Command("cancel"), RestoreStates.waiting_for_file)
async def restore_cancel(message: Message, state: FSMContext) -> None:
    """Cancel restore process."""
    await state.clear()
    await message.answer("❌ Восстановление отменено")


@router.message(RestoreStates.waiting_for_file, F.document)
async def restore_process(message: Message, state: FSMContext, config: Config) -> None:
    """Process backup file."""
    doc = message.document

    if not doc.file_name.endswith(".tar.gz"):
        await message.answer("❌ Файл должен быть .tar.gz архивом")
        return

    status_msg = await message.answer("📥 Восстанавливаю бэкап...")

    backup_current = None
    try:
        # Download file
        file = await message.bot.get_file(doc.file_id)
        backup_path = Path(f"/tmp/{doc.file_name}")
        await message.bot.download_file(file.file_path, backup_path)

        # Backup current data
        data_dir = config.DATA_DIR
        backup_current = data_dir.parent / f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copytree(data_dir, backup_current)

        # Extract archive
        with tarfile.open(backup_path, "r:gz") as tar:
            # Remove old data
            shutil.rmtree(data_dir)
            # Extract new data
            tar.extractall(data_dir.parent)

        # Cleanup
        backup_path.unlink()

        await status_msg.edit_text(
            f"✅ Бэкап восстановлен!\n"
            f"📁 Старые данные сохранены в: {backup_current.name}\n"
            f"⚠️ Перезапусти бота для применения изменений"
        )

        await state.clear()

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка восстановления: {e}")
        # Restore from backup if failed
        if backup_current and backup_current.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            shutil.copytree(backup_current, data_dir)
        await state.clear()


@router.message(RestoreStates.waiting_for_file)
async def restore_invalid(message: Message) -> None:
    """Handle invalid input during restore."""
    await message.answer("❌ Отправь файл .tar.gz или /cancel для отмены")
