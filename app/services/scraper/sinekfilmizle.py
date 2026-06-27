from __future__ import annotations

import re
import json
import asyncio
from typing import List, Optional, Dict
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.services.scraper.base import BaseScraper, ScrapedStream
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StreamSource:
    """Video + audio m3u8 cütü (və ya tək unified m3u8)."""
    video_url: str
    audio_url: Optional[str] = None
    quality: str = "HD"

    def is_dual(self) -> bool:
        return bool(self.audio_url and self.audio_url != self.video_url)


class SinekfilmizleScraper(BaseScraper):
    """
    sinekfilmizle.com üçün scraper.

    Strategiya (sıra ilə):
      1. aiohttp ilə əsas səhifəni çək → JS fayllarında m3u8 axtar
      2. iframe/embed URL-lərini tap → hər birini resolve et
      3. p2turk.xyz üçün xüsusi handler
      4. Playwright mövcuddursa son çarə kimi istifadə et
         (Render-də işləməyə bilər, ona görə son sıradadır)
    """

    name = "sinekfilmizle"
    base_url = "https://sinekfilmizle.com"

    KNOWN_PLAYER_HOSTS = [
        "vidmoly", "filemoon", "doodstream", "mixdrop",
        "streamtape", "voe.sx", "upstream", "vudeo",
        "player", "embed", "play", "stream", "p2turk",
        "mcloud", "rabbitstream", "mycloud",
    ]

    # sinekfilmizle.com-un öz JS player faylları
    PLAYER_JS_PATTERNS = [
        r"requests\.js",
        r"player\.js",
        r"video\.js",
        r"stream\.js",
        r"source\.js",
    ]

    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.page_url = page_url

    # ─────────────────────────────────────────────────────────────
    # Public interface
    # ─────────────────────────────────────────────────────────────

    async def scrape(self) -> List[ScrapedStream]:
        meta = await self._extract_meta()
        if not meta:
            return []

        sources = await self.resolve_live(self.page_url)
        if not sources:
            logger.warning("No sources found", url=self.page_url)
            return []

        streams: List[ScrapedStream] = []
        for src in sources:
            stored_url = self._encode_source(src)
            streams.append(ScrapedStream(
                title=meta["title"],
                description=meta.get("description", ""),
                url=stored_url,
                quality=src.quality,
                category_slug=meta["category_slug"],
                image=meta.get("image"),
            ))

        logger.info("Scrape tamamlandı", title=meta["title"], sources=len(streams))
        return streams

    @classmethod
    async def resolve_live(cls, page_url: str) -> List[StreamSource]:
        """
        Canlı resolve — hər izləmədə çağırılır.
        Əvvəlcə aiohttp+JS parsing, sonra Playwright cəhdi.
        """
        scraper = cls(page_url=page_url)
        try:
            # 1. Əsas strategiya: aiohttp ilə JS fayllarını analiz et
            sources = await scraper._aiohttp_resolve()
            if sources:
                logger.info("aiohttp resolve uğurlu", url=page_url, count=len(sources))
                return sources
        finally:
            await scraper.close()

        # 2. Fallback: Playwright (Render-də işləməyə bilər)
        try:
            sources = await cls._playwright_resolve(page_url)
            if sources:
                logger.info("Playwright resolve uğurlu", url=page_url, count=len(sources))
                return sources
        except ImportError:
            logger.warning("Playwright quraşdırılmayıb")
        except Exception as exc:
            logger.error("Playwright xətası", error=str(exc), type=type(exc).__name__)

        logger.warning("Bütün strategiyalar uğursuz oldu", url=page_url)
        return []

    # ─────────────────────────────────────────────────────────────
    # aiohttp — əsas strategiya
    # ─────────────────────────────────────────────────────────────

    async def _aiohttp_resolve(self) -> List[StreamSource]:
        html = await self.fetch(self.page_url)
        if not html:
            return []

        # 1. Əsas HTML-də birbaşa m3u8 axtar
        direct = self._find_m3u8_in_html(html)
        if direct:
            logger.info("HTML-də m3u8 tapıldı", count=len(direct))
            return direct

        # 2. sinekfilmizle öz JS player fayllarını yüklə — m3u8 orada ola bilər
        js_sources = await self._resolve_player_js(html)
        if js_sources:
            logger.info("JS faylında m3u8 tapıldı", count=len(js_sources))
            return js_sources

        # 3. iframe/embed URL-lərini tap və resolve et
        embed_urls = self._find_embed_urls(html)
        logger.debug("Embed URL-lər tapıldı", count=len(embed_urls), urls=embed_urls)
        for embed_url in embed_urls:
            sources = await self._resolve_embed(embed_url)
            if sources:
                return sources

        return []

    async def _resolve_player_js(self, page_html: str) -> List[StreamSource]:
        """
        sinekfilmizle.com öz JS fayllarında (requests.js kimi) m3u8 URL-lərini saxlayır.
        Şəbəkə request-lərindən görünür: playlist_index-f1-v1.m3u8, master.m3u8 və s.
        Bu metod həmin JS fayllarını çəkib m3u8 tapmağa çalışır.
        """
        soup = BeautifulSoup(page_html, "lxml")
        js_urls: List[str] = []

        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            if not src:
                continue
            # Nisbi URL-ləri mütləqə çevir
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = self.base_url + src
            # Player JS fayllarını tap
            for pattern in self.PLAYER_JS_PATTERNS:
                if re.search(pattern, src, re.I):
                    js_urls.append(src)
                    break

        # Həmçinin inline <script>-lərdə başqa JS URL-ləri axtar
        for script in soup.find_all("script"):
            text = script.get_text()
            for m in re.finditer(r'''['"]((?:https?:)?//[^'"]+\.js[^'"]*)['"]''', text):
                url = m.group(1)
                if url.startswith("//"):
                    url = "https:" + url
                for pattern in self.PLAYER_JS_PATTERNS:
                    if re.search(pattern, url, re.I):
                        if url not in js_urls:
                            js_urls.append(url)
                        break

        logger.debug("Player JS faylları tapıldı", count=len(js_urls), urls=js_urls)

        for js_url in js_urls[:5]:
            js_content = await self.fetch(js_url)
            if not js_content:
                continue
            sources = self._find_m3u8_in_html(js_content)
            if sources:
                logger.info("JS faylında m3u8 tapıldı", js=js_url)
                return sources

        return []

    async def _resolve_embed(self, embed_url: str) -> List[StreamSource]:
        """Embed URL-i resolve et — növünə görə xüsusi handler-lərə yönləndir."""

        if "p2turk" in embed_url:
            return await self._resolve_p2turk(embed_url)

        html = await self.fetch(embed_url)
        if not html:
            return []

        # Birbaşa m3u8 axtar
        sources = self._find_m3u8_in_html(html)
        if sources:
            return sources

        # JWPlayer / VideoJS config axtar
        sources = self._parse_player_config(html)
        if sources:
            return sources

        # Bu səhifənin JS fayllarını da yoxla
        js_sources = await self._resolve_player_js(html)
        if js_sources:
            return js_sources

        # Daha dərin iç-içə embed-lər
        nested = self._find_embed_urls(html)
        for nested_url in nested[:3]:
            if nested_url != embed_url:
                s = await self._resolve_embed(nested_url)
                if s:
                    return s

        return []

    async def _resolve_p2turk(self, embed_url: str) -> List[StreamSource]:
        """
        p2turk.xyz player — HTML-dən m3u8 çıxarır.
        Şəbəkədən görünür ki, bu player master.m3u8 istifadə edir.
        """
        html = await self.fetch(embed_url)
        if not html:
            return []

        # p2turk m3u8-i JSON config və ya JS dəyişənlərinin içinə yerləşdirir
        patterns = [
            r'"file"\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"',
            r"'file'\s*:\s*'(https?://[^']+\.m3u8[^']*)'",
            r'source\s*:\s*[\'\"](https?://[^\'\"]+\.m3u8[^\'\"]*)',
            r'src\s*:\s*[\'\"](https?://[^\'\"]+\.m3u8[^\'\"]*)',
            r'[\'\"](https?://[^\'\"]+master\.m3u8[^\'\"]*)[\'\""]',
            r'[\'\"](https?://[^\'\"]+\.m3u8[^\'\"]*)[\'\""]',
        ]
        found: set = set()
        for pattern in patterns:
            for m in re.finditer(pattern, html, re.IGNORECASE):
                url = m.group(1).strip()
                if url:
                    found.add(url)

        if found:
            urls = list(found)
            logger.info("p2turk m3u8 tapıldı", url=embed_url, count=len(urls))
            return self._pair_video_audio(urls)

        # p2turk-un öz JS fayllarını da yoxla
        js_sources = await self._resolve_player_js(html)
        if js_sources:
            return js_sources

        # p2turk iç-içə iframe istifadə edə bilər
        nested = self._find_embed_urls(html)
        for nested_url in nested[:2]:
            if nested_url != embed_url and "p2turk" not in nested_url:
                s = await self._resolve_embed(nested_url)
                if s:
                    return s

        logger.warning("p2turk: m3u8 tapılmadı", url=embed_url)
        return []

    # ─────────────────────────────────────────────────────────────
    # Playwright — son çarə
    # ─────────────────────────────────────────────────────────────

    @classmethod
    async def _playwright_resolve(cls, page_url: str) -> List[StreamSource]:
        """
        Headless Chromium ilə tam render edir.
        Bütün network request-lərini dinləyir — m3u8 görən kimi qeyd edir.
        Render/Docker-də işləməyə bilər, ona görə son sıradadır.
        """
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout

        m3u8_urls: List[str] = []
        embed_urls: List[str] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                    "--no-zygote",
                    "--disable-extensions",
                    "--disable-software-rasterizer",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--mute-audio",
                    "--hide-scrollbars",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )

            page = await context.new_page()

            def on_request(req):
                url = req.url
                if ".m3u8" in url:
                    m3u8_urls.append(url)
                    logger.debug("m3u8 tapıldı (Playwright)", url=url)
                elif any(h in url for h in cls.KNOWN_PLAYER_HOSTS):
                    embed_urls.append(url)

            page.on("request", on_request)

            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)

                for selector in [
                    "button.play", ".play-btn", "#play", ".player-play",
                    "[data-plyr='play']", ".jw-icon-playback",
                    "video", ".video-container", ".player",
                    "img[class*='poster']", "img[class*='play']",
                ]:
                    try:
                        el = await page.query_selector(selector)
                        if el:
                            await el.click()
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass

                for _ in range(15):
                    if m3u8_urls:
                        break
                    await page.wait_for_timeout(1000)

            except PWTimeout:
                logger.warning("Playwright timeout", url=page_url)
            except Exception as exc:
                logger.error("Playwright page error", error=str(exc))

            if not m3u8_urls and embed_urls:
                for embed_url in embed_urls[:3]:
                    embed_page = await context.new_page()
                    embed_page.on("request", on_request)
                    try:
                        await embed_page.goto(embed_url, wait_until="domcontentloaded", timeout=20_000)
                        await embed_page.wait_for_timeout(4000)

                        for selector in [
                            "button[class*='play']", ".play", "#play",
                            "[data-plyr='play']", ".jw-icon-playback",
                            "video",
                        ]:
                            try:
                                el = await embed_page.query_selector(selector)
                                if el:
                                    await el.click()
                                    await embed_page.wait_for_timeout(3000)
                                    break
                            except Exception:
                                pass

                        for _ in range(10):
                            if m3u8_urls:
                                break
                            await embed_page.wait_for_timeout(1000)

                    except Exception as exc:
                        logger.warning("Embed page error", embed=embed_url, error=str(exc))
                    finally:
                        await embed_page.close()

                    if m3u8_urls:
                        break

            await browser.close()

        if not m3u8_urls:
            return []

        unique = list(dict.fromkeys(m3u8_urls))
        return cls._pair_video_audio(unique)

    # ─────────────────────────────────────────────────────────────
    # HTML parse köməkçiləri
    # ─────────────────────────────────────────────────────────────

    def _find_m3u8_in_html(self, html: str) -> List[StreamSource]:
        patterns = [
            r'''(?:file|src|source|url)\s*[:=]\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
            r'''['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
        ]
        found: set = set()
        for pattern in patterns:
            for m in re.finditer(pattern, html, re.IGNORECASE):
                found.add(m.group(1).strip())
        return self._pair_video_audio(list(found))

    def _find_embed_urls(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        urls = []

        # iframe və frame-lər
        for tag in soup.find_all(["iframe", "frame"]):
            src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src") or ""
            if src.startswith("http"):
                urls.append(src)
            elif src.startswith("//"):
                urls.append("https:" + src)

        # Script-lərdə gizlənmiş embed URL-lər
        for script in soup.find_all("script"):
            text = script.get_text()
            for m in re.finditer(r'''['"](\bhttps?://\S+?)['"]''', text):
                c = m.group(1)
                if any(h in c for h in self.KNOWN_PLAYER_HOSTS):
                    urls.append(c)

        # data-* atributlarında embed URL-lər
        for tag in soup.find_all(True):
            for attr in ["data-src", "data-url", "data-video", "data-embed"]:
                val = tag.get(attr, "")
                if val.startswith("http") and any(h in val for h in self.KNOWN_PLAYER_HOSTS):
                    urls.append(val)

        seen = set()
        return [u for u in urls if u not in seen and not seen.add(u)]

    def _parse_player_config(self, html: str) -> List[StreamSource]:
        # JWPlayer
        m = re.search(r'jwplayer\([^)]+\)\.setup\((\{.*?\})\)', html, re.DOTALL)
        if m:
            try:
                cfg = json.loads(m.group(1))
                urls = [s["file"] for s in cfg.get("sources", []) if ".m3u8" in s.get("file", "")]
                if urls:
                    return self._pair_video_audio(urls)
            except Exception:
                pass

        # VideoJS
        m = re.search(r'videojs\([^)]+\)[^{]*(\{[^}]+sources[^}]+\})', html, re.DOTALL)
        if m:
            sources = self._find_m3u8_in_html(m.group(1))
            if sources:
                return sources

        # Generic file/url/src config
        video_urls = list(set(re.findall(
            r'''(?:file|url|src)\s*:\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
            html, re.IGNORECASE
        )))
        audio_urls = list(set(re.findall(
            r'''(?:audio|sound)\s*:\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
            html, re.IGNORECASE
        )))
        if video_urls:
            return self._pair_video_audio(video_urls, audio_urls or None)

        return []

    # ─────────────────────────────────────────────────────────────
    # Meta məlumatlar
    # ─────────────────────────────────────────────────────────────

    async def _extract_meta(self) -> Optional[Dict]:
        html = await self.fetch(self.page_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")

        title = ""
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Unknown"

        desc = ""
        og_d = soup.find("meta", property="og:description")
        if og_d:
            desc = og_d.get("content", "").strip()

        image = None
        og_i = soup.find("meta", property="og:image")
        if og_i:
            image = og_i.get("content", "").strip() or None

        slug = "series" if any(k in self.page_url for k in ["/dizi/", "/sezon-", "/bolum-"]) else "movies"
        return {"title": title, "description": desc, "image": image, "category_slug": slug}

    # ─────────────────────────────────────────────────────────────
    # Video + Audio cütləşdirmə
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def _pair_video_audio(
        cls,
        video_urls: List[str],
        audio_urls: Optional[List[str]] = None,
    ) -> List[StreamSource]:
        if not video_urls:
            return []

        if audio_urls is None:
            audio_candidates = [
                u for u in video_urls
                if re.search(r'[_\-/](audio|sound|aac|ac3)[_\-/.]', u, re.I)
                or re.search(r'[-_]a\d*\.m3u8', u, re.I)
                or re.search(r'/a\.m3u8', u, re.I)
                or re.search(r'f\d+-a\d+\.m3u8', u, re.I)   # f1-a1.m3u8 kimi
            ]
            pure_video = [u for u in video_urls if u not in audio_candidates]
        else:
            audio_candidates = audio_urls
            pure_video = video_urls

        results = []
        targets = pure_video if pure_video else video_urls

        for v_url in targets:
            quality = cls._detect_quality(v_url)
            matched_audio = cls._match_audio(v_url, audio_candidates)
            results.append(StreamSource(
                video_url=v_url,
                audio_url=matched_audio,
                quality=quality,
            ))
        return results

    @staticmethod
    def _match_audio(video_url: str, audio_urls: List[str]) -> Optional[str]:
        if not audio_urls:
            return None
        base = video_url.rsplit('/', 1)[0]
        for a in audio_urls:
            if a.startswith(base):
                return a
        return audio_urls[0] if len(audio_urls) == 1 else None

    @staticmethod
    def _detect_quality(url: str) -> str:
        m = re.search(r'(\d{3,4})[pP]', url)
        if m:
            return f"{m.group(1)}p"
        if "4k" in url.lower() or "2160" in url:
            return "4K"
        if "1080" in url:
            return "1080p"
        if "720" in url:
            return "720p"
        if "480" in url:
            return "480p"
        return "HD"

    # ─────────────────────────────────────────────────────────────
    # Encoding
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _encode_source(src: StreamSource) -> str:
        data: dict = {"v": src.video_url, "q": src.quality}
        if src.audio_url:
            data["a"] = src.audio_url
        return json.dumps(data, separators=(',', ':'))

    @staticmethod
    def decode_source(stored_url: str) -> Optional[StreamSource]:
        if stored_url.startswith("{"):
            try:
                data = json.loads(stored_url)
                return StreamSource(
                    video_url=data["v"],
                    audio_url=data.get("a"),
                    quality=data.get("q", "HD"),
                )
            except (json.JSONDecodeError, KeyError):
                pass
        return StreamSource(video_url=stored_url, quality="HD")
