from __future__ import annotations

import asyncio
import logging
import pathlib

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import settings
from app.database.supabase import close_client
from app.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)

# Path to the WebApp HTML file
WEBAPP_DIR = pathlib.Path(__file__).parent / "webapp"
PLAYER_HTML = WEBAPP_DIR / "player.html"


# ── WebApp route ──────────────────────────────────────────────
async def handle_player(request: web.Request) -> web.Response:
    """Serve the Telegram Mini App video player page."""
    try:
        content = PLAYER_HTML.read_text(encoding="utf-8")
        return web.Response(
            text=content,
            content_type="text/html",
            charset="utf-8",
            headers={
                # Required for Telegram WebApp to be allowed inside the in-app browser
                "X-Frame-Options": "ALLOWALL",
                "Content-Security-Policy": "frame-ancestors *",
            },
        )
    except FileNotFoundError:
        return web.Response(text="Player not found", status=404)


async def on_startup(bot: Bot) -> None:
    if settings.use_webhook:
        webhook_url = f"{settings.webhook_url}{settings.webhook_path}"
        await bot.set_webhook(
            webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"],
        )
        info = await bot.get_webhook_info()
        logger.info("Webhook set", url=info.url, pending=info.pending_update_count)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Running in long-polling mode")

    bot_info = await bot.get_me()
    logger.info("Bot started", username=bot_info.username)


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutting down...")
    await close_client()
    if settings.use_webhook:
        await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot shut down cleanly")


def run_polling(bot: Bot, dp: Dispatcher) -> None:
    async def _run() -> None:
        await on_startup(bot)
        try:
            # Run a minimal web server alongside polling so /player is reachable
            app = web.Application()
            app.router.add_get("/player", handle_player)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", settings.port)
            await site.start()
            logger.info("WebApp player available", port=settings.port, path="/player")

            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            await on_shutdown(bot)

    asyncio.run(_run())


def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    app = web.Application()

    async def _startup(app: web.Application) -> None:
        await on_startup(bot)

    async def _shutdown(app: web.Application) -> None:
        await on_shutdown(bot)

    app.on_startup.append(_startup)
    app.on_shutdown.append(_shutdown)

    # ── Telegram Mini App player page ──
    app.router.add_get("/player", handle_player)

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
