"""Configuration management."""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict
from dotenv import load_dotenv

from __init__ import __version__

load_dotenv()


@dataclass
class Config:
    """Bot configuration."""
    
    # Telegram bot
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    BOT_USERNAME: str = "minebridge52bot"
    VERSION: str = __version__
    
    # Channels and URLs
    CHANNEL: str = field(default_factory=lambda: os.getenv("CHANNEL", "@MineBridgeOfficial"))
    SUPPORT_URL: str = field(default_factory=lambda: os.getenv("SUPPORT_URL", "https://t.me/HelpSupportMineBridgeBot"))
    DONATE_URL: str = field(default_factory=lambda: os.getenv("DONATE_URL", "https://m-br.ru/shop/buy"))
    
    # API Keys
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    GOOGLE_API_KEY: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    JINA_API_KEY: str = field(default_factory=lambda: os.getenv("JINA_API_KEY", ""))
    PIXABAY_API_KEY: str = field(default_factory=lambda: os.getenv("PIXABAY_API_KEY", ""))
    TAVILY_API_KEY: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    
    # MineBridge API
    MB_HOST: str = "майнбридж.рф"
    
    # Minecraft server
    MC_SERVER_HOST: str = field(default_factory=lambda: os.getenv("MC_SERVER_HOST", ""))
    MC_CACHE_TTL: int = 20
    
    # Paths
    BASE_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    KB_DIR: Path = field(init=False)
    DATA_DIR: Path = field(init=False)
    RAG_INDEX_DIR: Path = field(init=False)
    PROMPTS_DIR: Path = field(init=False)
    PSEVDO_FILE: Path = field(init=False)
    HISTORY_FILE: Path = field(init=False)
    CHAT_LOGS_FILE: Path = field(init=False)
    FREEZES_FILE: Path = field(init=False)
    GUESSES_FILE: Path = field(init=False)
    
    # Memory limits
    GROUP_MAX_MESSAGES: int = 12
    DM_MAX_MESSAGES: int = 5
    
    # RAG settings
    RAG_CHUNK_SIZE: int = 1500
    RAG_CHUNK_OVERLAP: int = 150
    RAG_MIN_CHUNKS: int = 1  # Minimum number of chunks to return
    RAG_MAX_CHUNKS: int = 12  # Maximum number of chunks to return
    RAG_SIMILARITY_THRESHOLD: float = 0.75  # Minimum relative score (0.0-1.0) compared to top chunk
    RAG_EMB_MODEL: str = "jina-embeddings-v3"
    RAG_EMB_BATCH: int = 64
    
    # AI Models
    AI_MODEL: str = field(default_factory=lambda: os.getenv("AI_MODEL", "x-ai/grok-4-fast"))
    GEMINI_MODEL: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    
    # Freeze options (hours)
    FREEZE_OPTIONS: tuple = (1, 4, 12, 24)
    
    # Stickers
    STICKERS: Dict[str, str] = field(default_factory=lambda: {
        "странно": "CAACAgIAAxkBAAEPdBxo186lIJy0-xIy1eyVATr_mznqcgACTykAAgaVeUsg2eL2ufOZazYE",
        "нененене": "CAACAgIAAxkBAAEPdB5o1868amdp5swyuMsK0q-vYdF3xgACpGsAAhD9aUohrd7s7TgHiTYE",
        "крутой": "CAACAgIAAxkBAAEPdCBo187UoSTA0plgabybnSl0-0A2RwACiScAAlny6UpGhvNYO5zAKTYE",
        "сердце": "CAACAgIAAxkBAAEPdCJo187ihaiZMqs3jb4JA9iDefJWAAP1MAACPssIS9HkZ_xXu5p8NgQ",
        "привет": "CAACAgIAAxkBAAEPdCRo1870kvBfRhY_6x5rYIcjfx5hNgAC-y8AAgddAUsyYDgvJ2NxsTYE",
        "лайк": "CAACAgIAAxkBAAEPdC5o188CQqA8WW6UAQiL5KxPPLp9cwAC6ycAAv3bCEvOUGWa8xaW9DYE",
        "о боже": "CAACAgIAAxkBAAEPdDBo188ORT0-fTIQERvrNXsfqNrNfAACcCsAAp4IGEiu0E3hQ-bTEzYE",
        "сердцеед": "CAACAgIAAxkBAAEPdDJo188cR-wb98SP8hLBBcTJS-r3_gACeDcAAu9rgUgMcsWUSzUqjzYE",
        "я пофигист": "CAACAgIAAxkBAAEPdDRo188oAjG2x0UeX6_D9px0wAk4jgACSi4AAl8eSEkr3MjFJi8laTYE",
        "держи ковры": "CAACAgIAAxkBAAEPdDZo1882YBAkfWi1PpoVVa61TqymKAACljEAAkaP6Umsr6VkooR7zDYE",
        "привет детка": "CAACAgIAAxkBAAEPdDpo189KlNe3Dqw-R21xCKwSgu742QACRDMAAh2XOUqdiCZZo0GihjYE",
        "я устал": "CAACAgIAAxkBAAEPdDxo189XMqbCH6qjwnilQkW9hHIAATwAAh82AAIYZJBLZ4zUWspr7j42BA",
        "50 причин стать чебуреком": "CAACAgIAAxkBAAEPdD5o189k-BTLsFVq1AUqJ3PeZTW6jAACgjcAAhh6OUhvWxhgrCGMnTYE",
        "это наши ковры": "CAACAgIAAxkBAAEPdEBo189xUrCzDAwaKuYnejNd61XFiAAC_jMAAqUvqUrFJS7nMu25SDYE",
        "логотип майнбридж": "CAACAgIAAxkBAAEPdEJo18-fuqN93cSINqXPM7HBjh0L7wAClnUAAqu9-UhOkKmCkgUirzYE",
        "злой": "CAACAgIAAxkBAAEPdERo18_Q5OgT5DBFMVi3kGYAAUHE9D8AAu19AAK9LOFLCOKT-E8Blu02BA",
        "кривой лайк": "CAACAgIAAxkBAAEPdEZo19AjPQIaU0oYTUkePqkIVuyD2gACckcAAoG0sEghn014r-GJBDYE",
        "думать": "CAACAgIAAxkBAAEPdEho19A5nx_GRpTSY7B9XoMeUpilBAACP4QAAhpcaEnlchnEqaCAQjYE",
        "absolute cinema": "CAACAgUAAxkBAAEPdEpo19BXo_yCCCvUJXqZsaDmkMpQ_gACoiIAAuJAmFX4ln_-jyOnojYE",
        "ааа чебурек": "CAACAgIAAxkBAAEPdExo19B3uclvmJcG_fw6o_GV_XNAygACmW8AAmn2KUhx7O9ebCGM9DYE",
        "донат": "CAACAgIAAxkBAAEPdE5o19CntqMNTUjkTXfWX-tGYX3sJgAC9SkAAnODmElZp4v_nv7G_DYE",
        "сасун": "CAACAgIAAxkBAAEPdFBo19C0nZ_k8W6rQLqZe-psaZ4mkQAChDEAAt7P2Eh-W_CBrpdPSjYE",
        "программист": "CAACAgIAAxkBAAEPdFJo19DGzATA8Bb_JuCqW9azxwg3-gACUxgAAtkcCUuTTOAKMRASRzYE",
        "дададада": "CAACAgIAAxkBAAEPdFRo19DXMt-yFVwhZ_zYnsYS3II88wACLS0AApvBcUos_YGp9A1KYzYE",
        "омагад": "CAACAgIAAxkBAAEPdFZo19DrfRjZDJG6m4YVfbq6484-ZQACbAADT64DP65_iVH3bL_eNgQ",
        "каво мем": "CAACAgIAAxkBAAEPdFho19D9BKEsqGWBQSORenE4nFULtAACMAADOq1TFbyJ9Xyu41UENgQ",
        "осуждаю": "CAACAgIAAxkBAAEPdFpo19EVgVC2wij6ttj25JD6BRqucwACdQgAArtzaEpy0PTtNpgzNzYE",
        "произошёл трооллинг": "CAACAgIAAxkBAAEPdFxo19E6yKgckgl0kZm1zhVGnRlIgAACiwkAAtQocEr90H-KQtzpJzYE",
        "троллинг не удался": "CAACAgIAAxkBAAEPdF5o19FPNJDXRO52Gcp8B8cZXEZp2QAC_wYAAvQ-cEoeKrdTePgmSjYE",
        "бан": "CAACAgIAAxkBAAEPdGBo19FmQvHn_96Z2qly4R9JZrlRqQAC-wMAAuNuOhnmkaQ8f5x7gTYE",
        "свинья-паук": "CAACAgIAAxkBAAEPdGJo19Fy0DD8C3HHwH59lPMxWs0fOAACzgMAAuNuOhlMdELsVNZG3jYE",
        "понял": "CAACAgIAAxkBAAEPdGRo19GGVfaPQ-v6l9to-JLyXY4-JwAC_QMAAuNuOhkFraxiObgg8zYE",
        "не понял": "CAACAgIAAxkBAAEPdGZo19GUetpNzFesvbxuWq68nruWoAAC-gMAAuNuOhneeFh_QWSGtjYE",
        "эндер дракон в обычном мире": "CAACAgIAAxkBAAEPdGho19GbamD0KQP-HNmEh6ztSXbdggADBAAC4246GQABQFWDEcL2XzYE",
        "скобочка-стив": "CAACAgIAAxkBAAEPdGpo19GqRHawbSovbaZYpOqC5cIB5QACCAQAAuNuOhm7QrCupBDTMjYE",
        "лиса XD": "CAACAgIAAxkBAAEPdGxo19G4Km47XPUO1bHabzWcfbStvQACIwQAAuNuOhnT35jgRYDNAAE2BA",
        "этачё": "CAACAgIAAxkBAAEPdG5o19HHAV5py_M62T5MIOsHTXkt9QACKAUAAuNuOhlDVV50N0cFpjYE",
        "мем скала джонсон": "CAACAgIAAxkBAAEPdHBo19HXN6AaSMuqLuw7BTp4uSjC6AACyhMAAoyvMUhmhlHyjrTwgDYE",
        "кот качает головой": "CAACAgIAAxkBAAEPdHJo19H_3wuTPMITxs88zV7bruAn9gAC-z8AAq6uoEi8wbAnaQ14ZDYE",
        "понял осознал": "CAACAgIAAxkBAAEPdHRo19ITIiiTVs23V53PR-ofKHZ6egACej4AAqBFoUjbnntNL52jzDYE",
        "мозги мёрзнут": "CAACAgIAAxkBAAEPdHZo19JixuhFPL1Yn5kKESa8OV0dIwACAicAArwU8UrPXAIByUQcjjYE",
        "порево": "CAACAgIAAxkBAAEPdHho19J3XIG66Onpdlh7azH6zk1ZeQAC5CYAAuDg8ErT0gytemmbSjYE",
        "пон": "CAACAgIAAxkBAAEPdsxo2LIEJfGB0EKt2ds-3B1m6DmY8wACU1IAApN08Emwj5nw-krF-TYE",
        "покажи жопа": "CAACAgIAAxkBAAEPds5o2LaV739UX29Bmr32VZElS_7ebAAC5QMAAuNuOhkzeLGCxEclKzYE",
        "ахаха оой": "CAACAgIAAxkBAAEPdtBo2LgOEIfvyO8Ir2RhDkjZMaMpRgACn2kAAo1l8EryJ35lqVbCeTYE",
        "на кота падает бомба": "CAACAgIAAxkBAAEPedho277CHhKyEIpP_uv3q_HTom0I1wAC0R4AAmskwEvcFTxGmIq-aDYE",
        "ёжик кушает": "CAACAgIAAxkBAAEPedZo276eNLuYEjK6qs_nLREhlsnzsAACNBIAAhPX2EsAAbFTK7Zm0XQ2BA",
        "избивание": "CAACAgIAAxkBAAEPedpo278keWMqpYuB2NzkRuUWWE8hrwACpWkAAouCuUsz-7BQnjwGrjYE",
        "крутой школьник с битой": "CAACAgIAAxkBAAEPedxo2788zONHyeNbN-ZjcWRcISVJwAACNwADCouFHhLbTCP_OKFzNgQ",
        "голем повесился": "CAACAgIAAxkBAAEPed5o279XwOiAvcDWnNrD54UKEa8V1AACSwADCouFHp346BXWmq2HNgQ",
        "потеет": "CAACAgIAAxkBAAEPeeBo279yJ8elcCUszK0VopehIQwowwACz2kAAupcuUtMpGjn_EjAyDYE",
        "пепе с мечами": "CAACAgIAAxkBAAEPeeJo27-LuwxdCeZhkOe9LkLQXr6yggACVwADDnr7Ch9ftelV4vz7NgQ",
        "спидрань отсюда": "CAACAgIAAxkBAAEPeeRo27-ilQNaP9EPQrixhPv8D-1BywACO0QAAkj6kUrF3ZvhLYuXvjYE",
    })
    
    def __post_init__(self):
        """Initialize computed paths."""
        self.KB_DIR = self.BASE_DIR / "kb"
        self.DATA_DIR = self.BASE_DIR / "data"
        self.RAG_INDEX_DIR = self.BASE_DIR / ".rag_cache"
        self.PROMPTS_DIR = self.BASE_DIR / "prompts"
        self.PSEVDO_FILE = self.DATA_DIR / "psevdos.json"
        self.HISTORY_FILE = self.DATA_DIR / "history.json"
        self.CHAT_LOGS_FILE = self.DATA_DIR / "chat_logs.json"
        self.FREEZES_FILE = self.DATA_DIR / "freezes.json"
        self.GUESSES_FILE = self.DATA_DIR / "guesses.json"
        
        # Ensure data directory exists
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> None:
        """Validate required configuration."""
        from core.exceptions import ConfigurationError
        
        if not self.BOT_TOKEN:
            raise ConfigurationError("BOT_TOKEN is required in .env")
        if not self.OPENAI_API_KEY:
            raise ConfigurationError("OPENAI_API_KEY is required in .env")
        if not self.MC_SERVER_HOST:
            raise ConfigurationError("MC_SERVER_HOST is required in .env")
        if not self.JINA_API_KEY:
            raise ConfigurationError("JINA_API_KEY is required in .env")
        if not self.GOOGLE_API_KEY:
            raise ConfigurationError("GOOGLE_API_KEY is required in .env")
        if not self.PIXABAY_API_KEY:
            raise ConfigurationError("PIXABAY_API_KEY is required in .env")
        if not self.DONATE_URL.startswith("http"):
            raise ConfigurationError("DONATE_URL must be a valid URL")
        if not self.SUPPORT_URL.startswith("http"):
            raise ConfigurationError("SUPPORT_URL must be a valid URL")

