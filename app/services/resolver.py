"""
Live m3u8 resolver for sinekfilmizle.com + p2turk.xyz

İki strategiya:
  1. source_url sinekfilmizle.com-dusa — saytı açıb p2turk embed URL tapır,
     oradan da master.m3u8 qurur (session + Referer ilə)
  2. source_url artıq p2turk embed URL-idisə (https://p.2turk.xyz/...) —
     birbaşa resolve edir
  3. source_url video_id formatındadırsa (p2turk:Bno1xDl) —
     fresh timestamp ilə m3u8 URL qurur

Heç bir scraping DB-yə saxlanmır — hər izləmədə aktual link verilir.
"""
from __future__ import annotations

import re
import json
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Browser-kimi header-lər — Cloudflare bot filterindən keçmək üçün
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "DNT": "1",
}

KNOWN_PLAYER_HOSTS = [
    "p2turk", "vidmoly", "filemoon", "doodstream",
    "streamtape", "voe.sx", "upstream", "vudeo",
    "player", "embed", "play", "stream",
    "mcloud", "rabbitstream", "mycloud",
]

PLAYER_JS_PATTERNS = [
    r"requests\.js", r"player\.js", r"video\.js",
    r"stream\.js", r"source\.js",
]

P2TURK_HOST = "p.2turk.xyz"


@dataclass
class ResolvedStream:
    url: str           # m3u8 URL
    audio_url: Optional[str] = None
    quality: str = "HD"


# ── Public API ────────────────────────────────────────────────

async def resolve(source_url: str) -> List[ResolvedStream]:
    """
    Verilmiş source_url-dən canlı m3u8 tapır.

    source_url ola bilər:
      - https://sinekfilmizle.com/film-adi-izle/   → saytı açıb embed tapır
      - https://p.2turk.xyz/...                     → birbaşa p2turk resolve
      - p2turk:VIDEO_ID                             → sadəcə fresh timestamp ilə URL qurur
    """
    if source_url.startswith("p2turk:"):
        video_id = source_url.split(":", 1)[1].strip()
        return _build_p2turk_urls(video_id)

    if P2TURK_HOST in source_url:
        return await _resolve_p2turk_embed(source_url)

    # sinekfilmizle.com (və ya başqa sayt)
    return await _resolve_site(source_url)


# ── sinekfilmizle.com ─────────────────────────────────────────

async def _resolve_site(page_url: str) -> List[ResolvedStream]:
    """Sayt HTML-ini oxuyub embed/m3u8 tapır."""
    base = _base_url(page_url)

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # İlk öncə saytın ana səhifəsinə gir (cookie + CF clearance üçün)
        try:
            async with session.get(base, timeout=aiohttp.ClientTimeout(total=10)) as _:
                pass
        except Exception:
            pass

        html = await _fetch(session, page_url)
        if not html:
            logger.warning("Səhifə yüklənmədi", url=page_url)
            return []

        # 1. Birbaşa HTML-dən m3u8 axtar
        direct = _find_m3u8(html)
        if direct:
            logger.info("HTML-də m3u8 tapıldı", count=len(direct))
            return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in direct]

        # 2. Saytın öz JS player fayllarını yoxla
        js_streams = await _resolve_player_js(session, html, base)
        if js_streams:
            return js_streams

        # 3. iframe/embed URL-lərini tap
        embed_urls = _find_embed_urls(html, base)
        logger.debug("Embed URL-lər tapıldı", count=len(embed_urls), urls=embed_urls)

        for embed_url in embed_urls:
            streams = await _resolve_embed(session, embed_url)
            if streams:
                return streams

    logger.warning("Heç bir stream tapılmadı", url=page_url)
    return []


async def _resolve_player_js(
    session: aiohttp.ClientSession, page_html: str, base_url: str
) -> List[ResolvedStream]:
    """Saytın player JS fayllarında m3u8 və ya embed URL axtar."""
    soup = BeautifulSoup(page_html, "lxml")
    js_urls: List[str] = []

    for script in soup.find_all("script", src=True):
        src = script.get("src", "")
        if not src:
            continue
        src = _abs_url(src, base_url)
        for pattern in PLAYER_JS_PATTERNS:
            if re.search(pattern, src, re.I):
                js_urls.append(src)
                break

    # Inline script-lərdə JS URL axtar
    for script in soup.find_all("script"):
        text = script.get_text()
        for m in re.finditer(r'''['"]((?:https?:)?//[^'"]+\.js[^'"]*)['"]''', text):
            url = _abs_url(m.group(1), base_url)
            for pattern in PLAYER_JS_PATTERNS:
                if re.search(pattern, url, re.I) and url not in js_urls:
                    js_urls.append(url)
                    break

    for js_url in js_urls[:5]:
        js_content = await _fetch(session, js_url)
        if not js_content:
            continue
        # m3u8 axtar
        urls = _find_m3u8(js_content)
        if urls:
            logger.info("JS faylında m3u8 tapıldı", js=js_url)
            return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in urls]
        # embed URL-ləri axtar
        embeds = _find_embed_urls(js_content, base_url)
        for embed_url in embeds[:3]:
            async with aiohttp.ClientSession(headers=HEADERS) as s2:
                streams = await _resolve_embed(s2, embed_url)
                if streams:
                    return streams

    return []


# ── p2turk.xyz ───────────────────────────────────────────────

async def _resolve_p2turk_embed(embed_url: str) -> List[ResolvedStream]:
    """p2turk embed səhifəsindən video ID-ni çıxarıb m3u8 URL qurur."""

    # URL formatı: https://p.2turk.xyz/videos/Bno1xDl/  ya da
    #              https://p.2turk.xyz/embed/Bno1xDl
    video_id = _extract_p2turk_id(embed_url)
    if video_id:
        logger.info("p2turk video ID tapıldı (URL-dən)", video_id=video_id)
        return _build_p2turk_urls(video_id)

    # ID URL-dən tapılmadısa, HTML-i oxu
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html = await _fetch(session, embed_url)
        if not html:
            return []

        # HTML-dən m3u8 axtar
        urls = _find_m3u8(html)
        if urls:
            return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in urls]

        # HTML-dən video ID axtar
        video_id = _extract_p2turk_id_from_html(html)
        if video_id:
            return _build_p2turk_urls(video_id)

        # JS fayllarını yoxla
        js_streams = await _resolve_player_js(session, html, f"https://{P2TURK_HOST}")
        if js_streams:
            return js_streams

    logger.warning("p2turk: m3u8 tapılmadı", url=embed_url)
    return []


def _extract_p2turk_id(url: str) -> Optional[str]:
    """URL-dən p2turk video ID çıxarır. Nümunə: Bno1xDl"""
    m = re.search(r'/videos/([A-Za-z0-9_-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/embed/([A-Za-z0-9_-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'[?&]id=([A-Za-z0-9_-]+)', url)
    if m:
        return m.group(1)
    return None


def _extract_p2turk_id_from_html(html: str) -> Optional[str]:
    """HTML içindən p2turk video ID axtar."""
    patterns = [
        r'["\'](?:videoId|video_id|id)["\']:\s*["\']([A-Za-z0-9_-]{5,12})["\']',
        r'/videos/([A-Za-z0-9_-]{5,12})/master\.m3u8',
        r'file["\']?\s*[:=]\s*["\']https?://[^"\']*?/([A-Za-z0-9_-]{5,12})/master\.m3u8',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1)
    return None


def _build_p2turk_urls(video_id: str) -> List[ResolvedStream]:
    """
    p2turk video ID-dən fresh timestamp ilə m3u8 URL qurur.
    ?v= parametri hər zaman current unix timestamp olur.
    """
    ts = int(time.time())
    master = f"https://p.2turk.xyz/videos/{video_id}/master.m3u8?v={ts}"
    logger.info("p2turk m3u8 URL quruldu", video_id=video_id, url=master)
    return [ResolvedStream(url=master, quality="HD")]


# ── Generic embed resolver ────────────────────────────────────

async def _resolve_embed(
    session: aiohttp.ClientSession, embed_url: str, depth: int = 0
) -> List[ResolvedStream]:
    if depth > 3:
        return []

    if P2TURK_HOST in embed_url:
        return await _resolve_p2turk_embed(embed_url)

    html = await _fetch(session, embed_url)
    if not html:
        return []

    urls = _find_m3u8(html)
    if urls:
        return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in urls]

    nested = _find_embed_urls(html, _base_url(embed_url))
    for nested_url in nested[:3]:
        if nested_url != embed_url:
            streams = await _resolve_embed(session, nested_url, depth + 1)
            if streams:
                return streams

    return []


# ── HTML parsing helpers ──────────────────────────────────────

def _find_m3u8(text: str) -> List[str]:
    patterns = [
        r'''(?:file|src|source|url)\s*[:=]\s*['\"](https?://[^'\"]+\.m3u8[^'\"]*)['\"]\s*''',
        r'''['\"](https?://[^'\"]+\.m3u8[^'\"]*)['\"]\s*''',
    ]
    found: set = set()
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            found.add(m.group(1).strip())
    return list(found)


def _find_embed_urls(html: str, base_url: str = "") -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = []

    for tag in soup.find_all(["iframe", "frame"]):
        src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src") or ""
        if src:
            urls.append(_abs_url(src, base_url))

    for script in soup.find_all("script"):
        text = script.get_text()
        for m in re.finditer(r'''['\"](https?://\S+?)['\"]\s*''', text):
            c = m.group(1)
            if any(h in c for h in KNOWN_PLAYER_HOSTS):
                urls.append(c)

    for tag in soup.find_all(True):
        for attr in ["data-src", "data-url", "data-video", "data-embed"]:
            val = tag.get(attr, "")
            if val.startswith("http") and any(h in val for h in KNOWN_PLAYER_HOSTS):
                urls.append(val)

    seen: set = set()
    return [u for u in urls if u not in seen and not seen.add(u)]  # type: ignore


# ── Utilities ─────────────────────────────────────────────────

async def _fetch(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
        ) as resp:
            if resp.status == 403:
                logger.warning("403 Forbidden (bot/CF bloklama)", url=url)
                return None
            resp.raise_for_status()
            return await resp.text(errors="replace")
    except Exception as exc:
        logger.error("Fetch failed", url=url, error=str(exc))
        return None


def _detect_quality(url: str) -> str:
    m = re.search(r'(\d{3,4})[pP]', url)
    if m:
        return f"{m.group(1)}p"
    if "1080" in url:
        return "1080p"
    if "720" in url:
        return "720p"
    if "480" in url:
        return "480p"
    return "HD"


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _abs_url(url: str, base: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/") and base:
        return base.rstrip("/") + url
    if url.startswith("http"):
        return url
    return url
