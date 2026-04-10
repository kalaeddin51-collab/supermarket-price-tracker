"""
Woolworths scraper.

IMPORTANT: Woolworths blocks Railway's datacenter IP range at the Akamai
network level — they serve "Access Denied" (320 bytes) before any JavaScript
runs. No client-side approach (proxy, headless browser, TLS impersonation)
can bypass a network-level IP block.

This scraper fails fast so the UI can show a clear message.
It works fine on residential/home connections (no cloud IP block there).

Future option: use a residential proxy service like Zyte Smart Proxy (~$5/month)
which routes through home IPs that Woolworths trusts.
"""
import logging
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

logger = logging.getLogger(__name__)

WOW_HOME = "https://www.woolworths.com.au"
SEARCH_API = f"{WOW_HOME}/apis/ui/Search/products"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": WOW_HOME,
    "Referer": f"{WOW_HOME}/shop/search/products?searchTerm=milk",
    "request-id": "|abc123.def456",
}


def _parse_product(item: dict) -> SearchResult | None:
    stockcode = str(item.get("Stockcode", ""))
    if not stockcode:
        return None
    name = item.get("Name", "")
    price = item.get("Price") or item.get("InstorePrice")
    cup_string = item.get("CupString")
    image = f"https://cdn0.woolworths.media/content/wowproductimages/large/{stockcode}.jpg"
    return SearchResult(
        external_id=stockcode,
        name=name,
        price=float(price) if price is not None else None,
        url=f"{WOW_HOME}/shop/productdetails/{stockcode}",
        store="woolworths",
        image_url=image,
        unit=cup_string,
    )


class WoolworthsScraper(BaseScraper):
    store_slug = "woolworths"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=30,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """
        Attempt a direct POST to Woolworths API.

        Works on: residential/home internet connections.
        Blocked on: Railway, AWS, GCP, Azure (Akamai network-level IP block).

        If you are deploying on a cloud server and want Woolworths results,
        you need a residential proxy service (e.g. Zyte Smart Proxy ~$5/month).
        """
        client = await self._get_client()

        # Warm up session cookies
        try:
            r = await client.get(f"{WOW_HOME}/")
            if "Access Denied" in r.text or r.status_code == 403:
                raise RuntimeError(
                    "Woolworths is blocking this server's IP (Akamai network block). "
                    "A residential proxy is required — see /settings for options."
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Woolworths connection failed: {exc}") from exc

        payload = {
            "Filters": [], "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={query}",
            "PageNumber": 1, "PageSize": limit,
            "SearchTerm": query, "SortType": "TraderRelevance",
            "token": "", "gpBoost": 0, "CategoryVersion": "v2",
        }
        resp = await client.post(SEARCH_API, json=payload)

        if resp.status_code in (403, 429, 503):
            raise RuntimeError(
                f"Woolworths blocked request (HTTP {resp.status_code}). "
                "This cloud server's IP is on Akamai's blocklist."
            )
        resp.raise_for_status()

        data = resp.json()
        products_raw = []
        for bundle in data.get("Products", []):
            products_raw.extend(bundle.get("Products", []))
        logger.info("Woolworths: %d products for %r", len(products_raw), query)
        return [p for p in (_parse_product(x) for x in products_raw) if p]

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        client = await self._get_client()
        target = f"{WOW_HOME}/api/v3/ui/schemaorg/product/{external_id}"
        resp = await client.get(target)
        resp.raise_for_status()
        data = resp.json()

        offers = data.get("offers") or {}
        price = offers.get("price")
        availability = offers.get("availability", "")
        in_stock = "InStock" in availability if availability else True
        price_specs = offers.get("priceSpecification") or []
        was_price = None
        on_special = False
        if isinstance(price_specs, list):
            for spec in price_specs:
                if isinstance(spec, dict) and spec.get("price") and spec.get("price") != price:
                    was_price = spec["price"]
                    on_special = True

        name = data.get("name", "")
        image = data.get("image",
                         f"https://cdn0.woolworths.media/content/wowproductimages/large/{external_id}.jpg")
        return PriceResult(
            external_id=external_id, name=name,
            price=float(price) if price is not None else None,
            was_price=float(was_price) if was_price is not None else None,
            url=url, store=self.store_slug,
            in_stock=in_stock, on_special=on_special,
            image_url=image, unit=None,
        )
