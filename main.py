"""Main entry point for the bot."""
import asyncio
import logging
import signal
import sys

from core.dependencies import Container
from presentation.handlers.commands import start, user, info, server, game, admin
from presentation.handlers import messages, callbacks


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_event = None


def _handle_signal(signum, frame):
    """Handle SIGTERM and SIGINT signals for immediate shutdown."""
    sig_name = signal.Signals(signum).name
    logger.warning(f"Received {sig_name} signal, initiating immediate shutdown...")
    
    # Set the shutdown event if it exists
    if _shutdown_event:
        _shutdown_event.set()
    
    # Exit immediately
    sys.exit(0)


async def on_startup(container: Container):
    """Execute on bot startup."""
    try:
        me = await container.bot.get_me()
        logger.info(f"Bot started: @{me.username or 'unknown'}")
        
        # Log bot restart to chat logs for all known chats
        restart_message = f"🔄 Бот перезагружен (версия {container.config.VERSION})"
        for chat_id in container.chat_logs_repo._logs.keys():
            container.chat_logs_repo.add_message(
                chat_id=chat_id,
                author="System",
                is_bot=True,
                text=restart_message
            )
        logger.info(f"Logged restart notification to {len(container.chat_logs_repo._logs)} chats")
    except Exception:
        logger.exception("Failed to get bot info on startup")
    
    # Initialize RAG index
    try:
        logger.info("Initializing RAG index...")
        await container.rag_service._ensure_rag_index()
        chunks = container.rag_service.get_chunks()
        logger.info(f"RAG index initialized with {len(chunks)} chunks")
    except Exception:
        logger.exception("RAG: failed to ensure index on startup")


async def on_shutdown(container: Container):
    """Execute on bot shutdown."""
    logger.info("Shutting down bot...")
    
    try:
        # Close OpenAI client with timeout
        aclose = getattr(container.openai_client, "aclose", None)
        if callable(aclose):
            try:
                if asyncio.iscoroutinefunction(aclose):
                    await asyncio.wait_for(aclose(), timeout=2.0)
                else:
                    aclose()
                logger.debug("OpenAI client closed")
            except asyncio.TimeoutError:
                logger.warning("OpenAI client close timeout")
    except Exception:
        logger.exception("Error closing openai client")
    
    try:
        # Close bot session with timeout
        await asyncio.wait_for(container.bot.session.close(), timeout=2.0)
        logger.debug("Bot session closed")
    except asyncio.TimeoutError:
        logger.warning("Bot session close timeout")
    except Exception:
        logger.exception("Error closing bot session")
    
    logger.info("Bot shutdown complete")


def register_handlers(container: Container):
    """Register all handlers with dependency injection."""
    dp = container.dispatcher
    deps = container.get_handler_dependencies()
    
    # Register routers with dependencies
    # Commands
    dp.include_router(start.router)
    dp.include_router(user.router)
    dp.include_router(info.router)
    dp.include_router(server.router)
    dp.include_router(game.router)
    dp.include_router(admin.router)
    
    # Messages and callbacks
    dp.include_router(callbacks.router)
    dp.include_router(messages.router)  # Messages router should be last
    
    # Inject dependencies into all routers
    for key, value in deps.items():
        dp[key] = value
    
    logger.info("All handlers registered")


async def main():
    """Main function."""
    logger.info("Starting MineBridge bot...")
    
    # Initialize container
    container = Container()
    
    # Register handlers
    register_handlers(container)
    
    # Startup
    await on_startup(container)
    
    try:
        # Start polling
        await container.dispatcher.start_polling(container.bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
    finally:
        await on_shutdown(container)


if __name__ == "__main__":
    try:
        # Set signal handlers
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
        
        # Set the global shutdown event
        _shutdown_event = asyncio.Event()
        
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")

