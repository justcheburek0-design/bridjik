"""MineBridge API client."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)


class MineBridgeAPI:
    """Client for MineBridge API."""

    def __init__(self, host: str, cache_ttl: float = 20.0):
        self.host = host
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[float, dict[str, Any] | None]] = {}

    def _make_punycode_host(self, host: str) -> str:
        """Convert domain with non-ASCII to punycode for HTTP requests."""
        try:
            return host.encode("idna").decode("ascii")
        except Exception:
            return host

    def _get_cache(self, key: str) -> dict[str, Any] | None:
        """Get value from cache if not expired."""
        row = self._cache.get(key)
        if not row:
            return None
        ts, val = row
        if time.time() - ts > self.cache_ttl:
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return val

    def _set_cache(self, key: str, val: dict[str, Any] | None) -> None:
        """Store API response in cache with current timestamp."""
        self._cache[key] = (time.time(), val)

    async def _fetch_json_from_api(self, player_id: str) -> dict[str, Any] | None:
        """Fetch player data from MineBridge API."""
        if not player_id:
            return None

        host = self._make_punycode_host(self.host)
        id_esc = quote_plus(player_id, safe="")
        url = f"https://{host}/api/tg/{id_esc}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                try:
                    return r.json()
                except Exception:
                    logger.exception("mb_api: failed to parse JSON for id %s", player_id)
                    return None
        except httpx.HTTPStatusError as e:
            status = getattr(e.response, "status_code", None)
            body = (getattr(e.response, "text", "") or "")[:500]
            logger.warning("mb_api: HTTP error %s for %s: %s", status, player_id, body)
            return None
        except Exception as e:
            logger.exception("mb_api: network error for %s: %s", player_id, e)
            return None

    async def fetch_player_by_id(
        self, player_id: str, use_cache: bool = True
    ) -> dict[str, Any] | None:
        """Fetch player information by ID."""
        if not player_id:
            return None

        key = f"mb:{player_id}"
        if use_cache:
            player = self._get_cache(key)
            if player is not None:
                return player

        player_data = await self._fetch_json_from_api(player_id)
        if player_data is None:
            return None

        return await self._process_player_data(player_data, key, use_cache)

    async def fetch_player_by_nickname(
        self, nickname: str, use_cache: bool = True
    ) -> dict[str, Any] | None:
        """Fetch player information by nickname."""
        if not nickname:
            return None

        key = f"mb:nick:{nickname.lower()}"
        if use_cache:
            player = self._get_cache(key)
            if player is not None:
                return player

        # Try to fetch using /api/player/{nickname} endpoint
        # Note: This is an assumed endpoint based on standard REST patterns
        # If it doesn't exist, we might need to rely on other methods or ask user for clarification
        host = self._make_punycode_host(self.host)
        nick_esc = quote_plus(nickname, safe="")
        url = f"https://{host}/api/name/{nick_esc}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                player_data = r.json()

                # Process data similar to fetch_player_by_id
                # Assuming the structure is similar or identical
                return await self._process_player_data(player_data, key, use_cache)
        except Exception:
            # Fallback: try to see if the nickname is actually an ID (if it's numeric)
            if nickname.isdigit():
                return await self.fetch_player_by_id(nickname, use_cache)

            logger.warning("mb_api: failed to fetch player by nickname %s", nickname)
            return None

    async def _process_player_data(
        self, player_data: dict[str, Any], cache_key: str, use_cache: bool
    ) -> dict[str, Any] | None:
        """Process raw player data and cache it."""
        urls_start = {
            "vk": {"url": "https://vk.com/", "label": "ВК"},
            "twitch": {"url": "https://www.twitch.tv/", "label": "Твич"},
            "youtube": {"url": "https://youtube.com/@", "label": "Ютуб"},
            "donationAlerts": {"url": "https://donationalerts.com/r/", "label": "Донат"},
        }

        try:
            player = {
                "Ник": player_data.get("name") or "N/A",
                "ТГ ID": player_data.get("telegramId") or "N/A",
                "Звёзды (рейтинг)": player_data.get("rating") or 0,
                "Погасшие звёзды (скидки)": player_data.get("faded_rating") or 0,
                "Наигранные часы": player_data.get("hours") or 0,
                "Был онлайн на сайте": player_data.get("onlineAt") or "N/A",
                "Мостики": player_data.get("mostiki") or 0,
                "Проходка на дней": player_data.get("days") or 0,
                "Аккаунт создан": player_data.get("createdAt") or "N/A",
                "Роли": player_data.get("roles") or [],
            }

            if player_data.get("discordId"):
                player["Дискорд"] = f"https://discord.com/users/{player_data['discordId']}"

            for key, val in player_data.get("urls", {}).items():
                if key in urls_start and val:
                    player[urls_start[key]["label"]] = f"{urls_start[key]['url']}{val}"

            if use_cache:
                self._set_cache(cache_key, player)

            return player
        except Exception:
            logger.exception("mb_api: unexpected error processing data")
            return None

    async def search_player(self, query: str) -> dict[str, Any] | None:
        """Search player by ID or nickname."""
        if not query:
            return None

        query = query.strip()

        # If query is numeric, try ID first
        if query.isdigit():
            player = await self.fetch_player_by_id(query)
            if player:
                return player

        # Try as nickname
        return await self.fetch_player_by_nickname(query)

    async def fetch_events(self, season: int = -1) -> dict[str, Any] | None:
        """Fetch events for a specific season.

        Args:
            season: Season number (-1 for latest season, 1 for first season)

        Returns:
            Events data or None on error
        """
        host = self._make_punycode_host(self.host)
        url = f"https://{host}/api/events?season={season}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                return r.json()
        except Exception:
            logger.exception("mb_api: failed to fetch events for season %s", season)
            return None

    async def fetch_top_players(self, limit: int = 5, offset: int = 0) -> dict[str, Any] | None:
        """Fetch top players with pagination.

        Args:
            limit: Number of players to fetch
            offset: Offset for pagination

        Returns:
            Top players data or None on error
        """
        host = self._make_punycode_host(self.host)
        url = f"https://{host}/api/users?limit={limit}&offset={offset}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                return r.json()
        except Exception:
            logger.exception(
                "mb_api: failed to fetch top players (limit=%s, offset=%s)", limit, offset
            )
            return None
