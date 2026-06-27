from __future__ import annotations

import asyncio
import pathlib
from urllib.parse import unquote

import aiohttp
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

# Proxy üçün icazəli host-lar (təhlükəsizlik üçün whitelist)
PROXY_ALLOWED_HOSTS = {
    "p.2turk.xyz",
    "2turk.xyz",
}

PROXY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://p.2turk.xyz/",
    "Origin": "https://p.2turk.xyz",
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Range, Content-Type",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range",
}


async def handle_hls_proxy(request: web.Request) -> web.Response:
    """
    HLS stream proxy — CORS problemini həll edir.

    GET /hls-proxy?url=<encoded_m3u8_url>

    p.2turk.xyz CORS header-i göndərmir, buna görə Telegram Mini App
    birbaşa yükləyə bilmir. Bu endpoint stream-i serverimiz üzərindən
    keçirir və CORS header-ləri özümüz əlavə edirik.

    m3u8 faylları içindəki nisbi URL-ləri də proxy URL-ə çeviririk.
    """
    # OPTIONS preflight
    if request.method == "OPTIONS":
        return web.Response(headers=CORS_HEADERS, status=204)

    raw_url = request.query.get("url", "").strip()
    if not raw_url or not raw_url.startswith("http"):
        return web.Response(text="Missing url param", status=400, headers=CORS_HEADERS)

    # Whitelist yoxlanması
    from urllib.parse import urlparse
    parsed = urlparse(raw_url)
    if parsed.hostname not in PROXY_ALLOWED_HOSTS:
        return web.Response(
            text=f"Host not allowed: {parsed.hostname}",
            status=403,
            headers=CORS_HEADERS,
        )

    base_url = (settings.webapp_base_url or str(request.url.origin())).rstrip("/")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                raw_url,
                headers=PROXY_HEADERS,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
            ) as upstream:
                content_type = upstream.headers.get("Content-Type", "application/octet-stream")
                body = await upstream.read()

                if upstream.status != 200:
                    return web.Response(
                        text=f"Upstream error: {upstream.status}",
                        status=upstream.status,
                        headers=CORS_HEADERS,
                    )

                # m3u8 fayllarındakı nisbi URL-ləri proxy URL-ə çevir
                if "mpegurl" in content_type or raw_url.endswith(".m3u8"):
                    text = body.decode("utf-8", errors="replace")
                    from urllib.parse import urljoin, quote
                    import re

                    # #EXT-X-MEDIA, #EXT-X-KEY, #EXT-X-MAP, #EXT-X-I-FRAME-STREAM-INF
                    # kimi tag-ların daxilindəki URI="..." atributu da nisbi ola bilər.
                    # Əvvəlki versiya yalnız "#" ilə başlamayan sətirləri (variant/segment
                    # URL-ləri) rewrite edirdi, tag-lar isə "#" ilə başladığı üçün ötürülürdü.
                    # Nəticədə məsələn audio track-in URI-si proxy-ə yönləndirilmirdi və
                    # brauzer onu birbaşa öz domenimizdən (server root-dan) çağırıb 404
                    # alırdı (sonsuz təkrarlanan /playlist_xxxxx.m3u8 404-ləri buradan idi).
                    uri_attr_re = re.compile(r'URI="([^"]+)"')

                    def _rewrite_uri_attr(match: "re.Match[str]") -> str:
                        abs_u = urljoin(raw_url, match.group(1))
                        return f'URI="{base_url}/hls-proxy?url={quote(abs_u, safe="")}"'

                    lines = []
                    for line in text.splitlines():
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            # URL-dir — proxy-dən keçir
                            abs_url = urljoin(raw_url, stripped)
                            proxied = f"{base_url}/hls-proxy?url={quote(abs_url, safe='')}"
                            lines.append(proxied)
                        elif stripped.startswith("#") and 'URI="' in stripped:
                            # tag daxilindəki URI="..." atributunu da proxy-ə çeviririk
                            lines.append(uri_attr_re.sub(_rewrite_uri_attr, line))
                        else:
                            lines.append(line)
                    body = "\n".join(lines).encode("utf-8")
                    content_type = "application/vnd.apple.mpegurl"

                headers = {**CORS_HEADERS, "Content-Type": content_type}
                return web.Response(body=body, headers=headers)

    except asyncio.TimeoutError:
        return web.Response(text="Upstream timeout", status=504, headers=CORS_HEADERS)
    except Exception as e:
        logger.error("HLS proxy xəta", url=raw_url, error=str(e))
        return web.Response(text=f"Proxy error: {e}", status=502, headers=CORS_HEADERS)


# ── WebApp routes ─────────────────────────────────────────────

async def handle_player(request: web.Request) -> web.Response:
    """Telegram Mini App video player səhifəsi."""
    try:
        content = PLAYER_HTML.read_text(encoding="utf-8")
        # settings.webapp_base_url istifadə edirik — Render reverse proxy arxasında
        # request.url.origin() http://0.0.0.0:8000 qaytarır, bu yanlışdır.
        base_url = (settings.webapp_base_url or str(request.url.origin())).rstrip("/")
        content = content.replace(
            "const BASE_URL = '';",
            f"const BASE_URL = '{base_url}';"
        )
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


async def handle_resolve(request: web.Request) -> web.Response:
    """
    Canlı m3u8 resolve endpoint.

    Player hər izləmədə bu endpoint-i çağırır:
      GET /resolve?page=<sinekfilmizle_url>

    Cavab:
      {"sources": [{"video": "...m3u8", "quality": "HD"}, ...]}
    """
    page_url = request.query.get("page", "").strip()
    if not page_url or not page_url.startswith("http"):
        return web.json_response({"error": "invalid page url"}, status=400)

    from app.services.resolver import resolve

    logger.info("Resolve başladı", url=page_url)
    streams = await resolve(page_url)
    logger.info("Resolve tamamlandı", url=page_url, count=len(streams))

    if not streams:
        return web.json_response({"error": "no sources found"}, status=502)

    result = [{"video": s.url, "quality": s.quality} for s in streams]
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
            app.router.add_get("/hls-proxy", handle_hls_proxy)
            app.router.add_route("OPTIONS", "/hls-proxy", handle_hls_proxy)
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
    app.router.add_get("/hls-proxy", handle_hls_proxy)
    app.router.add_route("OPTIONS", "/hls-proxy", handle_hls_proxy)

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
