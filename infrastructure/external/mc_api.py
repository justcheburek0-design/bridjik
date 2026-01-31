"""Minecraft server status API client."""

import asyncio
import logging
import re
from typing import Dict

import httpx


class MinecraftAPI:
    """Client for Minecraft server status API."""

    def __init__(self, server_host: str, cache_ttl: int = 20):
        self.server_host = server_host
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}

    async def fetch_status(self) -> dict:
        """Fetch server status with short-lived cache."""
        now = asyncio.get_event_loop().time()
        cached = self._cache.get(self.server_host)
        if cached and (now - cached[0] < self.cache_ttl):
            return cached[1]

        url = f"https://api.mcsrvstat.us/3/{self.server_host}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                self._cache[self.server_host] = (now, data)
                return data
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "")[:300]
            logging.exception(f"MC API HTTP {e.response.status_code}: {body}")
            return {}
        except Exception as e:
            logging.exception(f"MC API request failed: {e}")
            return {}

    def format_status_text(self, payload: dict) -> str:
        """Format server status as human-readable text."""
        online = bool(payload.get("online"))
        version = payload.get("version") or ""
        players_online = players_max = None

        if isinstance(payload.get("players"), dict):
            players_online = payload["players"].get("online")
            players_max = payload["players"].get("max")

        motd = ""
        try:
            motd_data = payload.get("motd") or {}
            motd_clean = motd_data.get("clean")
            if isinstance(motd_clean, list):
                motd = "\n".join(motd_clean)
            elif isinstance(motd_clean, str):
                motd = motd_clean
        except Exception:
            pass

        lines = [
            "<b>Статус MineBridge</b>",
            f"IP: <code>{self.server_host}</code>",
            f"Состояние: {'🟢 <b>ОНЛАЙН</b>' if online else '🔴 оффлайн'}",
        ]

        if version:
            lines.append(f"Версия: <code>{version}</code>")

        if players_online is not None and players_max is not None:
            lines.append(f"Игроков: <b>{players_online}</b> / <b>{players_max}</b>")
        elif players_online is not None:
            lines.append(f"Игроков онлайн: <b>{players_online}</b>")

        if motd:
            safe_motd = re.sub(r"([_*`])", r"\\\1", motd)
            lines.append(f"<code>{safe_motd}</code>")

        return "\n".join(lines)
