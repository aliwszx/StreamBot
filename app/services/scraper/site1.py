from __future__ import annotations

from typing import List

from app.services.scraper.base import BaseScraper, ScrapedStream
from app.utils.logging import get_logger

logger = get_logger(__name__)


class Site1Scraper(BaseScraper):
    """
    Example scraper — replace selectors with the real site's structure.
    Target: a page that lists items with title, description, and a stream link.
    """

    name = "site1"
    base_url = "https://example-streaming-site1.com"

    async def scrape(self) -> List[ScrapedStream]:
        results: List[ScrapedStream] = []

        index_html = await self.fetch(f"{self.base_url}/movies")
        if not index_html:
            return results

        soup = self.parse_html(index_html)

        # ── Adapt these selectors to the real site ──────────────────────
        for card in soup.select("div.movie-card"):
            title_el = card.select_one("h2.title")
            desc_el = card.select_one("p.description")
            link_el = card.select_one("a.stream-link")
            img_el = card.select_one("img")

            if not title_el or not link_el:
                continue

            url = link_el.get("href", "")
            if not url.startswith("http"):
                url = self.base_url + url

            stream = ScrapedStream(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(strip=True) if desc_el else "",
                url=url,
                quality=link_el.get("data-quality", "HD"),
                category_slug="movies",
                image=img_el.get("src") if img_el else None,
            )
            results.append(self.normalize(stream))
        # ────────────────────────────────────────────────────────────────

        logger.info("Site1 scrape complete", count=len(results))
        return results
