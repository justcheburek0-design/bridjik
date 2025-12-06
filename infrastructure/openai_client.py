"""OpenAI/OpenRouter client."""
from openai import AsyncOpenAI


def create_openai_client(
    api_key: str,
    base_url: str,
    site_url: str = "https://t.me/MineBridgeBot",
    app_name: str = "MineBridge"
) -> AsyncOpenAI:
    """Create and configure OpenAI client."""
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={
            "HTTP-Referer": site_url,
            "X-Title": app_name,
        }
    )

