"""News API client."""

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class NewsAPI:
    """Client for News API."""

    def __init__(self, host: str = "news.m-br.ru", cache_ttl: float = 60.0):
        self.host = host
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[float, Optional[List[Dict[str, Any]]]]] = {}

    def _get_cache(self, key: str) -> Optional[List[Dict[str, Any]]]:
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

    def _set_cache(self, key: str, val: Optional[List[Dict[str, Any]]]) -> None:
        """Store API response in cache with current timestamp."""
        self._cache[key] = (time.time(), val)

    async def fetch_news(
        self, limit: int = 5, offset: int = 0, use_cache: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """Fetch news from News API.

        Args:
            limit: Number of news items to fetch (max 5)
            offset: Offset for pagination
            use_cache: Whether to use cached results

        Returns:
            List of news items or None on error
        """
        # Enforce maximum limit of 5
        limit = min(limit, 5)

        cache_key = f"news:{limit}:{offset}"
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached

        url = f"https://{self.host}"
        params = {"limit": limit, "offset": offset}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                try:
                    news_data = r.json()

                    # Cache the result
                    if use_cache:
                        self._set_cache(cache_key, news_data)

                    return news_data
                except Exception:
                    logger.exception("news_api: failed to parse JSON")
                    return None
        except httpx.HTTPStatusError as e:
            status = getattr(e.response, "status_code", None)
            body = (getattr(e.response, "text", "") or "")[:500]
            logger.warning("news_api: HTTP error %s: %s", status, body)
            return None
        except Exception as e:
            logger.exception("news_api: network error: %s", e)
            return None
