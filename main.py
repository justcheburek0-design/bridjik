"""Main entry point for the bot."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import structlog

from core.dependencies import Container
from infrastructure.health import start_health_server
from presentation.handlers import admin_memories, admin_stickers, callbacks, messages
from presentation.handlers.commands import admin, info, server, start, user

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)

log = structlog.get_logger(__name__)

_shutdown_event = None


def _handle_signal(signum, frame):
    """Handle SIGTERM and SIGINT signals for immediate shutdown."""
    sig_name = signal.Signals(signum).name
    log.warning("signal.received", signal=sig_name)
    if _shutdown_event:
        _shutdown_event.set()
    sys.exit(0)


async def on_startup(container: Container):
    """Execute on bot startup."""
    try:
        me = await container.bot.get_me()
        log.info("bot.started", username=me.username or "unknown")

        if me.username:
            container.config.BOT_USERNAME = me.username

        restart_message = f"🔄 Бот перезагружен (версия {container.config.VERSION})"
        restart_count = 0
        for chat_id in container.chat_logs_repo._logs.keys():
            recent = container.chat_logs_repo.get_recent_messages(chat_id, limit=1)
            if recent:
                last_text = recent[-1][3] if len(recent[-1]) > 3 else ""
                if last_text.startswith("🔄 Бот перезагружен"):
                    continue

            container.chat_logs_repo.add_message(
                chat_id=chat_id,
                author="System",
                is_bot=True,
                text=restart_message,
                message_id=None,
            )
            restart_count += 1
        log.info(
            "bot.restart_logged",
            count=restart_count,
            total=len(container.chat_logs_repo._logs),
        )
    except Exception:
        log.exception("bot.startup_failed")


async def on_shutdown(container: Container):
    """Execute on bot shutdown."""
    log.info("bot.shutting_down")

    try:
        aclose = getattr(container.openai_client, "aclose", None)
        if callable(aclose) and asyncio.iscoroutinefunction(aclose):
            async with asyncio.timeout(2.0):
                await aclose()
            log.debug("openai.client_closed")
        elif callable(aclose):
            aclose()
    except TimeoutError:
        log.warning("openai.close_timeout")
    except Exception:
        log.exception("openai.close_error")

    try:
        async with asyncio.timeout(2.0):
            await container.bot.session.close()
        log.debug("bot.session_closed")
    except TimeoutError:
        log.warning("bot.session_close_timeout")
    except Exception:
        log.exception("bot.session_close_error")

    log.info("bot.shutdown_complete")


def register_handlers(container: Container):
    """Register all handlers with dependency injection."""
    dp = container.dispatcher
    deps = container.get_handler_dependencies()

    dp.include_router(start.router)
    dp.include_router(user.router)
    dp.include_router(info.router)
    dp.include_router(server.router)
    dp.include_router(admin.router)
    dp.include_router(admin_stickers.router)
    dp.include_router(admin_memories.router)
    dp.include_router(callbacks.router)
    dp.include_router(messages.router)

    for key, value in deps.items():
        dp[key] = value

    log.info("handlers.registered")


async def main():
    """Main function."""
    log.info("bot.starting")

    # Start health check server
    health_runner = await start_health_server()
    log.info("health.server_started", port=8000)

    container = Container()
    register_handlers(container)
    await on_startup(container)

    try:
        await container.dispatcher.start_polling(container.bot)
    except KeyboardInterrupt:
        log.info("bot.stopped_by_user")
    except Exception as e:
        log.exception("bot.fatal_error", error=str(e))
    finally:
        await health_runner.cleanup()
        await on_shutdown(container)


if __name__ == "__main__":
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
        _shutdown_event = asyncio.Event()
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("bot.shutdown_complete")
