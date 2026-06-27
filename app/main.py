from __future__ import annotations

import asyncio
import json
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

WEBAPP_DIR = pathlib.Path(__file__).parent / "webapp"
PLAYER_HTML = WEBAPP_DIR / "player.html"


# ── WebApp route ──────────────────────────────────────────────

async def handle_player(request: web.Request) -> web.Response:
    """Telegram Mini App video player səhifəsi."""
    try:
        content = PLAYER_HTML.read_text(encoding="utf-8")
        return web.Response(
            text=content,
            content_type="text/html",
            charset="utf-8",
            headers={
                "X-Frame-Options": "ALLOWALL",
                "Content-Security-Policy": "frame-ancestors *",
            },
        )
    except FileNotFoundError:
        return web.Response(text="Player not found", status=404)



async def handle_playwright_status(request: web.Request) -> web.Response:
    """Playwright quraşdırılıb-quraşdırılmadığını yoxla."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
            await browser.close()
        return web.json_response({"status": "ok", "playwright": "ready"})
    except ImportError:
        return web.json_response({"status": "error", "playwright": "not installed"}, status=500)
    except Exception as exc:
        return web.json_response({"status": "error", "detail": str(exc)}, status=500)

async def handle_resolve(request: web.Request) -> web.Response:
    """
    Canlı resolve endpoint.

    Player hər izləmədə bu endpoint-i çağırır:
      GET /resolve?page=<url>

    Cavab:
      {
        "sources": [
          {"video": "...m3u8", "audio": "...m3u8", "quality": "1080p"},
          {"video": "...m3u8", "quality": "720p"}
        ]
      }

    audio sahəsi yalnız video və audio ayrı m3u8-dirsə olur.
    """
    page_url = request.query.get("page", "").strip()
    if not page_url or not page_url.startswith("http"):
        return web.json_response({"error": "invalid page url"}, status=400)

    from app.services.scraper.sinekfilmizle import SinekfilmizleScraper

    sources = await SinekfilmizleScraper.resolve_live(page_url)

    if not sources:
        return web.json_response({"error": "no sources found"}, status=502)

    result = []
    for src in sources:
        entry: dict = {"video": src.video_url, "quality": src.quality}
        if src.audio_url:
            entry["audio"] = src.audio_url
        result.append(entry)

    return web.json_response(
        {"sources": result},
        headers={"Cache-Control": "no-store"},
    )


# ── Lifecycle ─────────────────────────────────────────────────

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
            app = web.Application()
            app.router.add_get("/player", handle_player)
            app.router.add_get("/resolve", handle_resolve)
            app.router.add_get("/playwright-status", handle_playwright_status)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", settings.port)
            await site.start()
            logger.info("WebApp player hazırdır", port=settings.port, path="/player")
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

    app.router.add_get("/player", handle_player)
    app.router.add_get("/resolve", handle_resolve)
    app.router.add_get("/playwright-status", handle_playwright_status)

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=settings.port)


def main() -> None:
    setup_logging()
    bot = create_bot()
    dp = create_dispatcher()

    if settings.use_webhook:
        logger.info("Webhook mode başladılır", port=settings.port)
        run_webhook(bot, dp)
    else:
        logger.info("Polling mode başladılır")
        run_polling(bot, dp)


if __name__ == "__main__":
    main()
