from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import settings
from app.database.supabase import close_client
from app.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


async def on_startup(bot: Bot) -> None:
    if settings.use_webhook:
        webhook_url = f"{settings.webhook_url}{settings.webhook_path}"
        await bot.set_webhook(webhook_url)
        logger.info("Webhook set", url=webhook_url)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Running in long-polling mode")

    bot_info = await bot.get_me()
    logger.info("Bot started", username=bot_info.username)


async def on_shutdown(bot: Bot) -> None:
    await close_client()
    if settings.use_webhook:
        await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot shut down cleanly")


def run_polling(bot: Bot, dp: Dispatcher) -> None:
    async def _run() -> None:
        await on_startup(bot)
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            await on_shutdown(bot)

    asyncio.run(_run())


def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    app = web.Application()

    dp.startup.register(lambda: on_startup(bot))
    dp.shutdown.register(lambda: on_shutdown(bot))

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=settings.port)


def main() -> None:
    setup_logging()
    bot = create_bot()
    dp = create_dispatcher()

    if settings.use_webhook:
        logger.info("Starting in webhook mode", port=settings.port)
        run_webhook(bot, dp)
    else:
        logger.info("Starting in polling mode")
        run_polling(bot, dp)


if __name__ == "__main__":
    main()
