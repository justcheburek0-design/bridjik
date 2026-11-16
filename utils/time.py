"""Moscow clock and message timestamps shared by prompts and tools."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")


def moscow_time(value: datetime | None = None) -> str:
    """Format a Telegram timestamp (naive values are UTC), or the live clock."""
    value = value if value is not None else datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW).strftime("%Y-%m-%d %H:%M:%S МСК (UTC+03:00)")


def timestamp_message(text: str, sent_at: datetime | None = None) -> str:
    return f"[Время сообщения: {moscow_time(sent_at)}] {text}"


def historical_message(text: str) -> str:
    """Never invent dates for messages recorded before timestamp support."""
    if text.startswith("[Время сообщения:"):
        return text
    return f"[Время сообщения: неизвестно] {text}"
