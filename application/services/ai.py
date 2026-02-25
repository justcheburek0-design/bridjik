"""AI service for completions."""

from __future__ import annotations

import re
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, Awaitable, Callable

import msgspec.json as mjson
import structlog
from aiogram import types
from cachetools import TTLCache
from openai import APIError, AsyncOpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, wait_exponential

from application.services.ai_prompt_builder import AIPromptBuilderMixin
from application.services.ai_tools import AIToolsMixin, ToolResult
from application.services.ai_tts import AITTSMixin
from core.config import Config
from domain.dtos import IncomingMessageDTO
from domain.entities import MessageContext
from domain.interfaces import IChatLogsRepository, IHistoryRepository
from infrastructure.external.mb_api import MineBridgeAPI
from infrastructure.external.mc_api import MinecraftAPI
from utils.html_edit import remove as remove_html

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


class AIService(AIToolsMixin, AIPromptBuilderMixin, AITTSMixin):
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
        self._pending_reactions: list[tuple[str, str]] = []
        self._current_request_start_time = 0
        self._current_request_tool_calls: list = []
        self._current_user_id: int | None = None

        self._tools_raw: list = self._load_tools_raw()
        self._tools_skip_flags: dict[str, bool] = {
            t["function"]["name"]: t.get("skip_next_call", False)
            for t in self._tools_raw
            if "function" in t and "name" in t["function"]
        }

        self._stickers_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
        self._tool_handlers: dict[str, Callable] = self._build_tool_handlers()

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
        message: types.Message | None = None,
        on_tool_update: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str, list[str]]:
        """Generate AI completion for given context."""
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
        telemetry_error: str | None = None

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
                            f"🔧 Результат {tool_result.name}: {tool_result.content}",
                        )

                    messages.append(
                        {
                            "tool_call_id": tool_result.tool_call_id,
                            "role": tool_result.role,
                            "name": tool_result.name,
                            "content": tool_result.content,
                        }
                    )

                if self._should_skip_next_call(response_message.tool_calls, tool_results):
                    req_log.info("agentic_loop.skip_next_call")
                    with suppress(Exception):
                        self.chat_logs_repo.add_message(
                            context.chat.id,
                            "Ассистент",
                            True,
                            "⚡ Пропущен повторный вызов AI (оптимизация токенов)",
                        )
                    return (
                        response_message.content or "",
                        self._memory_updates,
                        self._pending_reactions,
                    )

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
        error: str | None = None,
    ) -> None:
        """Record telemetry for a completed request."""
        if not (context.user and context.user.id):
            return
        with suppress(Exception):
            self.telemetry_repo.record_request(
                user_id=context.user.id,
                chat_id=context.chat.id,
                model=self.model,
                tokens_input=total_input_tokens,
                tokens_output=total_output_tokens,
                tokens_cached=total_cached_tokens,
                latency_ms=int((time.time() - overall_start) * 1000),
                tool_calls=list(self._current_request_tool_calls),
                cost_usd=total_cost_credits,
                error=error,
            )

    # -------------------------------------------------------------------------
    # OpenAI call
    # -------------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _call_openai(self, messages: list[dict], tools: list[dict] | None = None) -> Any:
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

    def _process_response(self, response: Any) -> str:
        """Process OpenAI API response."""
        message = response.choices[0].message
        text = (message.content or "").strip()
        log.debug("openai.response", text_preview=text[:100])

        text, reactions = self._parse_reactions(text)
        self._pending_reactions = reactions

        text = re.sub(r"(\]\(){2,}", "", text)
        return remove_html(text)

    def _parse_reactions(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Parse reaction markers from AI response."""
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

    def _find_message_by_excerpt(self, chat_id: int, excerpt: str, limit: int = 50) -> int | None:
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

    async def _check_user_budget(self, user_id: int, chat_id: int) -> str | None:
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
