"""Dependency Injection container."""

from pathlib import Path

from application.services.ai import AIService
from application.services.game import GameService
from application.services.media import MediaService
from application.services.rag import RAGService
from application.services.strings import StringsService
from application.services.subscription import SubscriptionService
from application.services.user import UserService
from core.config import Config
from infrastructure.bot import create_bot, create_dispatcher
from infrastructure.external.gemini import GeminiAPI
from infrastructure.external.mb_api import MineBridgeAPI
from infrastructure.external.mc_api import MinecraftAPI
from infrastructure.external.news_api import NewsAPI
from infrastructure.external.tavily_api import TavilyAPI
from infrastructure.openai_client import create_openai_client
from infrastructure.repositories.chat_logs import ChatLogsRepository
from infrastructure.repositories.freezes import FreezesRepository
from infrastructure.repositories.guesses import GuessesRepository
from infrastructure.repositories.history import HistoryRepository
from infrastructure.repositories.psevdos import PsevdoRepository
from infrastructure.repositories.stickers import StickersRepository
from presentation.formatters import Formatter
from presentation.keyboards import KeyboardBuilder


class Container:
    """Dependency injection container."""

    def __init__(self):
        # Core
        self.config = Config()
        self.config.validate()

        # Infrastructure
        self.bot = create_bot(self.config.BOT_TOKEN)
        self.dispatcher = create_dispatcher()
        self.openai_client = create_openai_client(
            self.config.OPENAI_API_KEY,
            self.config.OPENAI_BASE_URL,
        )

        # Repositories
        self.history_repo = HistoryRepository(self.config.HISTORY_FILE, self.config.DM_MAX_MESSAGES)
        self.chat_logs_repo = ChatLogsRepository(
            self.config.CHAT_LOGS_FILE, self.config.GROUP_MAX_MESSAGES
        )
        self.psevdo_repo = PsevdoRepository(self.config.PSEVDO_FILE)
        self.freezes_repo = FreezesRepository(self.config.FREEZES_FILE)
        self.guesses_repo = GuessesRepository(self.config.GUESSES_FILE)
        self.stickers_repo = StickersRepository(self.config.STICKERS_FILE)

        # External APIs
        self.mc_api = MinecraftAPI(self.config.MC_SERVER_HOST, self.config.MC_CACHE_TTL)
        self.mb_api = MineBridgeAPI(self.config.MB_HOST)
        self.gemini_api = GeminiAPI(self.config.GOOGLE_API_KEY, self.config.GEMINI_MODEL)
        self.news_api = NewsAPI()
        self.tavily_api = TavilyAPI(self.config.TAVILY_API_KEY)

        # Services
        self.subscription_service = SubscriptionService(self.bot, self.config.CHANNEL)
        self.user_service = UserService(self.psevdo_repo)
        self.game_service = GameService(self.guesses_repo)
        self.ai_service = AIService(
            self.openai_client,
            self.history_repo,
            self.chat_logs_repo,
            self.config.AI_MODEL,
            self.mb_api,
            self.mc_api,
            self.news_api,
            self.tavily_api,
            self.config,
            self.stickers_repo,
        )
        self.media_service = MediaService(
            self.bot,
            self.config.BOT_TOKEN,
            self.config,
            self.stickers_repo,
            self.guesses_repo,
            self.openai_client,
        )
        self.rag_service = RAGService(self.config, self.mc_api, self.mb_api)
        self.strings_service = StringsService(self.config)

        # Presentation
        self.keyboard_builder = KeyboardBuilder(
            self.config.CHANNEL, self.config.SUPPORT_URL, self.config.DONATE_URL
        )
        self.formatter = Formatter()

    def get_handler_dependencies(self) -> dict:
        """Get dependencies dict for handlers."""
        return {
            "config": self.config,
            "bot": self.bot,
            "subscription_service": self.subscription_service,
            "user_service": self.user_service,
            "game_service": self.game_service,
            "ai_service": self.ai_service,
            "media_service": self.media_service,
            "rag_service": self.rag_service,
            "strings_service": self.strings_service,
            "mc_api": self.mc_api,
            "mb_api": self.mb_api,
            "gemini_api": self.gemini_api,
            "news_api": self.news_api,
            "tavily_api": self.tavily_api,
            "keyboard_builder": self.keyboard_builder,
            "formatter": self.formatter,
            "freezes_repo": self.freezes_repo,
            "history_repo": self.history_repo,
            "chat_logs_repo": self.chat_logs_repo,
            "stickers_repo": self.stickers_repo,
        }
