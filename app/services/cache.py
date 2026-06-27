from __future__ import annotations

from typing import Any, Optional

from cachetools import TTLCache

from app.config import settings

_cache: TTLCache = TTLCache(maxsize=512, ttl=settings.cache_ttl)


def cache_get(key: str) -> Optional[Any]:
    return _cache.get(key)


def cache_set(key: str, value: Any) -> None:
    _cache[key] = value


def cache_delete(key: str) -> None:
    _cache.pop(key, None)


def cache_clear() -> None:
    _cache.clear()
