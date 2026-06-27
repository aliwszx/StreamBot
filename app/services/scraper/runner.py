from __future__ import annotations

from typing import List, Type

from app.services.scraper.base import BaseScraper, ScrapedStream
from app.database import queries
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Avtomatik scraper-lər (gələcəkdə əlavə edilə bilər)
SCRAPERS: List[Type[BaseScraper]] = []


async def run_all_scrapers() -> int:
    """Qeydə alınmış bütün scraper-ləri işlət."""
    total = 0
    for scraper_cls in SCRAPERS:
        scraper = scraper_cls()
        try:
            streams = await scraper.scrape()
            saved = await _persist(streams)
            total += saved
            logger.info("Scraper finished", scraper=scraper.name, saved=saved)
        except Exception as exc:
            logger.error("Scraper error", scraper=scraper_cls.name, error=str(exc))
        finally:
            await scraper.close()
    return total


async def _persist(streams: List[ScrapedStream]) -> int:
    saved = 0
    categories = {cat.slug: cat for cat in await queries.get_categories()}

    for s in streams:
        cat = categories.get(s.category_slug)
        if cat is None:
            logger.warning("Unknown category slug, skipping", slug=s.category_slug)
            continue

        existing = await queries.search_items(s.title, limit=1)
        existing_in_cat = [i for i in existing if i.category_id == cat.id]
        if existing_in_cat:
            item = existing_in_cat[0]
        else:
            item = await queries.create_item(
                title=s.title,
                description=s.description,
                category_id=cat.id,
                image=s.image,
            )

        await queries.create_stream(item_id=item.id, url=s.url, quality=s.quality)
        saved += 1
    return saved
