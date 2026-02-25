"""Text formatters."""

from __future__ import annotations

from html import escape
from typing import Any


class Formatter:
    """Text formatter for bot responses."""

    @staticmethod
    def format_player_info(info: dict[str, Any]) -> str:
        """Format MineBridge player profile as safe Telegram HTML."""
        lines = []

        for key, value in info.items():
            if key == "Роли":
                roles_lines = "\n".join(f"• {escape(str(r))}" for r in value)
                lines.append(f"{escape(key)}:\n{roles_lines}")
            else:
                # Other simple fields and links
                lines.append(f"{escape(key)}: <code>{escape(str(value))}</code>")

        return "\n".join(lines)

    @staticmethod
    def format_freeze_message(username: str, hours: int, is_active: bool = True) -> str:
        """Format freeze status message."""
        from ..utils.text import get_hour_string

        if is_active:
            return f"🔐 Авто-ответы <b>выключены</b> для <b>{username}</b> на <b>{get_hour_string(hours)}</b>"
        else:
            return f"🔑 Авто-ответы <b>включены</b> для <b>{username}</b>"

    @staticmethod
    def format_error(message: str) -> str:
        """Format error message."""
        return f"<b>Ошибка</b> ⚠️\n{escape(message)}"

    @staticmethod
    def format_success(message: str) -> str:
        """Format success message."""
        return f"✅ {escape(message)}"
