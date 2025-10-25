"""AI service for completions."""
import logging
import base64
from typing import Optional
from openai import AsyncOpenAI, RateLimitError, APIError
from aiogram import types
from aiogram.enums import ChatType

from domain.entities import MessageContext, User
from domain.interfaces import IHistoryRepository, IChatLogsRepository
from utils.html_edit import remove as remove_html
from utils.text import shorten


logger = logging.getLogger(__name__)


class AIService:
    """Service for AI completions."""
    
    def __init__(
        self,
        openai_client: AsyncOpenAI,
        history_repo: IHistoryRepository,
        chat_logs_repo: IChatLogsRepository,
        model: str
    ):
        self.client = openai_client
        self.history_repo = history_repo
        self.chat_logs_repo = chat_logs_repo
        self.model = model
    
    async def complete(
        self,
        context: MessageContext,
        system_prompt: str,
        message: Optional[types.Message] = None,
        save_history: bool = True
    ) -> str:
        """Generate AI completion for given context."""
        # Determine if we're in a group chat
        use_thread = False
        if message is not None:
            chat_type = getattr(message.chat, "type", None)
            if chat_type in (ChatType.GROUP, ChatType.SUPERGROUP):
                use_thread = True
        
        # Build system prompt
        full_system_prompt = system_prompt + "\n\nВажно: Используй HTML-разметку для форматирования ответа (<b>, <i>, <code>, <s>, <u>, <pre>). MarkDown НЕЛЬЗЯ! Все ссылки вставляй сразу в текст <a href=\"\"></a>"
        
        # Build user input
        user_input = await self._build_user_input(context, use_thread, message)
        
        # Prepare message content
        messages = [{"role": "system", "content": full_system_prompt}]
        
        if context.has_image and context.image_bytes:
            user_content = [
                {"type": "text", "text": user_input},
                {"type": "image_url", "image_url": {"url": self._make_data_url(context.image_bytes, context.mime_type)}},
            ]
        else:
            user_content = user_input
        
        messages.append({"role": "user", "content": user_content})
        
        # Call OpenAI
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=1,
            )
            text = (resp.choices[0].message.content or "").strip()
            text = remove_html(text)
            
            # Save to history if needed
            if save_history and text:
                if not use_thread:
                    self.history_repo.add_assistant_message(context.chat.id, context.user.id, text)
                else:
                    self.chat_logs_repo.add_message(context.chat.id, "Ассистент", True, text)
            
            return text
        except (RateLimitError, APIError) as e:
            logger.error("OpenAI completion rate limit/API error: %s", str(e), exc_info=True)
            return "Произошла ошибка при обращении к AI. Попробуйте позже."
    
    async def _build_user_input(
        self,
        context: MessageContext,
        use_thread: bool,
        message: Optional[types.Message]
    ) -> str:
        """Build user input with history or chat context."""
        lines = []
        
        # Add RAG context if available
        if context.rag_context:
            lines.append(context.rag_context)
            lines.append("")
        
        # Add history or chat logs
        if use_thread and message:
            # Group chat: recent messages
            recent = self.chat_logs_repo.get_recent_messages(context.chat.id, 12)
            if recent:
                lines.append("Контекст чата: последние сообщения:")
                for author, is_bot, text in recent:
                    role = "Ассистент" if is_bot else author
                    lines.append(f"{role}: {text}")
                lines.append("Конец контекста")
        else:
            # Private chat: conversation history
            history = self.history_repo.get_history(context.chat.id, context.user.id)
            if history:
                lines.append("История: последние (до 5):")
                for role, text in history:
                    who = "Пользователь" if role == "user" else "Ассистент"
                    lines.append(f"{who}: {text}")
                lines.append("Конец истории")
        
        # Add current message
        lines.append(f"Пользователь ({context.user.get_display_name()}): {context.prompt}")
        lines.append("Ответ:")
        
        return "\n".join(lines)
    
    def _make_data_url(self, image_bytes: bytes, mime_type: Optional[str] = None) -> str:
        """Create data URL for image."""
        mt = (mime_type or "image/jpeg").strip().lower()
        if not mt.startswith("image/"):
            mt = f"image/{mt}" if "/" not in mt else mt
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mt};base64,{b64}"

