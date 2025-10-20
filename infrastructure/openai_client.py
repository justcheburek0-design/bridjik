"""OpenAI/OpenRouter client."""
from openai import AsyncOpenAI


def create_openai_client(api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> AsyncOpenAI:
    """Create and configure OpenAI client."""
    return AsyncOpenAI(api_key=api_key, base_url=base_url)

