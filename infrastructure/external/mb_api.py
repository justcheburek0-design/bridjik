"""MineBridge API client."""
import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import quote_plus
import httpx


logger = logging.getLogger(__name__)


class MineBridgeAPI:
    """Client for MineBridge API."""
    
    def __init__(self, host: str, cache_ttl: float = 20.0):
        self.host = host
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[float, Optional[Dict[str, Any]]]] = {}
    
    def _make_punycode_host(self, host: str) -> str:
        """Convert domain with non-ASCII to punycode for HTTP requests."""
        try:
            return host.encode("idna").decode("ascii")
        except Exception:
            return host
    
    def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
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
    
    def _set_cache(self, key: str, val: Optional[Dict[str, Any]]) -> None:
        """Store API response in cache with current timestamp."""
        self._cache[key] = (time.time(), val)
    
    async def _fetch_json_from_api(self, player_id: str) -> Optional[Dict[str, Any]]:
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
    
    async def fetch_player_by_id(self, player_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
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
        
        URLS_START = {
            "vk": {"url": 'https://vk.com/', "label": 'ВК'},
            "twitch": {"url": 'https://www.twitch.tv/', "label": 'Твич'},
            "youtube": {"url": 'https://youtube.com/@', "label": 'Ютуб'},
            "donationAlerts": {"url": 'https://donationalerts.com/r/', "label": 'Донат'}
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
                "Роли": player_data.get("roles") or []
            }
            
            if player_data.get("discordId"):
                player["Дискорд"] = f"https://discord.com/users/{player_data['discordId']}"
            
            for key, val in player_data.get("urls", {}).items():
                if key in URLS_START and val:
                    player[URLS_START[key]["label"]] = f"{URLS_START[key]['url']}{val}"
            
            if use_cache:
                self._set_cache(key, player)
            
            return player
        except Exception:
            logger.exception("mb_api: unexpected error processing data for %s", player_id)
            return None

