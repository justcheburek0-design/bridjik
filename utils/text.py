"""Text utilities."""
import hashlib


def shorten(text: str, limit: int = 700) -> str:
    """Shorten text to specified limit."""
    text = (text or "").strip()
    return (text[:limit] + "...") if len(text) > limit else text


def hash_text(text: str) -> str:
    """Create short deterministic hash for text."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def get_hour_string(hours: int) -> str:
    """Format hours as human-readable string in Russian."""
    if hours == 1:
        return "1 час"
    elif hours in (2, 3, 4):
        return f"{hours} часа"
    else:
        return f"{hours} часов"

