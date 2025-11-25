"""AI service for completions."""
import logging
import base64
import json
from typing import Optional, List, Tuple, Any
from openai import AsyncOpenAI, RateLimitError, APIError
from aiogram import types

from domain.entities import MessageContext
from domain.interfaces import IHistoryRepository, IChatLogsRepository
from infrastructure.external.mc_api import MinecraftAPI
from infrastructure.external.mb_api import MineBridgeAPI
from utils.html_edit import remove as remove_html
from utils.message import get_message_text, get_reply_quote
from utils.chat_helpers import is_group_chat, get_author_name, get_message_id, get_replied_message_id, is_bot_message
from utils.message_formatter import (
    format_reply_message,
    format_chat_history_entry,
    format_chat_log_entry
)
import edge_tts
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Constants
HTML_FORMATTING_INSTRUCTION = (
    "\n\nВажно: Используй HTML-разметку для форматирования ответа "
    "(<b>, <i>, <code>, <s>, <u>, <pre>). MarkDown НЕЛЬЗЯ! "
    "Все ссылки вставляй сразу в текст <a href=\"\"></a>"
)
DEFAULT_ERROR_MESSAGE = "Произошла ошибка при обращении к AI. Попробуйте позже."
TEMPERATURE = 1.0


class AIService:
    """Service for AI completions."""
    
    def __init__(
        self,
        openai_client: AsyncOpenAI,
        history_repo: IHistoryRepository,
        chat_logs_repo: IChatLogsRepository,
        model: str,
        mb_api: MineBridgeAPI,
        mc_api: MinecraftAPI
    ):
        self.client = openai_client
        self.history_repo = history_repo
        self.chat_logs_repo = chat_logs_repo
        self.model = model
        self.mb_api = mb_api
        self.mc_api = mc_api
    
    async def complete(
        self,
        context: MessageContext,
        system_prompt: str,
        message: Optional[types.Message] = None,
        save_history: bool = True
    ) -> Tuple[str, Optional[dict]]:
        """Generate AI completion for given context."""
        use_thread = self._is_group_chat(message)
        full_system_prompt = system_prompt
        
        user_input = await self._build_user_input(context, use_thread, message)
        messages = self._build_messages(full_system_prompt, user_input, context, use_thread)
        tools = self._get_tools()
        
        try:
            # Agentic loop (max 10 iterations)
            for _ in range(10):
                response = await self._call_openai(messages, tools)
                response_message = response.choices[0].message
                
                # Check for tool calls
                if response_message.tool_calls:
                    # Add assistant message with tool calls to history
                    messages.append(response_message)
                    
                    # Execute tools
                    for tool_call in response_message.tool_calls:
                        tool_result = await self._execute_tool(tool_call)
                        messages.append(tool_result)
                    
                    # Continue loop to get next response from model
                    continue
                
                # No tool calls, process final response
                text, reasoning = self._process_response(response)
                
                if save_history and text and not use_thread:
                    self.history_repo.add_assistant_message(
                        context.chat.id,
                        context.user.id,
                        text,
                        reasoning_details=reasoning
                    )
                
                return text, reasoning
                
            # If loop limit reached, return what we have or error
            return DEFAULT_ERROR_MESSAGE, None
            
        except (RateLimitError, APIError) as e:
            logger.error("OpenAI completion rate limit/API error: %s", str(e), exc_info=True)
            return DEFAULT_ERROR_MESSAGE, None
    
    def _get_tools(self) -> List[dict]:
        """Get available tools definition."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_player_info",
                    "description": "Get player information from MineBridge API by nickname or Telegram ID. Use this when user asks about a player.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Player nickname or Telegram ID"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_server_status",
                    "description": "Get Minecraft server status (online, players, version, etc). Use this when user asks about server status.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
    
    async def _execute_tool(self, tool_call: Any) -> dict:
        """Execute a tool call and return the result message."""
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": name,
                "content": "Error: Invalid JSON arguments"
            }
        
        logger.info(f"Executing tool: {name} with args: {args}")
        content = "Error: Unknown tool"
        
        try:
            if name == "get_player_info":
                query = args.get("query")
                data = await self.mb_api.search_player(query)
                if data:
                    content = json.dumps(data, ensure_ascii=False)
                else:
                    content = "Player not found"
            elif name == "get_server_status":
                data = await self.mc_api.fetch_status()
                content = json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            content = f"Error executing tool: {str(e)}"
            
        return {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": name,
            "content": content
        }

    async def generate_speech(self, text: str, voice: str = "ru-RU-DmitryNeural") -> Optional[bytes]:
        """Generate speech from text using Edge TTS.
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (default: ru-RU-DmitryNeural)
                   Available Russian voices:
                   - ru-RU-DmitryNeural (male)
                   - ru-RU-SvetlanaNeural (female)
        
        Returns:
            Audio bytes in OGG format or None on error
        """
        try:
            # Generate speech to temporary file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_path = tmp_file.name
            
            try:
                # Generate speech using Edge TTS
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(tmp_path)
                
                # Read the generated audio file
                audio_bytes = Path(tmp_path).read_bytes()
                
                logger.info(f"Generated speech with Edge TTS (voice: {voice}, size: {len(audio_bytes)} bytes)")
                return audio_bytes
            finally:
                # Clean up temp file
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass
        except Exception:
            logger.exception("Failed to generate speech with Edge TTS")
            return None
    
    def _is_group_chat(self, message: Optional[types.Message]) -> bool:
        """Check if message is from a group chat.
        
        Args:
            message: Telegram message or None
            
        Returns:
            True if message is from a group chat
        """
        if message is None:
            return False
        
        chat_type = getattr(message.chat, "type", None)
        return is_group_chat(chat_type)
    
    def _build_messages(
        self,
        system_prompt: str,
        user_input: str,
        context: MessageContext,
        use_thread: bool
    ) -> List[dict]:
        """Build messages list for OpenAI API.
        
        Args:
            system_prompt: System prompt text
            user_input: User input text
            context: Message context
            
        Returns:
            List of message dictionaries
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add history for private chats
        if not use_thread:
            history = self.history_repo.get_history(context.chat.id, context.user.id)
            messages.extend(history)
        
        if context.has_image and context.image_bytes:
            user_content = [
                {"type": "text", "text": user_input},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._make_data_url(context.image_bytes, context.mime_type)
                    }
                },
            ]
        else:
            user_content = user_input
        
        messages.append({"role": "user", "content": user_content})
        return messages
    
    async def _call_openai(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Call OpenAI API."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": TEMPERATURE,
            "extra_body": {"reasoning": {"enabled": True}}
        }
        if tools:
            kwargs["tools"] = tools
            
        return await self.client.chat.completions.create(**kwargs)
    
    def _process_response(self, response: dict) -> Tuple[str, Optional[dict]]:
        """Process OpenAI API response."""
        message = response.choices[0].message
        content = message.content
        reasoning = getattr(message, "reasoning_details", None)
        
        logger.info(f"OpenAI raw response: {content!r}")
        text = (content or "").strip()
        return remove_html(text), reasoning
    
    async def _build_user_input(
        self,
        context: MessageContext,
        use_thread: bool,
        message: Optional[types.Message]
    ) -> str:
        """Build user input with history or chat context.
        
        Args:
            context: Message context
            use_thread: Whether to use thread (group chat)
            message: Telegram message
            
        Returns:
            Formatted user input string
        """
        lines: List[str] = []
        
        # Add RAG context if available
        self._add_rag_context(lines, context)
        
        # Add history or chat logs
        if use_thread and message:
            self._add_group_chat_context(lines, context, message)
        else:
            # For private chats, history is added as separate messages in _build_messages
            # We only add reply context here if present
            if message and message.reply_to_message:
                self._add_reply_message(lines, message, is_private=True)
        
        # Add current message (only if not already added as reply)
        self._add_current_message(lines, context, message)
        lines.append("Ответ:")
        
        return "\n".join(lines)
    
    def _add_rag_context(self, lines: List[str], context: MessageContext) -> None:
        """Add RAG context to lines.
        
        Args:
            lines: List to append to
            context: Message context
        """
        if context.rag_context:
            lines.append(context.rag_context)
            lines.append("")
    
    def _add_group_chat_context(
        self,
        lines: List[str],
        context: MessageContext,
        message: types.Message
    ) -> None:
        """Add group chat context to lines.
        
        Args:
            lines: List to append to
            context: Message context
            message: Telegram message
        """
        # Add reply message if present
        if message.reply_to_message:
            self._add_reply_message(lines, message, is_private=False)
        
        # Add recent messages
        recent = self.chat_logs_repo.get_recent_messages(context.chat.id, 10)
        if recent:
            lines.append("Контекст чата: последние сообщения:")
            for msg_data in recent:
                message_id, author, is_bot, text = msg_data
                lines.append(format_chat_log_entry(message_id, author, is_bot, text))
            lines.append("Конец контекста")
    
    def _add_private_chat_context(
        self,
        lines: List[str],
        context: MessageContext,
        message: Optional[types.Message]
    ) -> None:
        """Add private chat context to lines.
        
        Args:
            lines: List to append to
            context: Message context
            message: Telegram message
        """
        # Add conversation history
        history = self.history_repo.get_history(context.chat.id, context.user.id)
        if history:
            lines.append("История: последние (до 5):")
            for role, text in history:
                lines.append(format_chat_history_entry(role, text))
            lines.append("Конец истории")
        
        # Add reply message if present
        if message and message.reply_to_message:
            self._add_reply_message(lines, message, is_private=True)
    
    def _add_reply_message(
        self,
        lines: List[str],
        message: types.Message,
        is_private: bool
    ) -> None:
        """Add formatted reply message to lines.
        
        Args:
            lines: List to append to
            message: Telegram message
            is_private: Whether this is a private chat
        """
        if not message.reply_to_message:
            return

        replied_msg = message.reply_to_message
        replied_msg_id = get_message_id(replied_msg)
        
        # Get author name
        if is_private:
            author_name = "Пользователь" if not is_bot_message(replied_msg) else "Ассистент"
        else:
            author_name = get_author_name(replied_msg, "unknown")
            if is_bot_message(replied_msg):
                author_name = "Ассистент"
        
        # Get text content
        text = get_message_text(replied_msg)
        
        # If text is empty or placeholder, try to fetch from logs (for group chats)
        if (not text or text == "(пусто)") and not is_private:
            log_msg = self.chat_logs_repo.get_message_by_id(message.chat.id, replied_msg_id)
            if log_msg:
                _, _, log_text = log_msg
                if log_text:
                    text = log_text

        # Format for AI
        lines.append(f"[В ответ на сообщение от {author_name}]")
        if text and text != "(пусто)":
            lines.append(f"Текст сообщения: \"{text}\"")
        else:
            lines.append("Текст сообщения: (недоступен)")
        lines.append("[/В ответ]")
    
    def _add_current_message(
        self,
        lines: List[str],
        context: MessageContext,
        message: Optional[types.Message]
    ) -> None:
        """Add current message to lines if not already added as reply.
        
        Args:
            lines: List to append to
            context: Message context
            message: Telegram message
        """
        if message and message.reply_to_message:
            return
        
        display_name = context.user.get_display_name()
        lines.append(f"Пользователь ({display_name}): {context.prompt}")
    
    def _make_data_url(self, image_bytes: bytes, mime_type: Optional[str] = None) -> str:
        """Create data URL for image."""
        mt = (mime_type or "image/jpeg").strip().lower()
        if not mt.startswith("image/"):
            mt = f"image/{mt}" if "/" not in mt else mt
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mt};base64,{b64}"


