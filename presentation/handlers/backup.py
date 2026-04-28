"""Backup and restore handlers for admin."""

import shutil
import tarfile
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from core.dependencies import Container

router = Router(name="backup")


@router.message(Command("backup"))
async def backup_handler(message: Message, container: Container) -> None:
    """Create and send backup of /data directory."""
    if message.from_user.id not in container.config.ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return

    status_msg = await message.answer("📦 Создаю бэкап...")

    try:
        data_dir = container.config.DATA_DIR
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
async def restore_handler(message: Message, container: Container) -> None:
    """Restore backup from attached file."""
    if message.from_user.id not in container.config.ADMIN_IDS:
        await message.answer("⛔ Только для администраторов")
        return

    if not message.reply_to_message or not message.reply_to_message.document:
        await message.answer("❌ Ответь на сообщение с файлом бэкапа командой /restore")
        return

    doc = message.reply_to_message.document
    if not doc.file_name.endswith(".tar.gz"):
        await message.answer("❌ Файл должен быть .tar.gz архивом")
        return

    status_msg = await message.answer("📥 Восстанавливаю бэкап...")

    try:
        # Download file
        file = await message.bot.get_file(doc.file_id)
        backup_path = Path(f"/tmp/{doc.file_name}")
        await message.bot.download_file(file.file_path, backup_path)

        # Backup current data
        data_dir = container.config.DATA_DIR
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

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка восстановления: {e}")
        # Restore from backup if failed
        if backup_current.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            shutil.copytree(backup_current, data_dir)
