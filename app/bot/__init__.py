from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import get_main_router
from app.bot.middlewares import UserMiddleware, RateLimitMiddleware
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Global middlewares (applied to all updates)
    dp.update.outer_middleware(RateLimitMiddleware())
    dp.update.outer_middleware(UserMiddleware())

    # Register all routers
    dp.include_router(get_main_router())

    return dp
