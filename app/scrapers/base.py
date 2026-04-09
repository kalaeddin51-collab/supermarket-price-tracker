from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceResult:
    """Returned by every scraper for a single product lookup."""
    external_id: str
    name: str
    price: float | None           # None = could not determine price
    url: str
    store: str
    in_stock: bool = True
    on_special: bool = False
    was_price: float | None = None
    image_url: str | None = None
    category: str | None = None
    unit: str | None = None
    error: bool = False
    error_message: str | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SearchResult:
    """A product hit returned from a search query."""
    external_id: str
    name: str
    price: float | None
    url: str
    store: str
    image_url: str | None = None
    category: str | None = None
    unit: str | None = None
    was_price: float | None = None
    on_special: bool = False


class BaseScraper(ABC):
    """Abstract base class all store scrapers must implement."""

    store_slug: str  # e.g. "woolworths", "coles", "harris_farm"

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search for products by name. Used when adding items to watchlist."""
        ...

    @abstractmethod
    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        """Fetch the current price for a single product."""
        ...

    async def fetch_prices(self, products: list[dict]) -> list[PriceResult]:
        """
        Fetch prices for multiple products.
        Each dict must have 'external_id' and 'url' keys.
        Default implementation calls fetch_price sequentially with a delay.
        Override in subclass for batch API calls if available.
        """
        import asyncio
        from app.config import settings

        results = []
        for product in products:
            try:
                result = await self.fetch_price(product["external_id"], product["url"])
            except Exception as exc:
                result = PriceResult(
                    external_id=product["external_id"],
                    name=product.get("name", ""),
                    price=None,
                    url=product["url"],
                    store=self.store_slug,
                    error=True,
                    error_message=str(exc),
                )
            results.append(result)
            await asyncio.sleep(settings.scrape_delay_seconds)
        return results
