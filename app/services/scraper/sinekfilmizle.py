from __future__ import annotations

import re
import json
import asyncio
from typing import List, Optional, Dict
from dataclasses import dataclass, field

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
    label: str = ""

    def is_dual(self) -> bool:
        return self.audio_url is not None and self.audio_url != self.video_url


class SinekfilmizleScraper(BaseScraper):
    """
    Sinekfilmizle.com üçün scraper.

    Strategiya:
    1. Sayt səhifəsini fetch edir
    2. iframe / embed URL-ni tapır
    3. Embed səhifəsindən JS source-ları, m3u8 linklərini çıxarır
    4. Video + audio ayrı m3u8 olarsa hər ikisini qaytarır

    Playwright olmadan işləyir — əgər JS render lazımdırsa,
    playwright_resolve() metodunu istifadə et.
    """

    name = "sinekfilmizle"
    base_url = "https://sinekfilmizle.com"

    # Saytın video player-i üçün tanınan host-lar
    KNOWN_PLAYER_HOSTS = [
        "vidmoly", "filemoon", "doodstream", "mixdrop",
        "streamtape", "voe.sx", "upstream", "vudeo",
        "player.php", "embed", "play", "stream",
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

        sources = await self._resolve_sources()
        if not sources:
            logger.warning("No sources found", url=self.page_url)
            return []

        streams: List[ScrapedStream] = []
        for src in sources:
            # URL-i JSON encode edib saxlayırıq ki player hər ikisini bilsin
            stored_url = self._encode_source(src)
            streams.append(ScrapedStream(
                title=meta["title"],
                description=meta.get("description", ""),
                url=stored_url,
                quality=src.quality,
                category_slug=meta["category_slug"],
                image=meta.get("image"),
            ))

        logger.info("Sinekfilmizle scrape done",
                    title=meta["title"], sources=len(streams))
        return streams

    @classmethod
    async def resolve_live(cls, page_url: str) -> Optional[List[StreamSource]]:
        """
        Canlı resolve — player tərəfindən hər izləmədə çağırılır.
        Qaytarır: StreamSource siyahısı (video+audio cütü).
        """
        scraper = cls(page_url=page_url)
        try:
            return await scraper._resolve_sources()
        finally:
            await scraper.close()

    # ─────────────────────────────────────────────────────────────
    # Meta məlumatları
    # ─────────────────────────────────────────────────────────────

    async def _extract_meta(self) -> Optional[Dict]:
        html = await self.fetch(self.page_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "lxml")

        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Unknown"

        desc = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            desc = og_desc.get("content", "").strip()

        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content", "").strip() or None

        # Kateqoriya URL-dən müəyyən edilir
        slug = "series" if any(k in self.page_url for k in ["/dizi/", "/sezon-", "/bolum-"]) else "movies"

        return {
            "title": title,
            "description": desc,
            "image": image,
            "category_slug": slug,
            "html": html,
        }

    # ─────────────────────────────────────────────────────────────
    # Stream mənbəyi tapma
    # ─────────────────────────────────────────────────────────────

    async def _resolve_sources(self) -> List[StreamSource]:
        html = await self.fetch(self.page_url)
        if not html:
            return []

        sources: List[StreamSource] = []

        # 1. Birbaşa m3u8 linki HTML-in içindədir?
        direct = self._find_m3u8_in_html(html)
        if direct:
            sources.extend(direct)
            return sources

        # 2. iframe / embed URL-lərini tap
        embed_urls = self._find_embed_urls(html)
        logger.info("Found embed URLs", count=len(embed_urls), embeds=embed_urls)

        for embed_url in embed_urls:
            embed_sources = await self._resolve_embed(embed_url)
            sources.extend(embed_sources)
            if sources:
                break  # İlk işləyən embed kifayətdir

        return sources

    def _find_m3u8_in_html(self, html: str) -> List[StreamSource]:
        """HTML-in özündə m3u8 var mı?"""
        results = []

        # file:"...m3u8" və ya src:"...m3u8" pattern-ləri
        patterns = [
            r'''(?:file|src|source)\s*[:=]\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
            r'''['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
        ]
        found_urls = set()
        for pattern in patterns:
            for m in re.finditer(pattern, html, re.IGNORECASE):
                url = m.group(1).strip()
                if url not in found_urls:
                    found_urls.add(url)

        # Dublikatları təmizlə, video/audio cütlərini tap
        results = self._pair_video_audio(list(found_urls))
        return results

    def _find_embed_urls(self, html: str) -> List[str]:
        """iframe src, data-src, embed URL-lərini tap."""
        soup = BeautifulSoup(html, "lxml")
        urls = []

        # iframe-lər
        for tag in soup.find_all(["iframe", "frame"]):
            src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src", "")
            if src and src.startswith("http"):
                urls.append(src)

        # <a> linklər içindəki embed keçidlər
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(h in href for h in self.KNOWN_PLAYER_HOSTS) and href.startswith("http"):
                urls.append(href)

        # JS-dəki URL-lər (string literal olaraq)
        for script in soup.find_all("script"):
            text = script.get_text()
            for m in re.finditer(r'''['"](\bhttps?://\S+(?:embed|player|play|stream|vod)\S*?)['"]''', text):
                candidate = m.group(1)
                if any(h in candidate for h in self.KNOWN_PLAYER_HOSTS):
                    urls.append(candidate)

        # Dublikatları saxla, sıranı qoru
        seen = set()
        result = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    async def _resolve_embed(self, embed_url: str) -> List[StreamSource]:
        """Embed səhifəsindən m3u8 tap."""
        html = await self.fetch(embed_url)
        if not html:
            return []

        # 1. Birbaşa m3u8
        sources = self._find_m3u8_in_html(html)
        if sources:
            return sources

        # 2. JWPlayer / VideoJS / DPlayer konfiqurasyonu
        sources = self._parse_player_config(html)
        if sources:
            return sources

        # 3. İç-içə iframe (bir embed başqasını yükləyir)
        nested = self._find_embed_urls(html)
        for nested_url in nested[:3]:  # Maksimum 3 səviyyə
            if nested_url != embed_url:
                nested_sources = await self._resolve_embed(nested_url)
                if nested_sources:
                    return nested_sources

        return []

    def _parse_player_config(self, html: str) -> List[StreamSource]:
        """JWPlayer, VideoJS, DPlayer JSON konfiqurasyonunu parse et."""
        results = []

        # JWPlayer: jwplayer(...).setup({...})
        jw_match = re.search(
            r'jwplayer\s*\(\s*["\'][^"\']*["\']\s*\)\s*\.\s*setup\s*\(\s*(\{.*?\})\s*\)',
            html, re.DOTALL
        )
        if jw_match:
            try:
                config = json.loads(jw_match.group(1))
                for src in config.get("sources", []):
                    file_url = src.get("file", "")
                    if ".m3u8" in file_url:
                        results.append(StreamSource(
                            video_url=file_url,
                            quality=src.get("label", "HD"),
                        ))
                if results:
                    return results
            except json.JSONDecodeError:
                pass

        # VideoJS: var player = videojs(...); player.src([...])
        vjs_match = re.search(r'\.src\s*\(\s*(\[.*?\])\s*\)', html, re.DOTALL)
        if vjs_match:
            try:
                sources = json.loads(vjs_match.group(1))
                for src in sources:
                    if isinstance(src, dict) and ".m3u8" in src.get("src", ""):
                        results.append(StreamSource(
                            video_url=src["src"],
                            quality=src.get("label", "HD"),
                        ))
                if results:
                    return results
            except json.JSONDecodeError:
                pass

        # DPlayer: new DPlayer({video: {url: "...", pic: "..."}})
        dp_match = re.search(r'new\s+DPlayer\s*\(\s*(\{.*?\})\s*\)', html, re.DOTALL)
        if dp_match:
            try:
                config_str = dp_match.group(1)
                # url field-ini tap
                url_m = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', config_str)
                audio_m = re.search(r'"audio"\s*:\s*"([^"]+\.m3u8[^"]*)"', config_str)
                if url_m:
                    results.append(StreamSource(
                        video_url=url_m.group(1),
                        audio_url=audio_m.group(1) if audio_m else None,
                        quality="HD",
                    ))
                if results:
                    return results
            except Exception:
                pass

        # Ümumi JS object axtarışı — {file: "...", audio: "..."}
        # video m3u8
        video_urls = list(set(re.findall(
            r'''(?:file|url|src|video)\s*:\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
            html, re.IGNORECASE
        )))
        # audio m3u8
        audio_urls = list(set(re.findall(
            r'''(?:audio|sound)\s*:\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''',
            html, re.IGNORECASE
        )))

        if video_urls:
            results = self._pair_video_audio(video_urls, audio_urls)

        return results

    # ─────────────────────────────────────────────────────────────
    # Video + Audio cütləşdirmə
    # ─────────────────────────────────────────────────────────────

    def _pair_video_audio(
        self,
        video_urls: List[str],
        audio_urls: Optional[List[str]] = None,
    ) -> List[StreamSource]:
        """
        URL siyahısından video+audio cütlərini müəyyən et.

        Ümumi pattern: CDN-dəki URL-lərdə
          - video: ...v.m3u8 / ...video.m3u8 / ...720p.m3u8
          - audio: ...a.m3u8 / ...audio.m3u8 / ...aac.m3u8
        """
        if not video_urls:
            return []

        if audio_urls is None:
            # URL-ləri video/audio olaraq ayır
            audio_candidates = [
                u for u in video_urls
                if re.search(r'[_\-/](audio|sound|aac|ac3)[_\-/.]', u, re.I)
                or u.endswith('a.m3u8')
            ]
            pure_video = [
                u for u in video_urls
                if u not in audio_candidates
            ]
        else:
            audio_candidates = audio_urls
            pure_video = video_urls

        results = []

        if pure_video:
            # Keyfiyyət etiketləri (720p, 1080p, vs.) hər video üçün
            for v_url in pure_video:
                quality = self._detect_quality(v_url)
                # Bu video URL-inə uyğun audio var mı?
                matched_audio = self._match_audio(v_url, audio_candidates)
                results.append(StreamSource(
                    video_url=v_url,
                    audio_url=matched_audio,
                    quality=quality,
                ))
        elif audio_candidates:
            # Yalnız audio URL-lər tapıldı (nadir hal)
            for a_url in audio_candidates:
                results.append(StreamSource(video_url=a_url, quality="Audio"))

        return results

    def _match_audio(self, video_url: str, audio_urls: List[str]) -> Optional[str]:
        """Video URL-ə uyğun audio URL-i tap (eyni CDN path prefix)."""
        if not audio_urls:
            return None
        # Eyni base path-i paylaşan audio
        base = video_url.rsplit('/', 1)[0]
        for a_url in audio_urls:
            if a_url.startswith(base):
                return a_url
        # Yalnız bir audio varsa onu istifadə et
        if len(audio_urls) == 1:
            return audio_urls[0]
        return None

    @staticmethod
    def _detect_quality(url: str) -> str:
        """URL-dən keyfiyyəti müəyyən et."""
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
    # URL encoding (DB-də saxlamaq üçün)
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _encode_source(src: StreamSource) -> str:
        """
        StreamSource-u JSON string-ə çevir.
        Format: {"v": "...", "a": "...", "q": "..."}
        Əgər audio yoxdursa: {"v": "...", "q": "..."}
        """
        data: Dict = {"v": src.video_url, "q": src.quality}
        if src.audio_url:
            data["a"] = src.audio_url
        return json.dumps(data, separators=(',', ':'))

    @staticmethod
    def decode_source(stored_url: str) -> Optional[StreamSource]:
        """
        DB-dəki URL string-i StreamSource-a geri çevir.
        Köhnə format (birbaşa URL) da dəstəklənir.
        """
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
        # Köhnə format — birbaşa URL
        return StreamSource(video_url=stored_url, quality="HD")
