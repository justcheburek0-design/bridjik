"""Tool definitions for the AI agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic_ai import Agent, RunContext

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


def register_tools(agent: "Agent[Any, str]") -> None:
    """Register all tool handlers on the given agent."""

    @agent.tool
    async def get_player_info(ctx: RunContext[Any], query: str) -> str:
        """Get MineBridge player info by name or UUID."""
        import msgspec.json as mjson

        data = await ctx.deps.mb_api.search_player(query)
        return mjson.encode(data).decode() if data else "Player not found"

    @agent.tool
    async def get_server_status(ctx: RunContext[Any]) -> str:
        """Get current Minecraft server status."""
        import msgspec.json as mjson

        data = await ctx.deps.mc_api.fetch_status()
        return mjson.encode(data).decode()

    @agent.tool
    async def get_news(ctx: RunContext[Any], limit: int = 10, offset: int = 0) -> str:
        """Get MineBridge news feed."""
        import msgspec.json as mjson

        data = await ctx.deps.news_api.fetch_news(min(limit, 20), offset)
        return mjson.encode(data).decode() if data else "Failed to fetch news"

    @agent.tool
    async def get_events(ctx: RunContext[Any], season: int = -1) -> str:
        """Get MineBridge events for a season (-1 = current)."""
        import msgspec.json as mjson

        data = await ctx.deps.mb_api.fetch_events(season)
        return mjson.encode(data).decode() if data else "Failed to fetch events"

    @agent.tool
    async def get_top_players(ctx: RunContext[Any], limit: int = 5, offset: int = 0) -> str:
        """Get top players leaderboard."""
        import msgspec.json as mjson

        data = await ctx.deps.mb_api.fetch_top_players(min(limit, 15), offset)
        return mjson.encode(data).decode() if data else "Failed to fetch top players"

    @agent.tool
    async def web_search(ctx: RunContext[Any], query: str, max_results: int = 5) -> str:
        """Search the web for up-to-date information."""
        data = await ctx.deps.tavily_api.search(query, max_results=min(max_results, 10))
        return ctx.deps.tavily_api.format_results(data) if data else "Failed to perform web search"

    @agent.tool
    async def add_sticker(ctx: RunContext[Any], description: str, message_id: int) -> str:
        """Save a sticker from a message to the sticker database."""
        description = description.strip()
        if not description:
            return "Error: Description is required"

        sticker_file_id = ctx.deps.find_sticker_file_id(message_id)
        if not sticker_file_id:
            return f"Не удалось найти стикер с message_id={message_id}. Убедитесь, что это сообщение со стикером."

        result = ctx.deps.stickers_repo.add_sticker(description, sticker_file_id)
        return (result["message"] + " в базу данных!") if result["success"] else result["message"]

    @agent.tool
    async def rename_sticker(
        ctx: RunContext[Any],
        new_name: str,
        old_name: str = "",
        message_id: int | None = None,
    ) -> str:
        """Rename a sticker by old name or message_id."""
        new_name = new_name.strip()
        old_name = old_name.strip()

        if not new_name:
            return "Error: Новое название обязательно"
        if not old_name and not message_id:
            return "Error: Укажите либо старое название (old_name), либо ID сообщения (message_id)"

        if message_id and not old_name:
            sticker_file_id = ctx.deps.find_sticker_file_id(message_id)
            if sticker_file_id:
                old_name = ctx.deps.stickers_repo.find_by_file_id(sticker_file_id) or ""
                if not old_name:
                    return f"Стикер с message_id={message_id} не найден в базе данных. Возможно, его нужно сначала добавить."
            else:
                return f"Не удалось найти стикер с message_id={message_id}."

        if not old_name:
            return "Error: Не удалось определить старое название стикера"

        result = ctx.deps.stickers_repo.rename_sticker(old_name, new_name)
        content = result["message"]
        if not result["success"] and result.get("similar_stickers"):
            content += f"\n\nВозможно, вы имели в виду: {', '.join(result['similar_stickers'])}"
        return content

    @agent.tool
    async def save_memory(
        ctx: RunContext[Any],
        content: str,
        scope: str = "chat",
        tags: list[str] | None = None,
    ) -> str:
        """Save a memory about the chat or a user. scope: 'chat' or 'user'."""
        tags = tags or []
        content = content.strip()

        if scope not in ("chat", "user"):
            return "Error: scope must be 'chat' or 'user'"
        if not content:
            return "Error: Content is required"

        ctx_ids = ctx.deps.require_message_context()
        if isinstance(ctx_ids, str):
            return ctx_ids
        chat_id, user_id = ctx_ids

        existing = (
            ctx.deps.memory_repo.get_chat_memories(chat_id)
            if scope == "chat"
            else ctx.deps.memory_repo.get_user_memories(user_id)
        )

        if tags:
            tags_set = {t.lower() for t in tags}
            for memory in existing:
                existing_tags = {t.lower() for t in memory.get("tags", [])}
                if existing_tags and len(tags_set & existing_tags) >= min(2, len(tags_set)):
                    scope_label = "чата" if scope == "chat" else "пользователя"
                    return (
                        f"❌ Такая запись уже существует в памяти {scope_label}:\n\n"
                        f"[ID: {memory['id'][:8]}]\n{memory['content']}\n"
                        f"Теги: {', '.join(memory.get('tags', []))}\n\n"
                        f"💡 Эта информация уже сохранена, но её можно изменить."
                    )

        if scope == "chat":
            memory_id = ctx.deps.memory_repo.add_chat_memory(
                chat_id=chat_id, content=content, tags=tags, author_id=user_id
            )
            log.info("memory.saved", scope="chat", chat_id=chat_id, memory_id=memory_id)
            ctx.deps.memory_updates.append(content)
            return f"✅ Запомнил (память чата): {content[:50]}..."

        memory_id = ctx.deps.memory_repo.add_user_memory(
            user_id=user_id, content=content, tags=tags
        )
        log.info("memory.saved", scope="user", user_id=user_id, memory_id=memory_id)
        ctx.deps.memory_updates.append(content)
        return f"✅ Запомнил (память о пользователе): {content[:50]}..."

    @agent.tool
    async def update_memory(
        ctx: RunContext[Any],
        search_query: str,
        scope: str = "chat",
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Update an existing memory by search query. scope: 'chat' or 'user'."""
        search_query = search_query.strip()

        if not search_query:
            return "Error: search_query is required"
        if scope not in ("chat", "user"):
            return "Error: scope must be 'chat' or 'user'"
        if not content and not tags:
            return "Error: At least one of content or tags must be provided"

        ctx_ids = ctx.deps.require_message_context()
        if isinstance(ctx_ids, str):
            return ctx_ids
        chat_id, user_id = ctx_ids

        scope_id = chat_id if scope == "chat" else user_id
        scope_label = "памяти чата" if scope == "chat" else "памяти о пользователе"

        found = ctx.deps.memory_repo.search_memories(scope, scope_id, search_query)
        if not found:
            return f"❌ Не нашел записи в {scope_label} по запросу: {search_query}"

        memory_id = found[0]["id"]
        updated = ctx.deps.memory_repo.update_memory(
            scope=scope, scope_id=scope_id, memory_id=memory_id, content=content, tags=tags
        )
        if updated:
            log.info("memory.updated", scope=scope, scope_id=scope_id, memory_id=memory_id)
            return f"✅ Обновил запись в {scope_label}: {found[0]['content'][:50]}..."
        return f"❌ Не удалось обновить запись (ID: {memory_id})"

    @agent.tool
    async def delete_memory(ctx: RunContext[Any], search_query: str, scope: str = "chat") -> str:
        """Delete a memory by search query. scope: 'chat' or 'user'."""
        search_query = search_query.strip()

        if not search_query:
            return "Error: Search query is required"
        if scope not in ("chat", "user"):
            return "Error: scope must be 'chat' or 'user'"

        ctx_ids = ctx.deps.require_message_context()
        if isinstance(ctx_ids, str):
            return ctx_ids
        chat_id, user_id = ctx_ids

        scope_id = chat_id if scope == "chat" else user_id
        scope_label = "памяти чата" if scope == "chat" else "памяти о пользователе"

        found = ctx.deps.memory_repo.search_and_delete(scope, scope_id, search_query)
        if found:
            log.info("memory.deleted", scope=scope, scope_id=scope_id, query=search_query)
            return f"🗑️ Удалил из {scope_label}: {found['content'][:50]}..."
        return f"❌ Не нашел записи в {scope_label} по запросу: {search_query}"
