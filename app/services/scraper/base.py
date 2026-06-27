from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from app.utils.logging import get_logger
from app.utils.validators import is_valid_url, normalize_url

logger = get_logger(__name__)


@dataclass
class ScrapedStream:
    title: str
    description: str
    url: str
    quality: str
    category_slug: str
    image: Optional[str] = None


class BaseScraper(abc.ABC):
    """Abstract base class for all site scrapers."""

    name: str = "base"
    base_url: str = ""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; StreamBot/1.0; +https://github.com/yourorg/streambot)"
                )
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def fetch(self, url: str) -> Optional[str]:
        """Fetch a URL and return HTML text, or None on error."""
        if not is_valid_url(url):
            logger.warning("Invalid URL skipped", url=url, scraper=self.name)
            return None
        session = await self._get_session()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as exc:
            logger.error("Fetch failed", url=url, error=str(exc), scraper=self.name)
            return None

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @abc.abstractmethod
    async def scrape(self) -> List[ScrapedStream]:
        """Fetch data and return a list of ScrapedStream objects."""

    def normalize(self, stream: ScrapedStream) -> ScrapedStream:
        stream.url = normalize_url(stream.url)
        return stream

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
