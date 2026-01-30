"""Admin command handlers."""

import logging

from aiogram import Router, types
from aiogram.filters import Command

from application.services.rag import RAGService
from presentation.decorators import handle_errors

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("rag_reindex"))
@handle_errors
async def cmd_rag_reindex(message: types.Message, rag_service: RAGService):
    """Handle /rag_reindex command to rebuild RAG index."""
    msg = await message.reply("🔄 <b>Перестраиваю индекс</b>...")
    try:
        await rag_service.reset_index()
        chunks = rag_service.get_chunks()
        await msg.edit_text(f"✅ <b>Готово</b>\nЧанков: {len(chunks)}")
    except Exception as e:
        logger.exception("RAG reindex error")
        await msg.edit_text(f"⚠️ Ошибка перестройки: {e}")
