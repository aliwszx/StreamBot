"""
Live m3u8 resolver for sinekfilmizle.com.

İstifadəçi filmi izləmək istədikdə bu modul çağırılır.
Saytdan cari/aktual m3u8 linkini tapıb qaytarır.
Heç bir scraping və ya DB saxlama yoxdur — hər dəfə canlı tapılır.
"""
from __future__ import annotations

import re
import json
import asyncio
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from app.utils.logging import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
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


@dataclass
class ResolvedStream:
    url: str           # m3u8 URL
    audio_url: Optional[str] = None
    quality: str = "HD"


async def _fetch(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            return await resp.text(errors="replace")
    except Exception as exc:
        logger.error("Fetch failed", url=url, error=str(exc))
        return None


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
        if src.startswith("http"):
            urls.append(src)
        elif src.startswith("//"):
            urls.append("https:" + src)
        elif src.startswith("/") and base_url:
            urls.append(base_url.rstrip("/") + src)

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
    return [u for u in urls if u not in seen and not seen.add(u)]  # type: ignore[func-returns-value]


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


async def _resolve_p2turk(session: aiohttp.ClientSession, embed_url: str) -> List[ResolvedStream]:
    """p2turk.xyz player-dən canlı m3u8 tapır."""
    html = await _fetch(session, embed_url)
    if not html:
        return []

    urls = _find_m3u8(html)
    if urls:
        logger.info("p2turk: m3u8 tapıldı", count=len(urls))
        return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in urls]

    # p2turk-un öz JS fayllarını yoxla
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", src=True):
        src = script.get("src", "")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        for pattern in PLAYER_JS_PATTERNS:
            if re.search(pattern, src, re.I):
                js_html = await _fetch(session, src)
                if js_html:
                    js_urls = _find_m3u8(js_html)
                    if js_urls:
                        return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in js_urls]
                break

    logger.warning("p2turk: m3u8 tapılmadı", url=embed_url)
    return []


async def _resolve_embed(
    session: aiohttp.ClientSession, embed_url: str, depth: int = 0
) -> List[ResolvedStream]:
    if depth > 3:
        return []

    if "p2turk" in embed_url:
        return await _resolve_p2turk(session, embed_url)

    html = await _fetch(session, embed_url)
    if not html:
        return []

    urls = _find_m3u8(html)
    if urls:
        return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in urls]

    nested = _find_embed_urls(html)
    for nested_url in nested[:3]:
        if nested_url != embed_url:
            streams = await _resolve_embed(session, nested_url, depth + 1)
            if streams:
                return streams

    return []


async def resolve(page_url: str) -> List[ResolvedStream]:
    """
    sinekfilmizle.com film/serial səhifəsindən canlı m3u8 tapır.
    
    Arxiv/DB-yə yazmır. Hər çağırışda aktual link verir.
    """
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        html = await _fetch(session, page_url)
        if not html:
            logger.warning("Səhifə yüklənmədi", url=page_url)
            return []

        # 1. Birbaşa HTML-də m3u8 axtar
        direct = _find_m3u8(html)
        if direct:
            logger.info("HTML-də m3u8 tapıldı", count=len(direct))
            return [ResolvedStream(url=u, quality=_detect_quality(u)) for u in direct]

        # 2. iframe/embed URL-lərini tap
        embed_urls = _find_embed_urls(html, base_url="https://sinekfilmizle.com")
        logger.debug("Embed URL-lər tapıldı", count=len(embed_urls))

        for embed_url in embed_urls:
            streams = await _resolve_embed(session, embed_url)
            if streams:
                return streams

    logger.warning("Heç bir stream tapılmadı", url=page_url)
    return []
