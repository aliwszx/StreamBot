from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TGUser

from app.database import queries
from app.utils.logging import get_logger

logger = get_logger(__name__)


class UserMiddleware(BaseMiddleware):
    """Attach the DB User to handler data as ``data["db_user"]``."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TGUser | None = data.get("event_from_user")
        if tg_user and not tg_user.is_bot:
            try:
                db_user = await queries.get_or_create_user(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                )
                data["db_user"] = db_user
            except Exception as exc:
                logger.error("UserMiddleware error", error=str(exc))
                data["db_user"] = None
        else:
            data["db_user"] = None
        return await handler(event, data)
