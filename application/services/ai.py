"""AI service for completions."""

import base64
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional, Tuple

import httpx
from aiogram import types
from openai import APIError, AsyncOpenAI, RateLimitError

from core.config import Config
from domain.entities import MessageContext
from domain.interfaces import IChatLogsRepository, IHistoryRepository
from infrastructure.external.mb_api import MineBridgeAPI
from infrastructure.external.mc_api import MinecraftAPI
from utils.chat_helpers import (
    get_author_name,
    get_message_id,
    get_replied_message_id,
    is_bot_message,
    is_group_chat,
)
from utils.html_edit import remove as remove_html
from utils.message import get_message_text, get_reply_quote
from utils.message_formatter import (
    format_chat_history_entry,
    format_chat_log_entry,
)

logger = logging.getLogger(__name__)

# Constants
DEFAULT_ERROR_MESSAGE = "Произошла ошибка при обращении к AI. Попробуйте позже."
TEMPERATURE = 0.7


class AIService:
    """Service for AI completions."""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        history_repo: IHistoryRepository,
        chat_logs_repo: IChatLogsRepository,
        model: str,
        mb_api: MineBridgeAPI,
        mc_api: MinecraftAPI,
        news_api,
        tavily_api,
        config: Config,
        stickers_repo,
    ):
        self.client = openai_client
        self.history_repo = history_repo
        self.chat_logs_repo = chat_logs_repo
        self.model = model
        self.mb_api = mb_api
        self.mc_api = mc_api
        self.news_api = news_api
        self.tavily_api = tavily_api
        self.config = config
        self.stickers_repo = stickers_repo

    async def complete(
        self,
        context: MessageContext,
        system_prompt: str,
        message: Optional[types.Message] = None,
        on_tool_update: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """Generate AI completion for given context."""
        full_system_prompt = system_prompt

        user_input = await self._build_user_input(context, message)
        messages = self._build_messages(full_system_prompt, user_input, context)
        tools = self._get_tools()

        try:
            # Agentic loop (max 10 iterations)
            for _ in range(10):
                response = await self._call_openai(messages, tools)
                response_message = response.choices[0].message

                # Check for tool calls
                # Update status if AI provided content
                if response_message.content and on_tool_update:
                    try:
                        await on_tool_update(response_message.content)
                    except Exception:
                        logger.warning("Failed to update tool status", exc_info=True)

                # Check for tool calls
                if response_message.tool_calls:
                    # Add assistant message with tool calls to history
                    messages.append(response_message)

                    # Update status if AI provided content
                    if response_message.content and on_tool_update:
                        try:
                            await on_tool_update(response_message.content)
                        except Exception:
                            logger.warning("Failed to update tool status", exc_info=True)

                    # Execute tools
                    for tool_call in response_message.tool_calls:
                        tool_result = await self._execute_tool(tool_call)
                        messages.append(tool_result)

                    # Continue loop to get next response from model
                    continue

                # No tool calls, process final response
                text = self._process_response(response)

                return text

            # If loop limit reached, return what we have or error
            return DEFAULT_ERROR_MESSAGE

        except (RateLimitError, APIError) as e:
            logger.error("OpenAI completion rate limit/API error: %s", str(e), exc_info=True)
            return DEFAULT_ERROR_MESSAGE

    def _get_tools(self) -> List[dict]:
        """Get available tools definition."""
        try:
            with open(self.config.TOOLS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load tools from {self.config.TOOLS_FILE}: {e}")
            return []

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
                "content": "Error: Invalid JSON arguments",
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
            elif name == "get_stickers":
                stickers = list(self.stickers_repo.get_all_stickers().keys())
                content = f"Available stickers: {', '.join(stickers)}"
            elif name == "get_news":
                limit = min(args.get("limit", 5), 15)
                offset = args.get("offset", 0)
                news_data = await self.news_api.fetch_news(limit, offset)
                if news_data:
                    content = json.dumps(news_data, ensure_ascii=False)
                else:
                    content = "Failed to fetch news"
            elif name == "get_events":
                season = args.get("season", -1)
                events_data = await self.mb_api.fetch_events(season)
                if events_data:
                    content = json.dumps(events_data, ensure_ascii=False)
                else:
                    content = "Failed to fetch events"
            elif name == "get_top_players":
                limit = min(args.get("limit", 5), 15)
                offset = args.get("offset", 0)
                top_players_data = await self.mb_api.fetch_top_players(limit, offset)
                if top_players_data:
                    content = json.dumps(top_players_data, ensure_ascii=False)
                else:
                    content = "Failed to fetch top players"
            elif name == "web_search":
                query = args.get("query")
                max_results = min(args.get("max_results", 5), 10)
                search_data = await self.tavily_api.search(query, max_results=max_results)
                if search_data:
                    content = self.tavily_api.format_results(search_data)
                else:
                    content = "Failed to perform web search"
        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            content = f"Error executing tool: {str(e)}"

        return {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": name,
            "content": content,
        }

    async def generate_speech(
        self,
        text: str,
        language_id: str = "ru",
        ref_wav: Optional[str] = None,
        exaggeration: float = 0.5,
        temperature: float = 0.8,
        seed: int = 0,
        cfg_weight: float = 0.5,
    ) -> Optional[bytes]:
        """Generate speech from text using ResembleAI Chatterbox TTS.

        Args:
            text: Text to convert to speech (max 300 characters)
            language_id: Language code (default: ru)
            ref_wav: Path to reference audio for voice cloning (wav/mp3)
            exaggeration: Expressiveness (0.0-1.0, default: 0.5)
            temperature: Variability (0.0-1.0, default: 0.8)
            seed: Seed for generation (0 for random)
            cfg_weight: Classifier-Free Guidance weight (default: 0.5)

        Returns:
            Audio bytes in WAV format or None on error
        """
        if not text:
            logger.warning("Empty text provided for speech generation")
            return None

        # Clean text: remove excessive whitespace and limit length
        import re

        cleaned_text = re.sub(r"\s+", " ", text.strip())
        if len(cleaned_text) > 300:
            cleaned_text = cleaned_text[:300]

        if not cleaned_text:
            return None

        try:
            # Prepare multipart data
            files = {}
            data = {
                "text": cleaned_text,
                "language_id": language_id,
                "exaggeration": str(exaggeration),
                "temperature": str(temperature),
                "cfg_weight": str(cfg_weight),
            }

            # Prepare reference audio
            ref_path = None
            if ref_wav and Path(ref_wav).exists():
                ref_path = Path(ref_wav)
            else:
                default_wav = self.config.VOICES_DIR / "voice.wav"
                default_mp3 = self.config.VOICES_DIR / "voice.mp3"
                if default_wav.exists():
                    ref_path = default_wav
                elif default_mp3.exists():
                    ref_path = default_mp3

            if ref_path:
                files["reference_audio"] = (ref_path.name, ref_path.read_bytes())

            # Call local FastAPI server
            tts_url = self.config.TTS_URL
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(tts_url, data=data, files=files)

                if response.status_code == 200:
                    audio_bytes = response.content
                    logger.info(
                        f"Generated speech with local TTS (lang: {language_id}, size: {len(audio_bytes)} bytes)"
                    )
                    return audio_bytes
                else:
                    logger.error(
                        f"Local TTS server returned error {response.status_code}: {response.text}"
                    )
                    return None

        except Exception:
            logger.exception("Failed to generate speech with local TTS server")
            return None

    def _build_messages(
        self,
        system_prompt: str,
        user_input: str,
        context: MessageContext,
    ) -> List[dict]:
        """Build messages list for OpenAI API.

        Creates a list of messages in OpenAI format:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]

        Args:
            system_prompt: System prompt text
            user_input: User input JSON string with context
            context: Message context

        Returns:
            List of message dictionaries in OpenAI format
        """
        import json

        # Parse user_input JSON to extract context
        try:
            input_data = json.loads(user_input)
        except json.JSONDecodeError:
            input_data = {"current_message": {"text": user_input}}

        # Build system message with RAG context
        system_content = system_prompt
        if "current_date" in input_data:
            system_content += f"\n\nТекущая дата: {input_data['current_date']}"
        if "knowledge_base" in input_data:
            kb_text = "\n\n# База знаний:\n"
            for item in input_data["knowledge_base"]:
                kb_text += f"\n{item['content']}\n"
            system_content += kb_text

        messages = [{"role": "system", "content": system_content}]

        # Build messages from chat logs (previously "group chat" logic, now universal)
        chat_context = input_data.get("chat_context", {})
        recent_messages = chat_context.get("recent_messages", [])

        # Skip leading assistant messages to ensure first message is from user
        # (required by some providers like Amazon Nova)
        first_user_found = False
        for msg in recent_messages:
            author = msg.get("author", "Unknown")
            is_bot = msg.get("is_bot", False)
            text = msg.get("text", "")

            if not text:
                continue
            elif text.startswith("🔄 Бот перезагружен"):
                is_bot = True

            # Skip assistant messages until we find the first user message
            if not first_user_found:
                if is_bot:
                    continue
                first_user_found = True

            role = "assistant" if is_bot else "user"
            content = text if is_bot else f"{author}: {text}"

            messages.append({"role": role, "content": content})

        # Build current message content
        current_msg = input_data.get("current_message", {})
        current_text = current_msg.get("text", context.prompt)

        # Add reply context if present (universal)
        chat_context = input_data.get("chat_context", {})
        reply_to = chat_context.get("reply_to")
        if reply_to:
            reply_author = reply_to.get("author", "Unknown")
            reply_text = reply_to.get("text", "")
            if reply_text:
                current_text = f'[Ответ на сообщение от {reply_author}: "{reply_text[:50]}..."]\n{current_text}'

        # Handle images
        if context.has_image and context.image_bytes:
            user_content = [
                {"type": "text", "text": current_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._make_data_url(context.image_bytes, context.mime_type)
                    },
                },
            ]
        else:
            user_content = current_text

        messages.append({"role": "user", "content": user_content})

        # Log message structure for debugging
        logger.info(f"Built {len(messages)} messages: {[m['role'] for m in messages]}")

        return messages

    async def _call_openai(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Call OpenAI API."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": TEMPERATURE,
        }
        if tools:
            kwargs["tools"] = tools

        return await self.client.chat.completions.create(**kwargs)

    def _process_response(self, response: dict) -> str:
        """Process OpenAI API response."""
        message = response.choices[0].message
        content = message.content

        logger.info(f"OpenAI raw response: {content!r}")
        text = (content or "").strip()

        # Filter out hallucinated empty markdown links like ]() that sometimes repeat endlessly
        import re

        text = re.sub(r"(\]\(\)){2,}", "", text)

        return remove_html(text)

    async def _build_user_input(
        self,
        context: MessageContext,
        message: Optional[types.Message],
    ) -> str:
        """Build user input with JSON context.

        Args:
            context: MessageContext
            message: Telegram message

        Returns:
            JSON string with structured context
        """
        structured_data = {}

        # Parse RAG context if it's a JSON string (from structured context)
        if context.rag_context:
            try:
                # Try to parse as JSON first
                import json

                rag_data = json.loads(context.rag_context)
                structured_data.update(rag_data)
            except (json.JSONDecodeError, TypeError):
                # Fallback: treat as plain text
                structured_data["context_text"] = context.rag_context

        # Add chat context for groups (history is kept as separate messages)
        # Add chat context for all chats (universally from chat logs)
        chat_context = self._build_chat_context_from_logs(context, message)
        if chat_context:
            structured_data["chat_context"] = chat_context

        # Add current message
        display_name = context.user.get_display_name()
        structured_data["current_message"] = {
            "author": display_name,
            "text": context.prompt,
        }

        import json

        return json.dumps(structured_data, ensure_ascii=False, indent=2)

    def _make_data_url(self, image_bytes: bytes, mime_type: Optional[str] = None) -> str:
        """Create data URL for image."""
        mt = (mime_type or "image/jpeg").strip().lower()
        if not mt.startswith("image/"):
            mt = f"image/{mt}" if "/" not in mt else mt
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mt};base64,{b64}"

    def _build_chat_context_from_logs(
        self, context: MessageContext, message: types.Message
    ) -> dict:
        """Build structured chat context from chat logs.

        Args:
            context: Message context
            message: Telegram message

        Returns:
            Dictionary with chat context
        """
        chat_context = {}

        if message.reply_to_message:
            reply_data = self._build_reply_context(message)
            if reply_data:
                chat_context["reply_to"] = reply_data

        # Add recent messages
        recent = self.chat_logs_repo.get_recent_messages(context.chat.id, 10)
        if recent:
            recent_messages = []
            for msg_data in recent:
                message_id, author, is_bot, text = msg_data
                recent_messages.append(
                    {
                        "message_id": message_id,
                        "author": author,
                        "is_bot": is_bot,
                        "text": text,
                    }
                )
            chat_context["recent_messages"] = recent_messages

        return chat_context

    def _build_reply_context(self, message: types.Message) -> Optional[dict]:
        """Build structured reply context.

        Args:
            message: Telegram message

        Returns:
            Dictionary with reply context or None
        """
        if not message.reply_to_message:
            return None

        replied_msg = message.reply_to_message
        replied_msg_id = get_message_id(replied_msg)

        # Get author name
        if is_bot_message(replied_msg):
            author_name = "Ассистент"
        else:
            author_name = get_author_name(replied_msg, "unknown")

        # Get text content
        text = get_message_text(replied_msg)

        # If text is empty or placeholder, try to fetch from logs
        if not text or text == "(пусто)":
            log_msg = self.chat_logs_repo.get_message_by_id(message.chat.id, replied_msg_id)
            if log_msg:
                _, _, log_text = log_msg
                if log_text:
                    text = log_text

        # Get quote if present
        quote = get_reply_quote(message)

        return {
            "message_id": replied_msg_id,
            "author": author_name,
            "text": text if text and text != "(пусто)" else None,
            "quote": quote,
        }
