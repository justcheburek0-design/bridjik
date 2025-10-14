# mb_api.py
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any
from urllib.parse import quote_plus
import time
import config
import json

# простое в памяти кэширование: key -> (ts, value)
_MB_CACHE: Dict[str, tuple[float, Optional[Dict[str, Any]]]] = {}
_MB_CACHE_TTL = 20.0  # seconds, настраиваемо

# параметры повторов/таймаутов (подобно mc.py)
_HTTP_TIMEOUT = 10.0

logger = logging.getLogger(__name__)


def _make_punycode_host(host: str) -> str:
    """RU: Преобразует домен с не-ASCII в punycode для HTTP-запросов."""
    try:
        return host.encode("idna").decode("ascii")
    except Exception:
        return host


async def _fetch_json_from_api(id: str | None) -> Optional[Dict[str, Any]]:
    """RU: Запрашивает у MineBridge API данные по нику и возвращает JSON."""
    if not id:
        return None
    
    host = _make_punycode_host(config.MB_HOST)
    
    id_esc = quote_plus(id, safe="")  # RU: гарантируем URL-безопасность id
    url = f"https://{host}/api/tg/{id_esc}"

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            try:
                return r.json()
            except Exception:
                # RU: JSON может быть некорректным — логируем и возвращаем None
                logger.exception("mb_api: failed to parse JSON for nick %s", id)
                return None
    except httpx.HTTPStatusError as e:
        status = getattr(e.response, "status_code", None)
        body = (getattr(e.response, "text", "") or "")[:500]
        logger.warning("mb_api: HTTP error %s for %s: %s", status, id, body)
        return None
    except Exception as e:
        logger.exception("mb_api: network error for %s: %s", id, e)
        return None

def _get_cache(key: str) -> Optional[Dict[str, Any]]:
    """RU: Возвращает значение из кэша, если оно ещё не истекло."""
    row = _MB_CACHE.get(key)
    if not row:
        return None
    ts, val = row
    if time.time() - ts > _MB_CACHE_TTL:
        try:
            del _MB_CACHE[key]
        except KeyError:
            pass
        return None
    return val


def _set_cache(key: str, val: Optional[Dict[str, Any]]) -> None:
    """RU: Кладёт снимок ответа API в кэш с текущим временем."""
    _MB_CACHE[key] = (time.time(), val)


async def fetch_player_by_id(id: str | None, use_cache: bool = True) -> Optional[str]:
    """
    Основная функция: принимает ник (строку), возвращает JSON-строку с информацией или None.
    use_cache=True включает кратковременный кэш.
    """
    if not id:
        return None
    key = f"mb:{id}"
    if use_cache:
        player = _get_cache(key)
        if player is not None:
            # cached — dict или None; сериализуем как строку перед возвратом
            try:
                return player
            except Exception:
                # если по какой-то причине сериализация упала, просто вернём None
                logger.exception("mb_api: failed to json.dumps cached value for %s", id)
                return None

    player_data = await _fetch_json_from_api(id)

    if player_data is None:
        return None

    URLS_START = {
        "vk": { "url": 'https://vk.com/', "label": 'ВК' },
        "twitch": { "url": 'https://www.twitch.tv/', "label": 'Твич' },
        "youtube": { "url": 'https://youtube.com/@', "label": 'Ютуб' },
        "donationAlerts": { "url": 'https://donationalerts.com/r/', "label": 'Донат' }
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
        
        if player_data["discordId"]:
            player["Дискорд"] = f"https://discord.com/users/{player_data['discordId']}"

        for key, val in player_data.get("urls", {}).items():
            if key in URLS_START and val:
                if player_data["urls"][key]:
                    player[URLS_START[key]["label"]] = f"{URLS_START[key]['url']}{val}"
                
        if use_cache:
            _set_cache(key, player)
        
        return player
        
    except Exception:
        logger.exception("mb_api: unexpected error processing data for %s", id)
        return None