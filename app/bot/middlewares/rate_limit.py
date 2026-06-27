from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Simple in-process sliding-window rate limiter
# 30 requests per 60 seconds per user
_WINDOW = 60       # seconds
_MAX_REQUESTS = 30

_user_requests: Dict[int, list] = defaultdict(list)


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        from aiogram.types import User as TGUser

        tg_user: TGUser | None = data.get("event_from_user")
        if tg_user and not tg_user.is_bot:
            uid = tg_user.id
            now = time.monotonic()
            window_start = now - _WINDOW
            _user_requests[uid] = [t for t in _user_requests[uid] if t > window_start]
            if len(_user_requests[uid]) >= _MAX_REQUESTS:
                logger.warning("Rate limit hit", user_id=uid)
                if isinstance(event, Message):
                    await event.answer("⏳ Too many requests. Please slow down.")
                return
            _user_requests[uid].append(now)
        return await handler(event, data)
