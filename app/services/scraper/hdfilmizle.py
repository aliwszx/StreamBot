from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup

from app.services.scraper.base import BaseScraper, ScrapedStream
from app.utils.logging import get_logger

logger = get_logger(__name__)


class HDFilmizleScraper(BaseScraper):
    """
    Scraper for hdfilmizle.to

    Vidrame embed URLs expire after a while, so we no longer store the
    resolved embed URL itself in the database. Instead the *page URL* is
    stored as the stream, and the embed is re-resolved live (see
    `resolve_embed_url`) every time someone actually opens the player.
    """

    name = "hdfilmizle"
    base_url = "https://www.hdfilmizle.to"

    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.page_url = page_url

    async def _get_metadata_and_embed(self) -> Optional[dict]:
        html = await self.fetch(self.page_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        # ── Title ──
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Unknown"

        # ── Description ──
        desc = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            desc = og_desc.get("content", "").strip()

        # ── Image ──
        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content", "").strip() or None

        # ── Category slug ──
        slug = "series" if "/dizi/" in self.page_url else "movies"

        # ── Vidrame embed URL ──
        embed_url = self._extract_embed_from_html(html)
        if not embed_url:
            logger.warning("Vidrame embed not found", url=self.page_url)
            return None

        return {
            "title": title,
            "description": desc,
            "image": image,
            "category_slug": slug,
            "embed_url": embed_url,
        }

    @staticmethod
    def _extract_embed_from_html(html: str) -> Optional[str]:
        """Pull the (current, possibly fresh) Vidrame embed URL out of page HTML."""
        soup = BeautifulSoup(html, "lxml")

        embed_url = None
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            if "vidrame.pro/vr/" in src:
                embed_url = src
                break
        if not embed_url:
            match = re.search(r"(https?://vidrame\.pro/vr/[a-f0-9]+)", html)
            if match:
                embed_url = match.group(1)

        if not embed_url:
            return None

        # Normalise: ensure no query string junk
        return embed_url.split("?")[0]

    @classmethod
    async def resolve_embed_url(cls, page_url: str) -> Optional[str]:
        """
        Lightweight, on-demand resolver: fetch the hdfilmizle page *right now*
        and return whatever Vidrame embed URL it currently contains.

        Called every time a user opens the player, instead of relying on a
        cached embed URL that Vidrame may have already invalidated.
        """
        scraper = cls(page_url=page_url)
        try:
            html = await scraper.fetch(page_url)
            if not html:
                return None
            embed_url = cls._extract_embed_from_html(html)
            if not embed_url:
                logger.warning("Live resolve: embed not found", url=page_url)
            return embed_url
        finally:
            await scraper.close()

    async def scrape(self) -> List[ScrapedStream]:
        meta = await self._get_metadata_and_embed()
        if not meta:
            return []

        logger.info(
            "HDFilmizle scrape complete",
            title=meta["title"],
            page=self.page_url,
        )

        return [
            ScrapedStream(
                title=meta["title"],
                description=meta["description"],
                # Store the PAGE url, not the embed url: Vidrame embed links
                # expire, so the actual embed is resolved live at watch-time
                # via HDFilmizleScraper.resolve_embed_url().
                url=self.page_url,
                quality="Vidrame",
                category_slug=meta["category_slug"],
                image=meta["image"],
            )
        ]
