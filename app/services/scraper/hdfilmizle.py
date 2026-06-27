from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from app.services.scraper.base import BaseScraper, ScrapedStream
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Quality label map: resolution height → label
QUALITY_MAP = {
    "2160": "4K",
    "1080": "1080p",
    "720": "720p",
    "480": "480p",
    "360": "360p",
}

VIDRAME_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://vidrame.pro",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}


class HDFilmizleScraper(BaseScraper):
    """
    Scraper for hdfilmizle.to
    Extracts Vidrame embed streams (360p / 480p / 720p / 1080p).

    Usage:
        scraper = HDFilmizleScraper(page_url="https://www.hdfilmizle.to/dizi/pluribus/sezon-1/bolum-1/")
        streams = await scraper.scrape()
    """

    name = "hdfilmizle"
    base_url = "https://www.hdfilmizle.to"

    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.page_url = page_url

    # ── Step 1: fetch hdfilmizle page and extract Vidrame embed ID ────────

    async def _get_vidrame_id(self) -> Optional[str]:
        html = await self.fetch(self.page_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        # Look for <iframe src="https://vidrame.pro/vr/<ID>">
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            match = re.search(r"vidrame\.pro/vr/([a-f0-9]+)", src)
            if match:
                return match.group(1)

        # Fallback: search raw HTML for the pattern
        match = re.search(r"vidrame\.pro/vr/([a-f0-9]+)", html)
        if match:
            return match.group(1)

        logger.warning("Vidrame ID not found", url=self.page_url)
        return None

    # ── Step 2: fetch master.txt with proper Referer ──────────────────────

    async def _fetch_vidrame(self, path: str, referer: str) -> Optional[str]:
        """Fetch a Vidrame endpoint with same-origin headers."""
        session = await self._get_session()
        headers = {**VIDRAME_HEADERS, "Referer": referer}
        try:
            async with session.get(
                path,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as exc:
            logger.error("Vidrame fetch failed", url=path, error=str(exc))
            return None

    # ── Step 3: parse master.txt and resolve quality URLs ─────────────────

    def _parse_master(self, master_txt: str, base: str) -> List[dict]:
        """
        Parse HLS master playlist (txt format) and return list of
        {"quality": "720p", "url": "https://vidrame.pro/vr/get/<id>/720.txt"}
        """
        streams = []
        lines = master_txt.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXT-X-STREAM-INF"):
                # Extract resolution
                res_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
                quality = "HD"
                if res_match:
                    height = res_match.group(2)
                    quality = QUALITY_MAP.get(height, f"{height}p")

                # Next non-empty line is the URI
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i < len(lines):
                    uri = lines[i].strip()
                    if not uri.startswith("http"):
                        uri = base + uri
                    streams.append({"quality": quality, "url": uri})
            i += 1
        return streams

    # ── Step 4: get page metadata (title, description, image) ─────────────

    async def _get_metadata(self) -> dict:
        html = await self.fetch(self.page_url)
        if not html:
            return {}
        soup = BeautifulSoup(html, "lxml")

        # Title
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else ""

        # Description
        desc = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            desc = og_desc.get("content", "").strip()
        if not desc:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                desc = meta_desc.get("content", "").strip()

        # Image
        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content", "").strip() or None

        # Category slug — infer from URL path
        # e.g. /dizi/... → "series", /film/... → "movies"
        slug = "movies"
        if "/dizi/" in self.page_url:
            slug = "series"

        return {
            "title": title,
            "description": desc,
            "image": image,
            "category_slug": slug,
        }

    # ── Main scrape entry point ────────────────────────────────────────────

    async def scrape(self) -> List[ScrapedStream]:
        results: List[ScrapedStream] = []

        # 1. Get Vidrame embed ID
        vid_id = await self._get_vidrame_id()
        if not vid_id:
            logger.error("Could not extract Vidrame ID", page=self.page_url)
            return results

        embed_url = f"https://vidrame.pro/vr/{vid_id}"
        master_url = f"https://vidrame.pro/vr/get/{vid_id}/master.txt"
        base_url   = f"https://vidrame.pro/vr/get/{vid_id}/"

        logger.info("Found Vidrame embed", id=vid_id, embed=embed_url)

        # 2. Fetch master.txt with proper Referer
        master_txt = await self._fetch_vidrame(master_url, referer=embed_url)
        if not master_txt:
            logger.error("Failed to fetch master.txt", url=master_url)
            return results

        # 3. Parse quality list
        quality_streams = self._parse_master(master_txt, base=base_url)
        if not quality_streams:
            logger.warning("No streams found in master.txt", id=vid_id)
            return results

        logger.info("Found streams", count=len(quality_streams), qualities=[s["quality"] for s in quality_streams])

        # 4. Get page metadata
        meta = await self._get_metadata()
        title    = meta.get("title", "Unknown")
        desc     = meta.get("description", "")
        image    = meta.get("image")
        cat_slug = meta.get("category_slug", "movies")

        # 5. Build ScrapedStream for each quality
        for s in quality_streams:
            results.append(
                ScrapedStream(
                    title=title,
                    description=desc,
                    url=s["url"],
                    quality=s["quality"],
                    category_slug=cat_slug,
                    image=image,
                )
            )

        logger.info("HDFilmizle scrape complete", page=self.page_url, streams=len(results))
        return results
