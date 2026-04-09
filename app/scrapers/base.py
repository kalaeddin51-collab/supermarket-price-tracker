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
        import httpx
        from app.config import settings

        results = []
        for product in products:
            result = await self._fetch_with_retry(product, settings.scrape_delay_seconds)
            results.append(result)
            await asyncio.sleep(settings.scrape_delay_seconds)
        return results

    async def _fetch_with_retry(self, product: dict, base_delay: float, max_retries: int = 3) -> PriceResult:
        """Fetch a single product price with exponential backoff on 429/529 rate-limit responses."""
        import asyncio
        import httpx

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self.fetch_price(product["external_id"], product["url"])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 529) and attempt < max_retries:
                    # Rate-limited: wait longer each attempt (3s → 9s → 27s)
                    wait = base_delay * (3 ** attempt)
                    await asyncio.sleep(wait)
                    last_exc = exc
                    continue
                last_exc = exc
                break
            except Exception as exc:
                last_exc = exc
                break

        return PriceResult(
            external_id=product["external_id"],
            name=product.get("name", ""),
            price=None,
            url=product["url"],
            store=self.store_slug,
            error=True,
            error_message=str(last_exc),
        )
