"""
Woolworths scraper using their internal API (reverse-engineered from the website).

Working endpoints:
  POST https://www.woolworths.com.au/apis/ui/Search/products  — product search
  GET  https://www.woolworths.com.au/apis/ui/product/detail?stockcode={id} — product detail
"""
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

BASE_URL = "https://www.woolworths.com.au/apis/ui"

# Headers that mimic a normal browser session
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Content-Type": "application/json",
    "Referer": "https://www.woolworths.com.au/shop/search/products?searchTerm=milk",
    "Origin": "https://www.woolworths.com.au",
    "request-id": "|abc123.def456",
}


def _parse_product(item: dict, store: str = "woolworths") -> SearchResult:
    """Parse a product dict from the Woolworths API into a SearchResult."""
    stockcode = str(item.get("Stockcode", ""))
    name = item.get("Name", "")
    price = item.get("Price") or item.get("InstorePrice")
    cup_string = item.get("CupString")  # e.g. "$1.20 per 100g"
    image = None
    if item.get("LargeImageFile"):
        image = f"https://cdn0.woolworths.media/content/wowproductimages/large/{stockcode}.jpg"
    category = item.get("PiesCategoryIdPath", "")

    return SearchResult(
        external_id=stockcode,
        name=name,
        price=float(price) if price is not None else None,
        url=f"https://www.woolworths.com.au/shop/productdetails/{stockcode}",
        store=store,
        image_url=image,
        category=category,
        unit=cup_string,
    )


class WoolworthsScraper(BaseScraper):
    store_slug = "woolworths"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a shared async client, creating one if needed.
        The client persists cookies across requests (needed for session auth).
        """
        if self._client is None or self._client.is_closed:
            proxy = settings.scraper_proxy or None
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=settings.request_timeout_seconds,
                follow_redirects=True,
                proxy=proxy,
            )
            # Hit the homepage once to establish a session cookie
            await self._client.get("https://www.woolworths.com.au/")
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        client = await self._get_client()

        payload = {
            "Filters": [],
            "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={query}",
            "PageNumber": 1,
            "PageSize": limit,
            "SearchTerm": query,
            "SortType": "TraderRelevance",
            "token": "",
            "gpBoost": 0,
            "CategoryVersion": "v2",
        }

        params = {"store_id": settings.woolworths_store_id} if settings.woolworths_store_id else {}

        resp = await client.post(
            f"{BASE_URL}/Search/products",
            json=payload,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        # Response shape: {"Products": [{"Products": [...product dicts...]}]}
        products = []
        for bundle in data.get("Products", []):
            products.extend(bundle.get("Products", []))

        return [_parse_product(p) for p in products if p.get("Stockcode")]

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        client = await self._get_client()

        params = {"store_id": settings.woolworths_store_id} if settings.woolworths_store_id else {}

        resp = await client.get(
            f"https://www.woolworths.com.au/api/v3/ui/schemaorg/product/{external_id}",
        )
        resp.raise_for_status()
        data = resp.json()

        offers = data.get("offers") or {}
        price = offers.get("price")
        availability = offers.get("availability", "")
        in_stock = "InStock" in availability if availability else True

        # Check priceSpecification for was/special price
        price_specs = offers.get("priceSpecification") or []
        was_price = None
        on_special = False
        if isinstance(price_specs, list):
            for spec in price_specs:
                if isinstance(spec, dict) and spec.get("price") and spec.get("price") != price:
                    was_price = spec["price"]
                    on_special = True

        name = data.get("name", "")
        image = data.get("image", f"https://cdn0.woolworths.media/content/wowproductimages/large/{external_id}.jpg")
        cup_string = None  # not available in schema.org format

        return PriceResult(
            external_id=external_id,
            name=name,
            price=float(price) if price is not None else None,
            was_price=float(was_price) if was_price is not None else None,
            url=url,
            store=self.store_slug,
            in_stock=in_stock,
            on_special=on_special,
            image_url=image,
            unit=cup_string,
        )
