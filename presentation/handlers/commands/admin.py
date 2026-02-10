"""Admin command handlers."""

import logging

from aiogram import Router

# RAG disabled - all commands commented out
# To restore: uncomment RAGService import and cmd_rag_reindex handler below

# from application.services.rag import RAGService  # RAG disabled

logger = logging.getLogger(__name__)

router = Router()  # Empty router for compatibility


# @router.message(Command("rag_reindex"))  # RAG disabled - uncomment to enable
# @handle_errors
# async def cmd_rag_reindex(message: types.Message, rag_service: RAGService):
#     """Handle /rag_reindex command to rebuild RAG index."""
#     msg = await message.reply("🔄 <b>Перестраиваю индекс</b>...")
#     try:
#         await rag_service.reset_index()
#         chunks = rag_service.get_chunks()
#         await msg.edit_text(f"✅ <b>Готово</b>\nЧанков: {len(chunks)}")
#     except Exception as e:
#         logger.exception("RAG reindex error")
#         await msg.edit_text(f"⚠️ Ошибка перестройки: {e}")
