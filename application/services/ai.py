"""AI service for completions."""

import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional, Tuple

import httpx
from aiogram import types
from openai import APIError, AsyncOpenAI, RateLimitError

from core.config import Config
from domain.dtos import IncomingMessageDTO
from domain.entities import MessageContext
from domain.interfaces import IChatLogsRepository, IHistoryRepository
from infrastructure.external.mb_api import MineBridgeAPI
from infrastructure.external.mc_api import MinecraftAPI
from utils.chat_helpers import get_author_name, get_message_id, is_bot_message
from utils.html_edit import remove as remove_html
from utils.message import get_message_text, get_reply_quote

logger = logging.getLogger(__name__)

# Constants
DEFAULT_ERROR_MESSAGE = "Произошла ошибка при обращении к AI. Попробуйте позже."
TEMPERATURE = 1

# Regex patterns for intent detection
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
        # Track memory updates for displaying to user
        self._memory_updates = []
        # Track reactions parsed from AI response
        self._pending_reactions: List[Tuple[str, str]] = []
        # Track current request for telemetry
        self._current_request_start_time = 0
        self._current_request_tool_calls = []

    async def should_respond(self, dto: IncomingMessageDTO, bot_username: str) -> bool:
        """Check if bot should respond to the message."""
        # Check basic noise
        if NOISE_RE.match(dto.text):
            return False

        # Private chats: always answer (unless noise)
        if dto.chat_type == "private":
            return True

        # Group chats: check triggers

        # 1. Reply to bot
        if dto.original_message.reply_to_message:
            reply = dto.original_message.reply_to_message
            if reply.from_user:
                replied_username = getattr(reply.from_user, "username", "") or ""
                if bot_username and replied_username == bot_username:
                    return True

        # 2. Mentions
        if dto.original_message.entities and dto.text:
            for entity in dto.original_message.entities:
                if entity.type == "mention":
                    mention_text = dto.text[entity.offset : entity.offset + entity.length]
                    if bot_username and mention_text.lstrip("@").lower() == bot_username.lower():
                        return True

        # 3. Keywords / Address
        if BOT_ADDRESS_RE.search(dto.text):
            return True

        # 4. Scoring system for implied questions
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
        full_system_prompt = system_prompt

        # Store message for tool execution (e.g., add_sticker needs sticker file_id)
        self._current_message = message
        # Reset memory updates tracker
        self._memory_updates = []
        # Reset telemetry tracking
        self._current_request_tool_calls = []

        # Telemetry: track time and usage
        import time

        overall_start_time = time.time()
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0

        messages = self._build_messages(full_system_prompt, context, message)
        tools = self._get_tools()

        try:
            # Agentic loop (max 10 iterations)
            for _ in range(10):
                response = await self._call_openai(messages, tools)
                response_message = response.choices[0].message

                # Accumulate usage for telemetry
                if hasattr(response, "usage") and response.usage:
                    total_input_tokens += response.usage.prompt_tokens or 0
                    total_output_tokens += response.usage.completion_tokens or 0
                    # Extract cached tokens if available
                    if hasattr(response.usage, "prompt_tokens_details"):
                        prompt_details = response.usage.prompt_tokens_details
                        if prompt_details and hasattr(prompt_details, "cached_tokens"):
                            total_cached_tokens += prompt_details.cached_tokens or 0

                # Check for tool calls
                # Update status if AI provided content
                if response_message.content and on_tool_update:
                    try:
                        await on_tool_update(response_message.content)
                    except Exception:
                        logger.warning("Failed to update tool status", exc_info=True)

                # Check for tool calls
                if response_message.tool_calls:
                    # Track tool names for telemetry
                    for tc in response_message.tool_calls:
                        self._current_request_tool_calls.append(tc.function.name)

                    # Add assistant message with tool calls to history
                    # Convert to dict to ensure compatibility with providers like xAI
                    # exclude_none=True removes fields like 'audio', 'refusal' etc. which might confuse the API
                    response_dict = response_message.model_dump(exclude_none=True)

                    # Remove 'reasoning_details' (specific to xAI output, not valid input)
                    response_dict.pop("reasoning_details", None)

                    if "content" not in response_dict or response_dict["content"] is None:
                        response_dict["content"] = ""
                    messages.append(response_dict)

                    # Update status if AI provided content
                    if response_message.content and on_tool_update:
                        try:
                            await on_tool_update(response_message.content)
                        except Exception:
                            logger.warning("Failed to update tool status", exc_info=True)

                    # Execute tools and collect results
                    tool_results = []
                    for tool_call in response_message.tool_calls:
                        # Save tool call to logs
                        try:
                            func_name = tool_call.function.name
                            func_args = tool_call.function.arguments
                            self.chat_logs_repo.add_message(
                                context.chat.id,
                                "Ассистент",
                                True,
                                f"🔨 Вызов инструмента: {func_name} ({func_args})",
                            )
                        except Exception:
                            logger.warning("Failed to save tool call to logs", exc_info=True)

                        tool_result = await self._execute_tool(tool_call)
                        tool_results.append(tool_result)

                        # Save tool result to logs
                        try:
                            # Parse content from tool result
                            content = tool_result.get("content", "")
                            tool_name = tool_result.get("name", "unknown")
                            self.chat_logs_repo.add_message(
                                context.chat.id,
                                "Ассистент",
                                True,
                                f"🔧 Результат {tool_name}: {content}",
                            )
                        except Exception:
                            logger.warning("Failed to save tool result to logs", exc_info=True)

                        # Append tool result to messages (removing internal 'success' field)
                        messages.append({k: v for k, v in tool_result.items() if k != "success"})

                    # Check if we should skip next AI call (optimization)
                    should_skip_next_call = self._should_skip_next_call(
                        response_message.tool_calls, tool_results
                    )

                    if should_skip_next_call:
                        # Log skip for debugging
                        logger.info(
                            "Skipping next AI call: all tools have skip_next_call=true and succeeded"
                        )

                        # Log to chat logs
                        try:
                            self.chat_logs_repo.add_message(
                                context.chat.id,
                                "Ассистент",
                                True,
                                "⚡ Пропущен повторный вызов AI (оптимизация токенов)",
                            )
                        except Exception:
                            logger.warning("Failed to log skip to chat logs", exc_info=True)

                        # Record telemetry with skipped call info
                        latency_ms = int((time.time() - overall_start_time) * 1000)
                        try:
                            if context.user and context.user.id:
                                # Track this as a skipped call in telemetry
                                # We'll add a custom field or note in tool_calls
                                tool_calls_with_skip = self._current_request_tool_calls + [
                                    "[SKIPPED_AI_CALL]"
                                ]

                                self.telemetry_repo.record_request(
                                    user_id=context.user.id,
                                    chat_id=context.chat.id,
                                    model=self.model,
                                    tokens_input=total_input_tokens,
                                    tokens_output=total_output_tokens,
                                    tokens_cached=total_cached_tokens,
                                    latency_ms=latency_ms,
                                    tool_calls=tool_calls_with_skip,
                                )
                        except Exception:
                            logger.exception("Failed to record telemetry")

                        # Return AI content (it should contain the response as instructed in tools description)
                        final_text = response_message.content or ""
                        return final_text, self._memory_updates, self._pending_reactions

                    # Continue loop to get next response from model
                    continue

                # No tool calls, process final response
                text = self._process_response(response)

                # Record telemetry after successful completion
                latency_ms = int((time.time() - overall_start_time) * 1000)
                try:
                    if context.user and context.user.id:
                        self.telemetry_repo.record_request(
                            user_id=context.user.id,
                            chat_id=context.chat.id,
                            model=self.model,
                            tokens_input=total_input_tokens,
                            tokens_output=total_output_tokens,
                            tokens_cached=total_cached_tokens,
                            latency_ms=latency_ms,
                            tool_calls=self._current_request_tool_calls,
                        )

                        # Check soft budget limit and add warning if needed
                        budget_warning = await self._check_user_budget(
                            context.user.id, context.chat.id
                        )
                        if budget_warning:
                            text += budget_warning
                except Exception:
                    logger.exception("Failed to record telemetry")

                return text, self._memory_updates, self._pending_reactions

            # If loop limit reached, return what we have or error
            latency_ms = int((time.time() - overall_start_time) * 1000)
            try:
                if context.user and context.user.id:
                    self.telemetry_repo.record_request(
                        user_id=context.user.id,
                        chat_id=context.chat.id,
                        model=self.model,
                        tokens_input=total_input_tokens,
                        tokens_output=total_output_tokens,
                        tokens_cached=total_cached_tokens,
                        latency_ms=latency_ms,
                        tool_calls=self._current_request_tool_calls,
                        error="Loop limit reached",
                    )
            except Exception:
                logger.exception("Failed to record telemetry")

            return DEFAULT_ERROR_MESSAGE, self._memory_updates, []

        except (RateLimitError, APIError) as e:
            logger.error("OpenAI completion rate limit/API error: %s", str(e), exc_info=True)
            # Record error in telemetry
            latency_ms = int((time.time() - overall_start_time) * 1000)
            try:
                if context.user and context.user.id:
                    self.telemetry_repo.record_request(
                        user_id=context.user.id,
                        chat_id=context.chat.id,
                        model=self.model,
                        tokens_input=total_input_tokens,
                        tokens_output=total_output_tokens,
                        tokens_cached=total_cached_tokens,
                        latency_ms=latency_ms,
                        tool_calls=self._current_request_tool_calls,
                        error=str(e),
                    )
            except Exception:
                logger.exception("Failed to record telemetry")

            return DEFAULT_ERROR_MESSAGE, self._memory_updates, []

    def _get_tools(self) -> List[dict]:
        """Get available tools definition."""
        try:
            with open(self.config.TOOLS_FILE, "r", encoding="utf-8") as f:
                tools = json.load(f)

            # Process tools: add skip_next_call info to description and remove the parameter
            processed_tools = []
            for tool in tools:
                # Check if tool has skip_next_call flag
                skip_next_call = tool.get("skip_next_call", False)

                # If skip_next_call is True, add instruction to description
                if skip_next_call and "function" in tool:
                    original_desc = tool["function"].get("description", "")
                    # Add warning about no feedback
                    tool["function"]["description"] = (
                        f"{original_desc}\n\n⚠️ Этот инструмент выполняется БЕЗ обратной связи. "
                        "Формулируй сообщение сразу готовым для пользователя."
                    )

                # Remove skip_next_call before sending to OpenAI (not part of their schema)
                clean_tool = {k: v for k, v in tool.items() if k != "skip_next_call"}
                processed_tools.append(clean_tool)

            return processed_tools
        except Exception as e:
            logger.error(f"Failed to load tools from {self.config.TOOLS_FILE}: {e}")
            return []

    def _should_skip_next_call(self, tool_calls: List[Any], tool_results: List[dict]) -> bool:
        """Check if we should skip the next AI call based on skip_next_call flags.

        Returns True if:
        - All executed tools have skip_next_call=true
        - All tools succeeded (no errors)

        Args:
            tool_calls: List of tool call objects from AI
            tool_results: List of tool result dicts with 'success' field

        Returns:
            bool: True if we should skip next AI call
        """
        if not tool_calls or not tool_results:
            return False

        # Load tools configuration to check skip_next_call flags
        try:
            with open(self.config.TOOLS_FILE, "r", encoding="utf-8") as f:
                tools_config = json.load(f)

            # Create a mapping of tool names to skip_next_call flags
            skip_flags = {}
            for tool in tools_config:
                if "function" in tool and "name" in tool["function"]:
                    tool_name = tool["function"]["name"]
                    skip_flags[tool_name] = tool.get("skip_next_call", False)

            # Check each executed tool
            for tool_call, tool_result in zip(tool_calls, tool_results):
                tool_name = tool_call.function.name

                # If any tool doesn't have skip_next_call=true, continue normally
                if not skip_flags.get(tool_name, False):
                    return False

                # If any tool failed, continue normally (AI needs to handle error)
                if not tool_result.get("success", False):
                    return False

            # All tools have skip_next_call=true AND all succeeded
            return True

        except Exception as e:
            logger.warning(f"Failed to check skip_next_call flags: {e}")
            # On error, play it safe and don't skip
            return False

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
            elif name == "get_news":
                limit = min(args.get("limit", 10), 20)
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
            elif name == "add_sticker":
                description = args.get("description", "").strip()
                msg_id = args.get("message_id")

                if not description:
                    content = "Error: Description is required"
                elif not msg_id:
                    content = "Error: Message ID is required"
                else:
                    # Get sticker file_id from the message
                    sticker_file_id = None

                    # Check if current message has sticker with matching ID
                    if self._current_message and hasattr(self._current_message, "message_id"):
                        if self._current_message.message_id == msg_id and hasattr(
                            self._current_message, "sticker"
                        ):
                            if self._current_message.sticker:
                                sticker_file_id = self._current_message.sticker.file_id

                    # If not found in current message, try to find in chat logs by message_id
                    if not sticker_file_id and self._current_message:
                        chat_id = self._current_message.chat.id

                        # Try to get file_id directly from chat logs
                        sticker_file_id = self.chat_logs_repo.get_file_id_by_message_id(
                            chat_id, msg_id
                        )

                        # If not found, check nearby messages in order: -1, +1, -2, +2
                        if not sticker_file_id:
                            for offset in [-1, 1, -2, 2]:
                                nearby_id = msg_id + offset
                                sticker_file_id = self.chat_logs_repo.get_file_id_by_message_id(
                                    chat_id, nearby_id
                                )
                                if sticker_file_id:
                                    logger.info(
                                        f"Sticker found at nearby message_id={nearby_id} (offset {offset} from {msg_id})"
                                    )
                                    break

                        # If still not found, check if user replied to a sticker message
                        if not sticker_file_id and (
                            hasattr(self._current_message, "reply_to_message")
                            and self._current_message.reply_to_message
                            and hasattr(self._current_message.reply_to_message, "sticker")
                            and self._current_message.reply_to_message.sticker
                        ):
                            if self._current_message.reply_to_message.message_id == msg_id:
                                sticker_file_id = (
                                    self._current_message.reply_to_message.sticker.file_id
                                )

                    if sticker_file_id:
                        try:
                            result = self.stickers_repo.add_sticker(description, sticker_file_id)
                            if result["success"]:
                                content = result["message"] + " в базу данных!"
                            else:
                                # Duplicate found
                                content = result["message"]
                        except Exception as e:
                            logger.exception("Failed to add sticker")
                            content = f"Ошибка при добавлении стикера: {str(e)}"
                    else:
                        content = f"Не удалось найти стикер с message_id={msg_id}. Убедитесь, что это сообщение со стикером."
            elif name == "rename_sticker":
                old_name = args.get("old_name", "").strip()
                new_name = args.get("new_name", "").strip()
                msg_id = args.get("message_id")

                if not new_name:
                    content = "Error: Новое название обязательно"
                elif not old_name and not msg_id:
                    content = "Error: Укажите либо старое название (old_name), либо ID сообщения (message_id)"
                else:
                    # If message_id provided, find sticker by file_id
                    if msg_id and not old_name:
                        sticker_file_id = None

                        # Try to get file_id from chat logs
                        if self._current_message:
                            chat_id = self._current_message.chat.id
                            sticker_file_id = self.chat_logs_repo.get_file_id_by_message_id(
                                chat_id, msg_id
                            )

                            # Check nearby messages if not found
                            if not sticker_file_id:
                                for offset in [-1, 1, -2, 2]:
                                    nearby_id = msg_id + offset
                                    sticker_file_id = self.chat_logs_repo.get_file_id_by_message_id(
                                        chat_id, nearby_id
                                    )
                                    if sticker_file_id:
                                        logger.info(
                                            f"Sticker found at nearby message_id={nearby_id} (offset {offset} from {msg_id})"
                                        )
                                        break

                        if sticker_file_id:
                            # Find sticker name by file_id
                            old_name = self.stickers_repo.find_by_file_id(sticker_file_id)
                            if not old_name:
                                content = f"Стикер с message_id={msg_id} не найден в базе данных. Возможно, его нужно сначала добавить."
                        else:
                            content = f"Не удалось найти стикер с message_id={msg_id}. Убедитесь, что это сообщение со стикером."

                    # Perform rename if we have old_name
                    if old_name:
                        try:
                            result = self.stickers_repo.rename_sticker(old_name, new_name)
                            if result["success"]:
                                content = result["message"]
                            else:
                                content = result["message"]
                                # Add similar suggestions if available
                                if result.get("similar_stickers"):
                                    similar_list = ", ".join(result["similar_stickers"])
                                    content += f"\n\nВозможно, вы имели в виду: {similar_list}"
                        except Exception as e:
                            logger.exception("Failed to rename sticker")
                            content = f"Ошибка при переименовании стикера: {str(e)}"

            elif name == "save_memory":
                scope = args.get("scope", "chat").strip()
                content_text = args.get("content", "").strip()
                tags = args.get("tags", [])

                if scope not in ["chat", "user"]:
                    content = "Error: scope must be 'chat' or 'user'"
                elif not content_text:
                    content = "Error: Content is required"
                elif not self._current_message:
                    content = "Error: Available only in message context"
                else:
                    try:
                        chat_id = self._current_message.chat.id
                        user_id = self._current_message.from_user.id
                        author_id = user_id

                        # Determine scope_id based on scope
                        if scope == "chat":
                            scope_id = chat_id
                            # Check for duplicates in chat memory
                            existing_memories = self.memory_repo.get_chat_memories(chat_id)
                        else:  # scope == "user"
                            scope_id = user_id
                            # Check for duplicates in user memory
                            existing_memories = self.memory_repo.get_user_memories(user_id)

                        # Check for duplicates by tags
                        duplicate_found = None
                        if tags:
                            tags_set = set(tag.lower() for tag in tags)

                            for memory in existing_memories:
                                existing_tags = set(tag.lower() for tag in memory.get("tags", []))
                                # If at least 2 tags match or all tags match (for single tag case)
                                if existing_tags and tags_set:
                                    matches = tags_set & existing_tags
                                    if len(matches) >= min(2, len(tags_set)):
                                        duplicate_found = memory
                                        break

                        if duplicate_found:
                            # Found duplicate by tags
                            mem_id = duplicate_found["id"][:8]
                            mem_content = duplicate_found["content"]
                            mem_tags = ", ".join(duplicate_found.get("tags", []))

                            scope_label = "чата" if scope == "chat" else "пользователя"
                            content = (
                                f"❌ Такая запись уже существует в памяти {scope_label}:\n\n"
                                f"[ID: {mem_id}]\n"
                                f"{mem_content}\n"
                                f"Теги: {mem_tags}\n\n"
                                f"💡 Эта информация уже сохранена, но её можно изменить."
                            )
                            logger.info(
                                f"Duplicate memory found in {scope} {scope_id} by tags {tags}, not adding"
                            )
                        else:
                            # No duplicate found, add as usual
                            if scope == "chat":
                                memory_id = self.memory_repo.add_chat_memory(
                                    chat_id=chat_id,
                                    content=content_text,
                                    tags=tags,
                                    author_id=author_id,
                                )
                                content = f"✅ Запомнил (память чата): {content_text[:50]}..."
                                logger.info(f"Saved chat memory {memory_id} for chat {chat_id}")
                            else:  # scope == "user"
                                memory_id = self.memory_repo.add_user_memory(
                                    user_id=user_id, content=content_text, tags=tags
                                )
                                content = (
                                    f"✅ Запомнил (память о пользователе): {content_text[:50]}..."
                                )
                                logger.info(f"Saved user memory {memory_id} for user {user_id}")

                            # Track memory update for user notification
                            self._memory_updates.append(f"{content_text}")
                    except Exception as e:
                        logger.exception("Failed to save memory")
                        content = f"Ошибка при сохранении: {str(e)}"

            elif name == "update_memory":
                search_query = args.get("search_query", "").strip()
                scope = args.get("scope", "chat").strip()
                new_content = args.get("content")
                new_tags = args.get("tags")

                if not search_query:
                    content = "Error: search_query is required"
                elif scope not in ["chat", "user"]:
                    content = "Error: scope must be 'chat' or 'user'"
                elif not new_content and not new_tags:
                    content = "Error: At least one of content or tags must be provided"
                elif not self._current_message:
                    content = "Error: Available only in message context"
                else:
                    try:
                        chat_id = self._current_message.chat.id
                        user_id = self._current_message.from_user.id

                        # Determine scope_id
                        scope_id = chat_id if scope == "chat" else user_id
                        scope_label = "памяти чата" if scope == "chat" else "памяти о пользователе"

                        # Search for memory
                        found_memories = self.memory_repo.search_memories(
                            scope, scope_id, search_query
                        )

                        if found_memories:
                            # Update the first match
                            memory_to_update = found_memories[0]
                            memory_id = memory_to_update["id"]

                            updated = self.memory_repo.update_memory(
                                scope=scope,
                                scope_id=scope_id,
                                memory_id=memory_id,
                                content=new_content,
                                tags=new_tags,
                            )

                            if updated:
                                content = f"✅ Обновил запись в {scope_label}: {memory_to_update['content'][:50]}..."
                                logger.info(f"Updated memory {memory_id} in {scope} {scope_id}")
                            else:
                                content = f"❌ Не удалось обновить запись (ID: {memory_id})"
                        else:
                            content = (
                                f"❌ Не нашел записи в {scope_label} по запросу: {search_query}"
                            )

                    except Exception as e:
                        logger.exception("Failed to update memory")
                        content = f"Ошибка при обновлении: {str(e)}"

            elif name == "delete_memory":
                search_query = args.get("search_query", "").strip()
                scope = args.get("scope", "chat").strip()

                if not search_query:
                    content = "Error: Search query is required"
                elif scope not in ["chat", "user"]:
                    content = "Error: scope must be 'chat' or 'user'"
                elif not self._current_message:
                    content = "Error: Available only in message context"
                else:
                    try:
                        chat_id = self._current_message.chat.id
                        user_id = self._current_message.from_user.id

                        # Determine scope_id
                        scope_id = chat_id if scope == "chat" else user_id
                        scope_label = "памяти чата" if scope == "chat" else "памяти о пользователе"

                        # Search and delete
                        found = self.memory_repo.search_and_delete(scope, scope_id, search_query)
                        if found:
                            content = f"🗑️ Удалил из {scope_label}: {found['content'][:50]}..."
                            logger.info(f"Deleted memory from {scope} {scope_id}: {search_query}")
                        else:
                            content = (
                                f"❌ Не нашел записи в {scope_label} по запросу: {search_query}"
                            )
                    except Exception as e:
                        logger.exception("Failed to delete memory")
                        content = f"Ошибка при удалении: {str(e)}"

        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            content = f"Error executing tool: {str(e)}"

        # Determine if execution was successful (no errors)
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
            "name": name,
            "content": content,
            "success": is_success,  # Internal flag for skip_next_call logic
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
        context: MessageContext,
        message: Optional[types.Message] = None,
    ) -> List[dict]:
        """Build messages list for OpenAI API.

        Args:
            system_prompt: System prompt text
            context: Message context
            message: Telegram message for additional context

        Returns:
            List of message dictionaries in OpenAI format
        """
        # 1. Build System Message
        # ОПТИМИЗАЦИЯ ДЛЯ КЕШИРОВАНИЯ: статичный контент в начале, динамичный в конце

        # Add stickers list (static content - будет кешироваться)
        stickers = list(self.stickers_repo.get_all_stickers().keys())
        if stickers:
            stickers_text = ", ".join(sorted(stickers))
            system_prompt += f"\n\n## Доступные стикеры:\n{stickers_text}"

        # # Add RAG Knowledge Base
        # if context.rag_context:
        #     try:
        #         # Try to parse RAG context as JSON
        #         rag_data = json.loads(context.rag_context)
        #
        #         if "knowledge_base" in rag_data:
        #             kb_text = "\n\n# База знаний:\n"
        #             for item in rag_data["knowledge_base"]:
        #                 kb_text += f"\n{item['content']}\n"
        #             system_prompt += kb_text
        #
        #         # Add Chat Info if present in RAG data (unlikely but possible)
        #         if "chat_info" in rag_data:
        #             # ... logic from previous _build_user_input
        #             pass
        #
        #     except (json.JSONDecodeError, TypeError):
        #         # Fallback if RAG context is just text
        #         system_prompt += f"\n\n# Контекст:\n{context.rag_context}"

        # Add Chat Info (relatively static - будет кешироваться)
        info_text = "\n\n# Информация о чате:\n"

        # Start with basic info from context
        chat_info = {
            "title": context.chat.title,
            "type": context.chat.type,
        }

        # Try to load cached metadata for more fields if available
        try:
            cached = self.memory_repo.get_chat_metadata(context.chat.id)
            if cached:
                # Update title if missing in context (unlikely but possible)
                if not chat_info["title"] and cached.get("title"):
                    chat_info["title"] = cached.get("title")

                # Add extra fields
                if cached.get("description"):
                    chat_info["description"] = cached.get("description")
                if cached.get("invite_link"):
                    chat_info["invite_link"] = cached.get("invite_link")
        except Exception:
            pass

        info_parts = []
        if chat_info.get("title"):
            info_parts.append(f"Название: {chat_info['title']}")
        if chat_info.get("type"):
            info_parts.append(f"Тип: {chat_info['type']}")
        if chat_info.get("description"):
            info_parts.append(f"Описание: {chat_info['description']}")
        if chat_info.get("invite_link"):
            info_parts.append(f"Ссылка: {chat_info['invite_link']}")

        if info_parts:
            system_prompt += info_text + "\n".join(info_parts) + "\n"

        # Add Chat/User Memories (dynamic - НЕ будет кешироваться, но после статичных блоков)
        mem_text = "\n\n# Память:\n"
        has_memories = False

        if context.chat.id:
            try:
                # 1. Load chat memories (always include)
                chat_memories = self.memory_repo.get_chat_memories(context.chat.id)
                if chat_memories:
                    # Sort by timestamp (newest first)
                    sorted_memories = sorted(
                        chat_memories, key=lambda m: m.get("timestamp", ""), reverse=True
                    )

                    mem_text += "## Память чата:\n"
                    for m in sorted_memories:
                        content = m.get("content", "").strip()
                        if content:
                            mem_text += f"- {content}\n"
                            has_memories = True

                # 2. Load user memories if user is present
                if context.user and context.user.id:
                    user_memories = self.memory_repo.get_user_memories(context.user.id)
                    if user_memories:
                        # Sort by timestamp (newest first)
                        sorted_user_memories = sorted(
                            user_memories, key=lambda m: m.get("timestamp", ""), reverse=True
                        )

                        user_name = context.user.username or context.user.first_name
                        mem_text += f"\n## Память о пользователе {user_name}:\n"
                        for m in sorted_user_memories:
                            content = m.get("content", "").strip()
                            if content:
                                mem_text += f"- {content}\n"
                                has_memories = True

            except Exception as e:
                logger.warning(f"Failed to load memories in AIService: {e}")

        if has_memories:
            system_prompt += mem_text

        # Add Date (САМЫЙ ДИНАМИЧНЫЙ ЭЛЕМЕНТ - в конце для минимизации влияния на кеш)
        # ОПТИМИЗАЦИЯ: только дата дня без времени для кеширования на протяжении всего дня
        moscow_tz = timezone(timedelta(hours=3))
        date = datetime.now(tz=moscow_tz).strftime("%Y-%m-%d")  # Формат: 2026-02-10
        system_prompt += f"\n\nТекущая дата: {date}"

        messages = [{"role": "system", "content": system_prompt}]

        # 2. Build Chat History (Context)
        # Get history directly from repository helper
        # We need a message object to get history properly
        # If message is None, we might not be able to get history for "reply_to" context properly
        # but basic history comes from repository.

        if message:
            chat_context = self._build_chat_context_from_logs(context, message)
            recent_messages = chat_context.get("recent_messages", [])
        else:
            # Fallback if no message object (e.g. strict command measurement?)
            # Usually complete() is called with a message.
            recent_messages = []

        # Skip leading assistant messages (Amazon Nova fix, kept from original)
        first_user_found = False
        for msg in recent_messages:
            author = msg.get("author", "Unknown")
            is_bot = msg.get("is_bot", False)
            text = msg.get("text", "")
            image_bytes = msg.get("image_bytes")
            mime_type = msg.get("mime_type")

            if not text and not image_bytes:
                continue
            elif text and text.startswith("🔄 Бот перезагружен"):
                is_bot = True

            # Skip assistant messages until we find the first user message
            if not first_user_found:
                if is_bot:
                    continue
                first_user_found = True

            role = "assistant" if is_bot else "user"

            # Format content
            content = self._format_multimodal_message(text, author, is_bot, image_bytes, mime_type)

            messages.append({"role": role, "content": content})

        # Log message structure for debugging
        logger.info(f"Built {len(messages)} messages: {[m['role'] for m in messages]}")

        return messages

    def _format_multimodal_message(
        self,
        text: str,
        author: str,
        is_bot: bool,
        image_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> Any:
        """Format a message for OpenAI API, handling text and images."""

        # Base text format
        text_content = text if is_bot else f"{author}: {text}"

        if image_bytes and mime_type and self.config.AI_MULTIMODAL_CONTEXT:
            # Multimodal content
            content_parts = []
            if text:
                content_parts.append({"type": "text", "text": text_content})

            data_url = self._make_data_url(image_bytes, mime_type)
            content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
            return content_parts
        else:
            # Text only
            return text_content

    async def _call_openai(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Call OpenAI API."""
        # Debug logging for xAI 422 error
        import json

        try:
            logger.warn(f"Sending request to OpenAI with {len(messages)} messages")
            # Log the last 3 messages to avoid clutter, but fully
            last_msgs = messages[-3:] if len(messages) > 3 else messages
            logger.warn(
                f"Last messages payload: {json.dumps(last_msgs, default=str, ensure_ascii=False)}"
            )
        except Exception:
            pass

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

        # Parse and extract reactions
        text, reactions = self._parse_reactions(text)

        # Store reactions for later processing
        self._pending_reactions = reactions

        # Filter out hallucinated empty markdown links like ]() that sometimes repeat endlessly
        import re

        text = re.sub(r"(\]\(){2,}", "", text)

        return remove_html(text)

    def _parse_reactions(self, text: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Parse reaction markers from AI response.

        Args:
            text: AI response text

        Returns:
            Tuple of (cleaned_text, reactions_list)
            reactions_list: [(emoji, excerpt), ...]
        """
        import re

        # Pattern: [emoji:😊:выдержка из текста]
        pattern = r"\[emoji:(.*?):(.*?)\]"
        reactions = []

        for match in re.finditer(pattern, text):
            emoji = match.group(1).strip()
            excerpt = match.group(2).strip()
            if emoji and excerpt:
                reactions.append((emoji, excerpt))
                logger.info(f"Parsed reaction: {emoji} for excerpt: {excerpt[:30]}...")

        # Remove markers from text (including surrounding newlines)
        # Pattern matches optional newlines before/after the emoji marker
        cleaned_text = re.sub(r"\n*\[emoji:.*?:.*?\]\n*", "", text)
        # Clean up multiple consecutive newlines that might remain
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

        return cleaned_text, reactions

    def _find_message_by_excerpt(
        self, chat_id: int, excerpt: str, limit: int = 50
    ) -> Optional[int]:
        """Find message ID by text excerpt in chat history.

        Args:
            chat_id: Chat ID
            excerpt: Text excerpt to search for
            limit: Number of recent messages to search

        Returns:
            Message ID if found, None otherwise
        """
        try:
            recent = self.chat_logs_repo.get_recent_messages(chat_id, limit)
            excerpt_lower = excerpt.lower()

            # Search from newest to oldest
            for msg in reversed(recent):
                msg_id, author, is_bot, text, *_ = msg
                if not text:
                    continue

                if excerpt_lower in text.lower():
                    logger.info(f"Found message {msg_id} matching excerpt: {excerpt[:30]}...")
                    return msg_id

            return None
        except Exception:
            logger.exception(f"Error finding message by excerpt: {excerpt}")
            return None

    async def _set_pending_reactions(self, chat_id: int, bot) -> None:
        """Set reactions that were parsed from AI response.

        Args:
            chat_id: Chat ID
            bot: Bot instance for setting reactions
        """
        if not self._pending_reactions:
            return

        from aiogram.types import ReactionTypeEmoji

        for emoji, excerpt in self._pending_reactions:
            try:
                # Find message by excerpt
                msg_id = self._find_message_by_excerpt(chat_id, excerpt)

                if msg_id:
                    await bot.set_message_reaction(
                        chat_id=chat_id,
                        message_id=msg_id,
                        reaction=[ReactionTypeEmoji(emoji=emoji)],
                    )
                    logger.info(
                        f"Set reaction {emoji} on message {msg_id} (excerpt: {excerpt[:20]}...)"
                    )
                else:
                    logger.warning(
                        f"Could not find message for reaction {emoji} with excerpt: {excerpt[:30]}..."
                    )
            except Exception as e:
                logger.warning(f"Failed to set reaction {emoji}: {e}")

        # Clear pending reactions
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

        # Add recent messages (with images!)
        recent = self.chat_logs_repo.get_recent_messages(context.chat.id, 10)
        if recent:
            recent_messages = []
            for msg_data in recent:
                # Unpack: (message_id, author, is_bot, text, image_bytes, mime_type, file_id, reactions)
                (
                    message_id,
                    author,
                    is_bot,
                    text,
                    image_bytes,
                    mime_type,
                    file_id,
                    reactions,
                ) = msg_data

                # Format reactions string
                # We have dict[int, list[str]], we want unique emojis
                reaction_text = ""
                if reactions:
                    all_emojis = set()
                    for user_emojis in reactions.values():
                        for emoji in user_emojis:
                            all_emojis.add(emoji)

                    if all_emojis:
                        reaction_text = f" [Реакции: {', '.join(sorted(all_emojis))}]"

                msg_dict = {
                    "message_id": message_id,
                    "author": author,
                    "is_bot": is_bot,
                    "text": text + reaction_text,
                }

                # Include image data if present
                if image_bytes and mime_type:
                    msg_dict["image_bytes"] = image_bytes
                    msg_dict["mime_type"] = mime_type

                recent_messages.append(msg_dict)
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

    async def _check_user_budget(self, user_id: int, chat_id: int) -> Optional[str]:
        """Check if user is approaching budget limit.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID

        Returns:
            Warning message if approaching limit, None otherwise
        """
        try:
            tokens_used = self.telemetry_repo.get_user_tokens_in_window(
                user_id, hours=self.config.TELEMETRY_WINDOW_HOURS
            )
            soft_limit = self.config.TELEMETRY_SOFT_LIMIT_TOKENS

            # Warning at 90% of limit
            if tokens_used > soft_limit * 0.9:
                remaining = soft_limit - tokens_used
                return (
                    f"\n\n⚠️ <b>Внимание:</b> использовано {tokens_used:,} токенов "
                    f"за последние {self.config.TELEMETRY_WINDOW_HOURS} часа "
                    f"(лимит: {soft_limit:,}, осталось: {remaining:,})"
                )
            return None
        except Exception:
            logger.exception("Failed to check user budget")
            return None
