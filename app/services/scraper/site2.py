from __future__ import annotations

from typing import List

from app.services.scraper.base import BaseScraper, ScrapedStream
from app.utils.logging import get_logger

logger = get_logger(__name__)


class Site2Scraper(BaseScraper):
    """
    Example scraper for a second site — adapt selectors as needed.
    """

    name = "site2"
    base_url = "https://example-streaming-site2.com"

    async def scrape(self) -> List[ScrapedStream]:
        results: List[ScrapedStream] = []

        for category_slug, path in [("series", "/series"), ("sports", "/live")]:
            html = await self.fetch(f"{self.base_url}{path}")
            if not html:
                continue

            soup = self.parse_html(html)

            # ── Adapt these selectors ──────────────────────────────────
            for row in soup.select("table.content-table tr.item-row"):
                cells = row.select("td")
                if len(cells) < 3:
                    continue
                title = cells[0].get_text(strip=True)
                quality = cells[1].get_text(strip=True) or "SD"
                link_el = cells[2].select_one("a")
                if not link_el:
                    continue
                url = link_el.get("href", "")
                if not url.startswith("http"):
                    url = self.base_url + url

                stream = ScrapedStream(
                    title=title,
                    description="",
                    url=url,
                    quality=quality,
                    category_slug=category_slug,
                )
                results.append(self.normalize(stream))
            # ──────────────────────────────────────────────────────────

        logger.info("Site2 scrape complete", count=len(results))
        return results
