"""Tool execution mixin for AIService."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable

import msgspec
import msgspec.json as mjson
import structlog

if TYPE_CHECKING:
    from aiogram import types

log = structlog.get_logger(__name__)


class ToolResult(msgspec.Struct):
    """Result of a tool call."""

    tool_call_id: str
    role: str = "tool"
    name: str = ""
    content: str = ""
    success: bool = True


class AIToolsMixin:
    """Mixin that provides tool execution for AIService."""

    # These attributes are provided by AIService.__init__
    mb_api: Any
    mc_api: Any
    news_api: Any
    tavily_api: Any
    stickers_repo: Any
    memory_repo: Any
    chat_logs_repo: Any
    config: Any
    _memory_updates: list
    _current_message: Any
    _tools_raw: list
    _tools_skip_flags: dict[str, bool]

    # -------------------------------------------------------------------------
    # Tools registry
    # -------------------------------------------------------------------------

    def _build_tool_handlers(self) -> dict[str, Callable]:
        return {
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

    def _get_tools(self) -> list[dict]:
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

    def _should_skip_next_call(self, tool_calls: list[Any], tool_results: list[ToolResult]) -> bool:
        """Return True if all tools have skip_next_call=True and all succeeded."""
        if not tool_calls or not tool_results:
            return False
        for tool_call, result in zip(tool_calls, tool_results):
            if not self._tools_skip_flags.get(tool_call.function.name, False):
                return False
            if not result.success:
                return False
        return True

    def _tool_result(self, tool_call: Any, content: str) -> ToolResult:
        """Build a ToolResult from a tool call and its content string."""
        is_success = not any(
            [
                content.startswith("Error:"),
                content.startswith("Ошибка:"),
                content.startswith("❌"),
                "Не удалось" in content,
                "не найден" in content.lower(),
            ]
        )
        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.function.name,
            content=content,
            success=is_success,
        )

    async def _execute_tool(self, tool_call: Any) -> ToolResult:
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

    def _find_sticker_file_id(self, msg_id: int) -> str | None:
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
