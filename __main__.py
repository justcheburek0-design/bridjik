"""Main entry point for the bot."""
import asyncio
import logging

from core.dependencies import Container
from presentation.handlers.commands import start, user, info, server, game, admin
from presentation.handlers import messages, callbacks


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def on_startup(container: Container):
    """Execute on bot startup."""
    try:
        me = await container.bot.get_me()
        logger.info(f"Bot started: @{me.username or 'unknown'}")
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
    try:
        # Close OpenAI client
        aclose = getattr(container.openai_client, "aclose", None)
        if callable(aclose):
            if asyncio.iscoroutinefunction(aclose):
                await aclose()
            else:
                aclose()
    except Exception:
        logger.exception("Error closing openai client")
    
    try:
        await container.bot.session.close()
    except Exception:
        logger.exception("Error closing bot session")


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
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")

