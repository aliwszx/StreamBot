from __future__ import annotations

from functools import lru_cache

from supabase import AsyncClient, acreate_client

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    """Return (and lazily create) the shared AsyncClient."""
    global _client
    if _client is None:
        _client = await acreate_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase async client initialised")
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        # supabase-py AsyncClient does not expose an explicit close,
        # but we reset the reference so the next call re-creates it.
        _client = None
        logger.info("Supabase client reference cleared")
