"""AI service for completions."""

from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog
from aiogram import types
from aiogram.types import ReactionTypeEmoji
from cachetools import TTLCache
from openai import AsyncOpenAI
from pydantic_ai import Agent, ImageUrl, ModelRequest, ModelResponse, TextPart, UserPromptPart
from openai.types import chat
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from application.services.ai_prompt_builder import AIPromptBuilderMixin
from application.services.ai_tools import register_tools
from application.services.ai_tts import AITTSMixin
from core.config import Config
from domain.dtos import IncomingMessageDTO
from domain.entities import MessageContext
from domain.interfaces import IChatLogsRepository, IHistoryRepository
from infrastructure.external.mb_api import MineBridgeAPI
from infrastructure.external.mc_api import MinecraftAPI
from utils.html_edit import remove as remove_html
from utils.time import historical_message, timestamp_message
from utils.history_context import HISTORY_LIMIT, context_messages

log = structlog.get_logger(__name__)

DEFAULT_ERROR_MESSAGE = "Произошла ошибка при обращении к AI. Попробуйте позже."

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


@dataclass
class AIServiceDeps:
    """Runtime dependencies injected into every agent tool call."""

    mb_api: MineBridgeAPI
    mc_api: MinecraftAPI
    news_api: Any
    tavily_api: Any
    stickers_repo: Any
    memory_repo: Any
    chat_logs_repo: IChatLogsRepository
    config: Config

    reminders: Any = None

    # Mutable per-request state (reset in AIService.complete)
    memory_updates: list[str] = field(default_factory=list)
    current_message: types.Message | None = field(default=None, repr=False)

    def require_message_context(self) -> tuple[int, int] | str:
        if not self.current_message:
            return "Error: Available only in message context"
        return self.current_message.chat.id, self.current_message.from_user.id

    def find_sticker_file_id(self, msg_id: int) -> str | None:
        msg = self.current_message
        if not msg:
            return None
        if msg.message_id == msg_id and getattr(msg, "sticker", None):
            return msg.sticker.file_id

        chat_id = msg.chat.id
        file_id = self.chat_logs_repo.get_file_id_by_message_id(chat_id, msg_id)
        if file_id:
            return file_id

        for offset in (-1, 1, -2, 2):
            file_id = self.chat_logs_repo.get_file_id_by_message_id(chat_id, msg_id + offset)
            if file_id:
                log.info("sticker.found_nearby", msg_id=msg_id, nearby_id=msg_id + offset)
                return file_id

        reply = getattr(msg, "reply_to_message", None)
        if reply and getattr(reply, "sticker", None) and reply.message_id == msg_id:
            return reply.sticker.file_id
        return None


class RouterAIChatModel(OpenAIChatModel):
    """OpenAI-compatible model with RouterAI response normalisation.

    RouterAI may return service_tier='standard', which is accepted by the
    upstream router but is not currently in openai-python's ChatCompletion
    Literal set. pydantic-ai re-validates responses, so normalise that field
    before its validation step.
    """

    def _validate_completion(self, response: chat.ChatCompletion) -> chat.ChatCompletion:
        data = response.model_dump()
        if data.get("service_tier") == "standard":
            data["service_tier"] = "default"
        return chat.ChatCompletion.model_validate(data)


class AIService(AIPromptBuilderMixin, AITTSMixin):
    """Service for AI completions powered by pydantic-ai."""

    def __init__(
        self,
        client: AsyncOpenAI,
        history_repo: IHistoryRepository,
        chat_logs_repo: IChatLogsRepository,
        model: str,
        mb_api: MineBridgeAPI,
        mc_api: MinecraftAPI,
        news_api: Any,
        tavily_api: Any,
        config: Config,
        stickers_repo: Any,
        memory_repo: Any,
        rag_service: Any,
    ):
        self.history_repo = history_repo
        self.chat_logs_repo = chat_logs_repo
        self.model = model
        self.config = config
        self.stickers_repo = stickers_repo
        self.memory_repo = memory_repo
        self.rag_service = rag_service

        self._client = client
        self._stickers_cache: TTLCache = TTLCache(maxsize=1, ttl=60)

        # Runtime deps shared with tools
        self._deps = AIServiceDeps(
            mb_api=mb_api,
            mc_api=mc_api,
            news_api=news_api,
            tavily_api=tavily_api,
            stickers_repo=stickers_repo,
            memory_repo=memory_repo,
            chat_logs_repo=chat_logs_repo,
            config=config,
        )

        openai_model = RouterAIChatModel(
            model,
            provider=OpenAIProvider(openai_client=client),
        )
        self._agent: Agent[AIServiceDeps, str] = Agent(
            openai_model,
            output_type=str,
            deps_type=AIServiceDeps,
        )
        register_tools(self._agent)

    def set_model(self, model: str) -> None:
        """Switch active OpenAI-compatible model at runtime."""
        model = model.strip()
        if not model:
            raise ValueError("model is empty")

        self.model = model
        self.config.AI_MODEL = model
        openai_model = RouterAIChatModel(
            model,
            provider=OpenAIProvider(openai_client=self._client),
        )
        self._agent = Agent(
            openai_model,
            output_type=str,
            deps_type=AIServiceDeps,
        )
        register_tools(self._agent)

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
    ) -> tuple[str, list[str], list[tuple[str, str]]]:
        """Generate AI completion for given context."""
        req_log = log.bind(
            user_id=context.user.id if context.user else None,
            chat_id=context.chat.id,
            model=self.model,
        )

        # Isolate owner/message state across concurrent requests.
        from dataclasses import replace
        deps = replace(self._deps, current_message=message, memory_updates=[])
        pending_reactions: list[tuple[str, str]] = []

        full_system_prompt = self._build_system_prompt(system_prompt, context)
        history = self._build_message_history(context, message)

        prompt_text = timestamp_message(
            context.prompt or ("Картинка" if context.has_image else ""),
            message.date if message else None,
        )

        if message and message.reply_to_message:
            reply = message.reply_to_message
            reply_text = reply.text or reply.caption or "[медиа]"
            prompt_text += (
                f"\n[Ответ на сообщение {reply.message_id}]: "
                f"{timestamp_message(reply_text, reply.date)}"
            )

        # Build user prompt with optional image
        if context.has_image and context.image_bytes and context.mime_type:
            from utils.media import make_data_url

            data_url = make_data_url(context.image_bytes, context.mime_type)
            # Create multimodal prompt with text and image
            user_prompt = [
                prompt_text,
                ImageUrl(url=data_url, media_type=context.mime_type),
            ]
        else:
            user_prompt = prompt_text

        try:
            result = await self._agent.run(
                user_prompt,
                deps=deps,
                message_history=history,
                model_settings=ModelSettings(temperature=1),
                instructions=full_system_prompt,
            )

            text = result.output or ""
            text, pending_reactions = self._parse_reactions(text)
            text = re.sub(r"(\]\(){2,}", "", text)
            text = remove_html(text)

            usage = result.usage()
            req_log.info(
                "ai.complete",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )

            return text, deps.memory_updates, pending_reactions

        except Exception as e:
            req_log.exception("ai.error", error=str(e))
            return DEFAULT_ERROR_MESSAGE, deps.memory_updates, []

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _build_message_history(
        self, context: MessageContext, message: types.Message | None
    ) -> list:
        """Convert recent chat logs to pydantic-ai ModelMessage history."""
        if not message:
            return []

        recent = self.chat_logs_repo.get_recent_messages(context.chat.id, HISTORY_LIMIT)
        recent = context_messages([row for row in recent if row[0] != message.message_id])
        if not recent:
            return []

        history = []
        first_user_found = False

        for msg_data in recent:
            message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions = msg_data

            if not text:
                continue
            if message_id == message.message_id:
                continue  # Current message is sent separately, with its Telegram timestamp.
            if text.startswith("🔄 Бот перезагружен"):
                is_bot = True

            if not first_user_found:
                if is_bot:
                    continue
                first_user_found = True

            reaction_text = ""
            if reactions:
                all_emojis = {e for emojis in reactions.values() for e in emojis}
                if all_emojis:
                    reaction_text = f" [Реакции: {', '.join(sorted(all_emojis))}]"

            full_text = historical_message(text) + reaction_text

            # Build message parts (text + optional image)
            if is_bot:
                # Bot responses can only contain text, not images
                parts = [TextPart(content=full_text)]
                history.append(ModelResponse(parts=parts))
            else:
                # User messages can contain text and images
                if image_bytes and mime_type:
                    from utils.media import make_data_url

                    data_url = make_data_url(image_bytes, mime_type)
                    # ImageUrl must be inside UserPromptPart.content, not as separate part
                    content = [
                        f"{author}: {full_text}",
                        ImageUrl(url=data_url, media_type=mime_type),
                    ]
                    parts = [UserPromptPart(content=content)]
                else:
                    parts = [UserPromptPart(content=f"{author}: {full_text}")]
                history.append(ModelRequest(parts=parts))

        return history

    # Media action tags that should NOT be treated as emoji reactions
    _MEDIA_ACTION_KEYS = frozenset({
        "voice", "sticker", "find_photo", "gen_photo", "kb", "guess",
    })

    def _parse_reactions(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        pattern = r"\[(.*?):(.*?)\]"
        reactions: list[tuple[str, str]] = []
        segments: list[tuple[str, str | None]] = []  # (raw_text, None) or (None, "emoji:excerpt") for removal

        pos = 0
        for m in re.finditer(pattern, text):
            key = m.group(1).strip()
            val = m.group(2).strip()
            # Text before this tag (handle invalid tags too)
            if m.start() > pos:
                segments.append((text[pos : m.start()], None))
            if not key or not val:
                pos = m.end()
                continue

            if key.lower() in self._MEDIA_ACTION_KEYS:
                # Media action — keep in text as-is
                segments.append((m.group(0), None))
            else:
                # Emoji reaction — strip from text, collect separately
                segments.append(("", key))
                reactions.append((key, val))

            pos = m.end()

        # Remaining text after last match
        if pos < len(text):
            segments.append((text[pos:], None))

        for _, emoji in segments:
            if emoji:
                log.info("reaction.parsed", emoji=emoji, excerpt="...")

        # Build cleaned text: only keep text segments, skip reaction placeholders
        cleaned_parts: list[str] = []
        for content, _ in segments:
            if content is not None:
                cleaned_parts.append(content)
        cleaned = "".join(cleaned_parts)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned, reactions

    def _find_message_by_excerpt(self, chat_id: int, excerpt: str, limit: int = 50) -> int | None:
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

    async def _set_pending_reactions(self, chat_id: int, bot: Any) -> None:
        """Set reactions that were parsed from AI response."""
        if not hasattr(self, "_pending_reactions") or not self._pending_reactions:
            return

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
