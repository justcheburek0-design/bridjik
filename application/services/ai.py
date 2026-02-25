"""AI service for completions."""

import base64
import json
import re
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional, Tuple

import httpx
import msgspec.json as mjson
import structlog
from aiogram import types
from cachetools import TTLCache
from openai import APIError, AsyncOpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, wait_exponential

from core.config import Config
from domain.dtos import IncomingMessageDTO
from domain.entities import MessageContext
from domain.interfaces import IChatLogsRepository, IHistoryRepository
from infrastructure.external.mb_api import MineBridgeAPI
from infrastructure.external.mc_api import MinecraftAPI
from utils.chat_helpers import get_author_name, get_message_id, is_bot_message
from utils.html_edit import remove as remove_html
from utils.message import get_message_text, get_reply_quote

log = structlog.get_logger(__name__)

DEFAULT_ERROR_MESSAGE = "Произошла ошибка при обращении к AI. Попробуйте позже."
TEMPERATURE = 1

BOT_ADDRESS_RE = re.compile(
    r"(?i)(?<!\w)(?:нейро-?бот(?:ик|яра)?|бот(?:ик|яра)?|бридж(?:ик)?)(?!\w)"
)
QUESTION_MARK_RE = re.compile(r"\?")
INTERROGATIVE_RE = re.compile(
    r"(?i)\b("
    r"можно ли|кто может помочь|кто поможет|подскаж(?:и|ите)|помогите|нужна помощь|help|помощь"
    r")\b"
)
COMMAND_RE = re.compile(
    r"(?i)\b("
    r"объясни|расскажи|скажи|подскажи|помоги|проверь|сделай|напиши|создай|найди|покажи|настрой"
    r")\b"
)
NOISE_RE = re.compile(r"^\s*(?:[^\w\s]|[\w]{1,2})\s*$")


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
        memory_repo,
        rag_service,
        telemetry_repo,
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
        self.memory_repo = memory_repo
        self.rag_service = rag_service
        self.telemetry_repo = telemetry_repo

        self._memory_updates: list = []
        self._pending_reactions: List[Tuple[str, str]] = []
        self._current_request_start_time = 0
        self._current_request_tool_calls: list = []
        self._current_user_id: Optional[int] = None

        # Cache: tools.json loaded once at startup
        self._tools_raw: list = self._load_tools_raw()
        self._tools_skip_flags: dict[str, bool] = {
            t["function"]["name"]: t.get("skip_next_call", False)
            for t in self._tools_raw
            if "function" in t and "name" in t["function"]
        }

        # Cache: stickers with short TTL (refresh every 60s)
        self._stickers_cache: TTLCache = TTLCache(maxsize=1, ttl=60)

        # Tool handler registry
        self._tool_handlers: dict[str, Callable] = {
            "get_player_info": self._tool_get_player_info,
            "get_server_status": self._tool_get_server_status,
            "get_news": self._tool_get_news,
            "get_events": self._tool_get_events,
            "get_top_players": self._tool_get_top_players,
            "web_search": self._tool_web_search,
            "add_sticker": self._tool_add_sticker,
            "rename_sticker": self._tool_rename_sticker,
            "save_memory": self._tool_save_memory,
            "update_memory": self._tool_update_memory,
            "delete_memory": self._tool_delete_memory,
        }

    def _load_tools_raw(self) -> list:
        """Load tools.json once at init."""
        try:
            return mjson.decode(Path(self.config.TOOLS_FILE).read_bytes())
        except Exception as e:
            log.error("tools.load_failed", error=str(e))
            return []

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def should_respond(self, dto: IncomingMessageDTO, bot_username: str) -> bool:
        """Check if bot should respond to the message."""
        if NOISE_RE.match(dto.text):
            return False

        if dto.chat_type == "private":
            return True

        if dto.original_message.reply_to_message:
            reply = dto.original_message.reply_to_message
            if reply.from_user:
                replied_username = getattr(reply.from_user, "username", "") or ""
                if bot_username and replied_username == bot_username:
                    return True

        if dto.original_message.entities and dto.text:
            for entity in dto.original_message.entities:
                if entity.type == "mention":
                    mention_text = dto.text[entity.offset : entity.offset + entity.length]
                    if bot_username and mention_text.lstrip("@").lower() == bot_username.lower():
                        return True

        if BOT_ADDRESS_RE.search(dto.text):
            return True

        score = 0
        if QUESTION_MARK_RE.search(dto.text):
            score += 1
        if INTERROGATIVE_RE.search(dto.text):
            score += 2
        if COMMAND_RE.search(dto.text):
            score += 1
        if len(dto.text) >= 25:
            score += 1

        return score >= 4

    async def complete(
        self,
        context: MessageContext,
        system_prompt: str,
        message: Optional[types.Message] = None,
        on_tool_update: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> tuple[str, list[str]]:
        """Generate AI completion for given context.

        Returns:
            tuple: (answer_text, memory_updates_list)
        """
        req_log = log.bind(
            user_id=context.user.id if context.user else None,
            chat_id=context.chat.id,
            model=self.model,
        )

        self._current_message = message
        self._current_user_id = context.user.id if context.user else None
        self._current_chat = context.chat
        self._memory_updates = []
        self._current_request_tool_calls = []

        overall_start = time.time()
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0
        total_cost_credits: float = 0.0
        telemetry_error: Optional[str] = None

        messages = self._build_messages(system_prompt, context, message)
        tools = self._get_tools()

        try:
            for _ in range(10):
                response = await self._call_openai(messages, tools)
                response_message = response.choices[0].message

                if hasattr(response, "usage") and response.usage:
                    total_input_tokens += response.usage.prompt_tokens or 0
                    total_output_tokens += response.usage.completion_tokens or 0
                    if hasattr(response.usage, "prompt_tokens_details"):
                        details = response.usage.prompt_tokens_details
                        if details and hasattr(details, "cached_tokens"):
                            total_cached_tokens += details.cached_tokens or 0

                if hasattr(response.usage, "cost") and response.usage.cost:
                    total_cost_credits += float(response.usage.cost)

                if response_message.content and on_tool_update:
                    with suppress(Exception):
                        await on_tool_update(response_message.content)

                if not response_message.tool_calls:
                    text = self._process_response(response)
                    budget_warning = (
                        await self._check_user_budget(context.user.id, context.chat.id)
                        if context.user and context.user.id
                        else None
                    )
                    if budget_warning:
                        text += budget_warning
                    return text, self._memory_updates, self._pending_reactions

                # --- Tool calls branch ---
                for tc in response_message.tool_calls:
                    self._current_request_tool_calls.append(tc.function.name)

                response_dict = response_message.model_dump(exclude_none=True)
                response_dict.pop("reasoning_details", None)
                if "content" not in response_dict or response_dict["content"] is None:
                    response_dict["content"] = ""
                messages.append(response_dict)

                tool_results = []
                for tool_call in response_message.tool_calls:
                    with suppress(Exception):
                        self.chat_logs_repo.add_message(
                            context.chat.id,
                            "Ассистент",
                            True,
                            f"🔨 Вызов инструмента: {tool_call.function.name} ({tool_call.function.arguments})",
                        )

                    tool_result = await self._execute_tool(tool_call)
                    tool_results.append(tool_result)

                    with suppress(Exception):
                        self.chat_logs_repo.add_message(
                            context.chat.id,
                            "Ассистент",
                            True,
                            f"🔧 Результат {tool_result.get('name', 'unknown')}: {tool_result.get('content', '')}",
                        )

                    messages.append({k: v for k, v in tool_result.items() if k != "success"})

                if self._should_skip_next_call(response_message.tool_calls, tool_results):
                    req_log.info("agentic_loop.skip_next_call")
                    with suppress(Exception):
                        self.chat_logs_repo.add_message(
                            context.chat.id,
                            "Ассистент",
                            True,
                            "⚡ Пропущен повторный вызов AI (оптимизация токенов)",
                        )
                    final_text = response_message.content or ""
                    return final_text, self._memory_updates, self._pending_reactions

            # Loop limit reached
            telemetry_error = "Loop limit reached"
            return DEFAULT_ERROR_MESSAGE, self._memory_updates, []

        except (RateLimitError, APIError) as e:
            req_log.error("openai.error", error=str(e))
            telemetry_error = str(e)
            return DEFAULT_ERROR_MESSAGE, self._memory_updates, []

        finally:
            self._record_telemetry(
                context=context,
                overall_start=overall_start,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_cached_tokens=total_cached_tokens,
                total_cost_credits=total_cost_credits,
                error=telemetry_error,
            )

    def _record_telemetry(
        self,
        context: MessageContext,
        overall_start: float,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cached_tokens: int,
        total_cost_credits: float,
        error: Optional[str] = None,
    ) -> None:
        """Record telemetry for a completed request."""
        if not (context.user and context.user.id):
            return
        with suppress(Exception):
            tool_calls = list(self._current_request_tool_calls)
            if error == "Loop limit reached":
                tool_calls = tool_calls  # already tracked
            self.telemetry_repo.record_request(
                user_id=context.user.id,
                chat_id=context.chat.id,
                model=self.model,
                tokens_input=total_input_tokens,
                tokens_output=total_output_tokens,
                tokens_cached=total_cached_tokens,
                latency_ms=int((time.time() - overall_start) * 1000),
                tool_calls=tool_calls,
                cost_usd=total_cost_credits,
                error=error,
            )

    # -------------------------------------------------------------------------
    # Tools helpers
    # -------------------------------------------------------------------------

    def _get_tools(self) -> List[dict]:
        """Get processed tools list for OpenAI API."""
        processed = []
        for tool in self._tools_raw:
            skip = tool.get("skip_next_call", False)
            clean = {k: v for k, v in tool.items() if k != "skip_next_call"}
            if skip and "function" in clean:
                orig = clean["function"].get("description", "")
                clean["function"]["description"] = (
                    f"{orig}\n\n⚠️ Этот инструмент выполняется БЕЗ обратной связи. "
                    "Формулируй сообщение сразу готовым для пользователя."
                )
            processed.append(clean)
        return processed

    def _should_skip_next_call(self, tool_calls: List[Any], tool_results: List[dict]) -> bool:
        """Return True if all tools have skip_next_call=True and all succeeded."""
        if not tool_calls or not tool_results:
            return False
        for tool_call, result in zip(tool_calls, tool_results):
            if not self._tools_skip_flags.get(tool_call.function.name, False):
                return False
            if not result.get("success", False):
                return False
        return True

    def _tool_result(self, tool_call: Any, content: str) -> dict:
        """Build a tool result dict with success flag."""
        is_success = not any(
            [
                content.startswith("Error:"),
                content.startswith("Ошибка:"),
                content.startswith("❌"),
                "Не удалось" in content,
                "не найден" in content.lower(),
            ]
        )
        return {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": tool_call.function.name,
            "content": content,
            "success": is_success,
        }

    async def _execute_tool(self, tool_call: Any) -> dict:
        """Dispatch tool call to the appropriate handler."""
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return self._tool_result(tool_call, "Error: Invalid JSON arguments")

        log.info("tool.execute", tool=name, args=args)

        handler = self._tool_handlers.get(name)
        if handler is None:
            return self._tool_result(tool_call, "Error: Unknown tool")

        try:
            content = await handler(args)
        except Exception as e:
            log.exception("tool.error", tool=name, error=str(e))
            content = f"Error executing tool: {e}"

        return self._tool_result(tool_call, content)

    # -------------------------------------------------------------------------
    # Individual tool handlers
    # -------------------------------------------------------------------------

    async def _tool_get_player_info(self, args: dict) -> str:
        data = await self.mb_api.search_player(args.get("query"))
        return mjson.encode(data).decode() if data else "Player not found"

    async def _tool_get_server_status(self, args: dict) -> str:
        data = await self.mc_api.fetch_status()
        return mjson.encode(data).decode()

    async def _tool_get_news(self, args: dict) -> str:
        limit = min(args.get("limit", 10), 20)
        offset = args.get("offset", 0)
        data = await self.news_api.fetch_news(limit, offset)
        return mjson.encode(data).decode() if data else "Failed to fetch news"

    async def _tool_get_events(self, args: dict) -> str:
        data = await self.mb_api.fetch_events(args.get("season", -1))
        return mjson.encode(data).decode() if data else "Failed to fetch events"

    async def _tool_get_top_players(self, args: dict) -> str:
        limit = min(args.get("limit", 5), 15)
        offset = args.get("offset", 0)
        data = await self.mb_api.fetch_top_players(limit, offset)
        return mjson.encode(data).decode() if data else "Failed to fetch top players"

    async def _tool_web_search(self, args: dict) -> str:
        query = args.get("query")
        max_results = min(args.get("max_results", 5), 10)
        data = await self.tavily_api.search(query, max_results=max_results)
        return self.tavily_api.format_results(data) if data else "Failed to perform web search"

    async def _tool_add_sticker(self, args: dict) -> str:
        description = args.get("description", "").strip()
        msg_id = args.get("message_id")

        if not description:
            return "Error: Description is required"
        if not msg_id:
            return "Error: Message ID is required"

        sticker_file_id = self._find_sticker_file_id(msg_id)
        if not sticker_file_id:
            return f"Не удалось найти стикер с message_id={msg_id}. Убедитесь, что это сообщение со стикером."

        result = self.stickers_repo.add_sticker(description, sticker_file_id)
        return (result["message"] + " в базу данных!") if result["success"] else result["message"]

    async def _tool_rename_sticker(self, args: dict) -> str:
        old_name = args.get("old_name", "").strip()
        new_name = args.get("new_name", "").strip()
        msg_id = args.get("message_id")

        if not new_name:
            return "Error: Новое название обязательно"
        if not old_name and not msg_id:
            return "Error: Укажите либо старое название (old_name), либо ID сообщения (message_id)"

        if msg_id and not old_name:
            sticker_file_id = self._find_sticker_file_id(msg_id)
            if sticker_file_id:
                old_name = self.stickers_repo.find_by_file_id(sticker_file_id) or ""
                if not old_name:
                    return f"Стикер с message_id={msg_id} не найден в базе данных. Возможно, его нужно сначала добавить."
            else:
                return f"Не удалось найти стикер с message_id={msg_id}. Убедитесь, что это сообщение со стикером."

        if not old_name:
            return "Error: Не удалось определить старое название стикера"

        result = self.stickers_repo.rename_sticker(old_name, new_name)
        content = result["message"]
        if not result["success"] and result.get("similar_stickers"):
            content += f"\n\nВозможно, вы имели в виду: {', '.join(result['similar_stickers'])}"
        return content

    async def _tool_save_memory(self, args: dict) -> str:
        scope = args.get("scope", "chat").strip()
        content_text = args.get("content", "").strip()
        tags = args.get("tags", [])

        if scope not in ["chat", "user"]:
            return "Error: scope must be 'chat' or 'user'"
        if not content_text:
            return "Error: Content is required"
        if not self._current_message:
            return "Error: Available only in message context"

        chat_id = self._current_message.chat.id
        user_id = self._current_message.from_user.id
        scope_id = chat_id if scope == "chat" else user_id

        existing = (
            self.memory_repo.get_chat_memories(chat_id)
            if scope == "chat"
            else self.memory_repo.get_user_memories(user_id)
        )

        if tags:
            tags_set = {t.lower() for t in tags}
            for memory in existing:
                existing_tags = {t.lower() for t in memory.get("tags", [])}
                if existing_tags and len(tags_set & existing_tags) >= min(2, len(tags_set)):
                    mem_id = memory["id"][:8]
                    scope_label = "чата" if scope == "chat" else "пользователя"
                    return (
                        f"❌ Такая запись уже существует в памяти {scope_label}:\n\n"
                        f"[ID: {mem_id}]\n{memory['content']}\n"
                        f"Теги: {', '.join(memory.get('tags', []))}\n\n"
                        f"💡 Эта информация уже сохранена, но её можно изменить."
                    )

        if scope == "chat":
            memory_id = self.memory_repo.add_chat_memory(
                chat_id=chat_id, content=content_text, tags=tags, author_id=user_id
            )
            log.info("memory.saved", scope="chat", chat_id=chat_id, memory_id=memory_id)
            content = f"✅ Запомнил (память чата): {content_text[:50]}..."
        else:
            memory_id = self.memory_repo.add_user_memory(
                user_id=user_id, content=content_text, tags=tags
            )
            log.info("memory.saved", scope="user", user_id=user_id, memory_id=memory_id)
            content = f"✅ Запомнил (память о пользователе): {content_text[:50]}..."

        self._memory_updates.append(content_text)
        return content

    async def _tool_update_memory(self, args: dict) -> str:
        search_query = args.get("search_query", "").strip()
        scope = args.get("scope", "chat").strip()
        new_content = args.get("content")
        new_tags = args.get("tags")

        if not search_query:
            return "Error: search_query is required"
        if scope not in ["chat", "user"]:
            return "Error: scope must be 'chat' or 'user'"
        if not new_content and not new_tags:
            return "Error: At least one of content or tags must be provided"
        if not self._current_message:
            return "Error: Available only in message context"

        chat_id = self._current_message.chat.id
        user_id = self._current_message.from_user.id
        scope_id = chat_id if scope == "chat" else user_id
        scope_label = "памяти чата" if scope == "chat" else "памяти о пользователе"

        found = self.memory_repo.search_memories(scope, scope_id, search_query)
        if not found:
            return f"❌ Не нашел записи в {scope_label} по запросу: {search_query}"

        memory_id = found[0]["id"]
        updated = self.memory_repo.update_memory(
            scope=scope,
            scope_id=scope_id,
            memory_id=memory_id,
            content=new_content,
            tags=new_tags,
        )
        if updated:
            log.info("memory.updated", scope=scope, scope_id=scope_id, memory_id=memory_id)
            return f"✅ Обновил запись в {scope_label}: {found[0]['content'][:50]}..."
        return f"❌ Не удалось обновить запись (ID: {memory_id})"

    async def _tool_delete_memory(self, args: dict) -> str:
        search_query = args.get("search_query", "").strip()
        scope = args.get("scope", "chat").strip()

        if not search_query:
            return "Error: Search query is required"
        if scope not in ["chat", "user"]:
            return "Error: scope must be 'chat' or 'user'"
        if not self._current_message:
            return "Error: Available only in message context"

        chat_id = self._current_message.chat.id
        user_id = self._current_message.from_user.id
        scope_id = chat_id if scope == "chat" else user_id
        scope_label = "памяти чата" if scope == "chat" else "памяти о пользователе"

        found = self.memory_repo.search_and_delete(scope, scope_id, search_query)
        if found:
            log.info("memory.deleted", scope=scope, scope_id=scope_id, query=search_query)
            return f"🗑️ Удалил из {scope_label}: {found['content'][:50]}..."
        return f"❌ Не нашел записи в {scope_label} по запросу: {search_query}"

    # -------------------------------------------------------------------------
    # Sticker helper
    # -------------------------------------------------------------------------

    def _find_sticker_file_id(self, msg_id: int) -> Optional[str]:
        """Lookup sticker file_id by message_id from current message context."""
        if self._current_message and hasattr(self._current_message, "message_id"):
            if self._current_message.message_id == msg_id and getattr(
                self._current_message, "sticker", None
            ):
                return self._current_message.sticker.file_id

        if not self._current_message:
            return None

        chat_id = self._current_message.chat.id
        file_id = self.chat_logs_repo.get_file_id_by_message_id(chat_id, msg_id)
        if file_id:
            return file_id

        for offset in [-1, 1, -2, 2]:
            nearby_id = msg_id + offset
            file_id = self.chat_logs_repo.get_file_id_by_message_id(chat_id, nearby_id)
            if file_id:
                log.info("sticker.found_nearby", msg_id=msg_id, nearby_id=nearby_id)
                return file_id

        reply = getattr(self._current_message, "reply_to_message", None)
        if reply and getattr(reply, "sticker", None) and reply.message_id == msg_id:
            return reply.sticker.file_id

        return None

    # -------------------------------------------------------------------------
    # Speech generation
    # -------------------------------------------------------------------------

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
        """Generate speech from text using ResembleAI Chatterbox TTS."""
        if not text:
            log.warning("tts.empty_text")
            return None

        cleaned_text = re.sub(r"\s+", " ", text.strip())[:300]
        if not cleaned_text:
            return None

        files = {}
        data = {
            "text": cleaned_text,
            "language_id": language_id,
            "exaggeration": str(exaggeration),
            "temperature": str(temperature),
            "cfg_weight": str(cfg_weight),
        }

        ref_path: Optional[Path] = None
        if ref_wav and Path(ref_wav).exists():
            ref_path = Path(ref_wav)
        else:
            for candidate in [
                self.config.VOICES_DIR / "voice.wav",
                self.config.VOICES_DIR / "voice.mp3",
            ]:
                if candidate.exists():
                    ref_path = candidate
                    break

        if ref_path:
            files["reference_audio"] = (ref_path.name, ref_path.read_bytes())

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.config.TTS_URL, data=data, files=files)
                if response.status_code == 200:
                    log.info("tts.generated", lang=language_id, size=len(response.content))
                    return response.content
                log.error("tts.server_error", status=response.status_code, body=response.text)
                return None
        except Exception:
            log.exception("tts.failed")
            return None

    # -------------------------------------------------------------------------
    # Message building
    # -------------------------------------------------------------------------

    def _build_messages(
        self,
        system_prompt: str,
        context: MessageContext,
        message: Optional[types.Message] = None,
    ) -> List[dict]:
        """Build messages list for OpenAI API."""
        system_prompt = self._build_system_prompt(system_prompt, context)
        messages = [{"role": "system", "content": system_prompt}]

        recent_messages = []
        if message:
            chat_context = self._build_chat_context_from_logs(context, message)
            recent_messages = chat_context.get("recent_messages", [])

        first_user_found = False
        for msg in recent_messages:
            author = msg.get("author", "Unknown")
            is_bot = msg.get("is_bot", False)
            text = msg.get("text", "")
            image_bytes = msg.get("image_bytes")
            mime_type = msg.get("mime_type")

            if not text and not image_bytes:
                continue
            if text and text.startswith("🔄 Бот перезагружен"):
                is_bot = True

            if not first_user_found:
                if is_bot:
                    continue
                first_user_found = True

            role = "assistant" if is_bot else "user"
            content = self._format_multimodal_message(text, author, is_bot, image_bytes, mime_type)
            messages.append({"role": role, "content": content})

        log.info("messages.built", count=len(messages), roles=[m["role"] for m in messages])
        return messages

    def _build_system_prompt(self, system_prompt: str, context: MessageContext) -> str:
        """Build system prompt with stickers, chat info, memories and date."""
        # Stickers (static, cached)
        if "stickers" not in self._stickers_cache:
            self._stickers_cache["stickers"] = list(self.stickers_repo.get_all_stickers().keys())
        stickers = self._stickers_cache["stickers"]
        if stickers:
            system_prompt += f"\n\n## Доступные стикеры:\n{', '.join(sorted(stickers))}"

        # Chat info (relatively static)
        chat_info: dict = {"title": context.chat.title, "type": context.chat.type}
        with suppress(Exception):
            cached = self.memory_repo.get_chat_metadata(context.chat.id)
            if cached:
                if not chat_info["title"] and cached.get("title"):
                    chat_info["title"] = cached["title"]
                if cached.get("description"):
                    chat_info["description"] = cached["description"]
                if cached.get("invite_link"):
                    chat_info["invite_link"] = cached["invite_link"]

        info_parts = []
        for key, label in [
            ("title", "Название"),
            ("type", "Тип"),
            ("description", "Описание"),
            ("invite_link", "Ссылка"),
        ]:
            if chat_info.get(key):
                info_parts.append(f"{label}: {chat_info[key]}")
        if info_parts:
            system_prompt += "\n\n# Информация о чате:\n" + "\n".join(info_parts) + "\n"

        # Memories (dynamic)
        mem_parts: list[str] = []
        with suppress(Exception):
            if context.chat.id:
                chat_mems = sorted(
                    self.memory_repo.get_chat_memories(context.chat.id),
                    key=lambda m: m.get("timestamp", ""),
                    reverse=True,
                )
                if chat_mems:
                    mem_parts.append(
                        "## Память чата:\n"
                        + "\n".join(
                            f"- {m['content'].strip()}"
                            for m in chat_mems
                            if m.get("content", "").strip()
                        )
                    )

            if context.user and context.user.id:
                user_mems = sorted(
                    self.memory_repo.get_user_memories(context.user.id),
                    key=lambda m: m.get("timestamp", ""),
                    reverse=True,
                )
                if user_mems:
                    uname = context.user.username or context.user.first_name
                    mem_parts.append(
                        f"## Память о пользователе {uname}:\n"
                        + "\n".join(
                            f"- {m['content'].strip()}"
                            for m in user_mems
                            if m.get("content", "").strip()
                        )
                    )

        if mem_parts:
            system_prompt += "\n\n# Память:\n" + "\n\n".join(mem_parts)

        # Date (most dynamic — at the end to minimise cache invalidation)
        moscow_tz = timezone(timedelta(hours=3))
        date = datetime.now(tz=moscow_tz).strftime("%Y-%m-%d")
        system_prompt += f"\n\nТекущая дата: {date}"

        return system_prompt

    def _format_multimodal_message(
        self,
        text: str,
        author: str,
        is_bot: bool,
        image_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> Any:
        """Format a message for OpenAI API, handling text and images."""
        text_content = text if is_bot else f"{author}: {text}"

        if image_bytes and mime_type and self.config.AI_MULTIMODAL_CONTEXT:
            content_parts = []
            if text:
                content_parts.append({"type": "text", "text": text_content})
            data_url = self._make_data_url(image_bytes, mime_type)
            content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
            return content_parts

        return text_content

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _call_openai(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Call OpenAI API with automatic retry on rate limit."""
        try:
            last_msgs = messages[-3:] if len(messages) > 3 else messages
            log.debug(
                "openai.request",
                msg_count=len(messages),
                last_msgs=mjson.encode(last_msgs).decode(),
            )
        except Exception:
            pass

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": TEMPERATURE,
        }
        if self._current_user_id:
            chat = getattr(self, "_current_chat", None)
            if chat and chat.type == "private":
                kwargs["user"] = f"user_{self._current_user_id}"
            else:
                chat_id = chat.id if chat else self._current_user_id
                kwargs["user"] = f"chat_{chat_id}"
        if tools:
            kwargs["tools"] = tools

        return await self.client.chat.completions.create(**kwargs)

    def _process_response(self, response: dict) -> str:
        """Process OpenAI API response."""
        message = response.choices[0].message
        text = (message.content or "").strip()
        log.debug("openai.response", text_preview=text[:100])

        text, reactions = self._parse_reactions(text)
        self._pending_reactions = reactions

        text = re.sub(r"(\]\(){2,}", "", text)
        return remove_html(text)

    def _parse_reactions(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Parse reaction markers from AI response.

        Returns:
            Tuple of (cleaned_text, reactions_list) where reactions_list = [(emoji, excerpt), ...]
        """
        pattern = r"\[emoji:(.*?):(.*?)\]"
        reactions = [
            (m.group(1).strip(), m.group(2).strip())
            for m in re.finditer(pattern, text)
            if m.group(1).strip() and m.group(2).strip()
        ]
        for emoji, excerpt in reactions:
            log.info("reaction.parsed", emoji=emoji, excerpt=excerpt[:30])

        cleaned = re.sub(r"\n*\[emoji:.*?:.*?\]\n*", "", text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned, reactions

    def _find_message_by_excerpt(
        self, chat_id: int, excerpt: str, limit: int = 50
    ) -> Optional[int]:
        """Find message ID by text excerpt in chat history."""
        try:
            recent = self.chat_logs_repo.get_recent_messages(chat_id, limit)
            excerpt_lower = excerpt.lower()
            for msg in reversed(recent):
                msg_id, author, is_bot, text, *_ = msg
                if text and excerpt_lower in text.lower():
                    log.info("excerpt.found", msg_id=msg_id, excerpt=excerpt[:30])
                    return msg_id
            return None
        except Exception:
            log.exception("excerpt.search_failed", excerpt=excerpt)
            return None

    async def _set_pending_reactions(self, chat_id: int, bot) -> None:
        """Set reactions that were parsed from AI response."""
        if not self._pending_reactions:
            return

        from aiogram.types import ReactionTypeEmoji

        for emoji, excerpt in self._pending_reactions:
            msg_id = self._find_message_by_excerpt(chat_id, excerpt)
            if msg_id:
                with suppress(Exception):
                    await bot.set_message_reaction(
                        chat_id=chat_id,
                        message_id=msg_id,
                        reaction=[ReactionTypeEmoji(emoji=emoji)],
                    )
                    log.info("reaction.set", emoji=emoji, msg_id=msg_id)
            else:
                log.warning("reaction.msg_not_found", emoji=emoji, excerpt=excerpt[:30])

        self._pending_reactions = []

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
        """Build structured chat context from chat logs."""
        chat_context: dict = {}

        if message.reply_to_message:
            reply_data = self._build_reply_context(message)
            if reply_data:
                chat_context["reply_to"] = reply_data

        recent = self.chat_logs_repo.get_recent_messages(context.chat.id, 10)
        if recent:
            recent_messages = []
            for msg_data in recent:
                (message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions) = (
                    msg_data
                )

                reaction_text = ""
                if reactions:
                    all_emojis = {e for emojis in reactions.values() for e in emojis}
                    if all_emojis:
                        reaction_text = f" [Реакции: {', '.join(sorted(all_emojis))}]"

                msg_dict: dict = {
                    "message_id": message_id,
                    "author": author,
                    "is_bot": is_bot,
                    "text": text + reaction_text,
                }
                if image_bytes and mime_type:
                    msg_dict["image_bytes"] = image_bytes
                    msg_dict["mime_type"] = mime_type

                recent_messages.append(msg_dict)
            chat_context["recent_messages"] = recent_messages

        return chat_context

    def _build_reply_context(self, message: types.Message) -> Optional[dict]:
        """Build structured reply context."""
        if not message.reply_to_message:
            return None

        replied_msg = message.reply_to_message
        replied_msg_id = get_message_id(replied_msg)
        author_name = (
            "Ассистент" if is_bot_message(replied_msg) else get_author_name(replied_msg, "unknown")
        )

        text = get_message_text(replied_msg)
        if not text or text == "(пусто)":
            log_msg = self.chat_logs_repo.get_message_by_id(message.chat.id, replied_msg_id)
            if log_msg:
                _, _, log_text = log_msg
                if log_text:
                    text = log_text

        return {
            "message_id": replied_msg_id,
            "author": author_name,
            "text": text if text and text != "(пусто)" else None,
            "quote": get_reply_quote(message),
        }

    async def _check_user_budget(self, user_id: int, chat_id: int) -> Optional[str]:
        """Check if user is approaching budget limit."""
        try:
            tokens_used = self.telemetry_repo.get_user_tokens_in_window(
                user_id, hours=self.config.TELEMETRY_WINDOW_HOURS
            )
            soft_limit = self.config.TELEMETRY_SOFT_LIMIT_TOKENS
            if tokens_used > soft_limit * 0.9:
                remaining = soft_limit - tokens_used
                return (
                    f"\n\n⚠️ <b>Внимание:</b> использовано {tokens_used:,} токенов "
                    f"за последние {self.config.TELEMETRY_WINDOW_HOURS} часа "
                    f"(лимит: {soft_limit:,}, осталось: {remaining:,})"
                )
        except Exception:
            log.exception("budget.check_failed", user_id=user_id)
        return None
