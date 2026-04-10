"""
Woolworths scraper — two strategies:

1. Direct API (no proxy): POST to internal /apis/ui/Search/products
2. ScraperAPI mode: GET the HTML search page and parse __NEXT_DATA__ JSON
   (GET requests work reliably through ScraperAPI; POST forwarding is unreliable)
"""
import json as _json
import logging
import re
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings, get_scraperapi_key

logger = logging.getLogger(__name__)

BASE_URL = "https://www.woolworths.com.au/apis/ui"
WOW_HOME = "https://www.woolworths.com.au"

# Headers that mimic a normal browser session
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.woolworths.com.au/",
}

API_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
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


def _parse_nextdata_product(item: dict) -> SearchResult | None:
    """Parse a product from __NEXT_DATA__ embedded in Woolworths HTML."""
    stockcode = str(item.get("Stockcode", "") or item.get("stockcode", ""))
    if not stockcode:
        return None
    name = item.get("Name", "") or item.get("name", "")
    price = item.get("Price") or item.get("InstorePrice")
    cup_string = item.get("CupString") or item.get("cupString")
    image = f"https://cdn0.woolworths.media/content/wowproductimages/large/{stockcode}.jpg"

    return SearchResult(
        external_id=stockcode,
        name=name,
        price=float(price) if price is not None else None,
        url=f"https://www.woolworths.com.au/shop/productdetails/{stockcode}",
        store="woolworths",
        image_url=image,
        unit=cup_string,
    )


def _scraperapi_url(target_url: str, country: str = "au", render: bool = False) -> str:
    """Wrap a target URL with ScraperAPI using Australian residential IPs."""
    url = (
        f"http://api.scraperapi.com"
        f"?api_key={get_scraperapi_key()}"
        f"&url={urllib.parse.quote(target_url, safe='')}"
        f"&country_code={country}"
        f"&keep_headers=true"
    )
    if render:
        url += "&render=true"
    return url


def _use_scraperapi() -> bool:
    return bool(get_scraperapi_key())


class WoolworthsScraper(BaseScraper):
    store_slug = "woolworths"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a shared async client, creating one if needed."""
        if self._client is None or self._client.is_closed:
            proxy = settings.scraper_proxy or None
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=120,  # render=true can take up to 90s
                follow_redirects=True,
                proxy=proxy if not _use_scraperapi() else None,
            )
            if not _use_scraperapi():
                # Hit the homepage once to establish a session cookie
                try:
                    await self._client.get(f"{WOW_HOME}/")
                except Exception:
                    pass
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        if _use_scraperapi():
            return await self._search_via_html(query, limit)
        return await self._search_via_api(query, limit)

    async def _search_via_html(self, query: str, limit: int) -> list[SearchResult]:
        """GET the Woolworths search HTML page through ScraperAPI and parse __NEXT_DATA__."""
        client = await self._get_client()
        search_url = f"{WOW_HOME}/shop/search/products?searchTerm={urllib.parse.quote(query)}"
        # render=True executes JavaScript so Woolworths products load into the DOM
        api_url = _scraperapi_url(search_url, render=True)

        logger.info("Woolworths HTML search via ScraperAPI (render=true) for %r", query)
        try:
            resp = await client.get(api_url, timeout=90)
            logger.info("Woolworths HTML resp: %d, len=%d", resp.status_code, len(resp.text))
        except Exception as exc:
            logger.error("Woolworths HTML request failed: %s", exc)
            raise

        resp.raise_for_status()

        # Parse __NEXT_DATA__ embedded JSON
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not match:
            logger.warning("Woolworths: no __NEXT_DATA__ found in HTML (len=%d)", len(resp.text))
            logger.debug("Woolworths HTML snippet: %s", resp.text[:500])
            return []

        try:
            data = _json.loads(match.group(1))
        except Exception as exc:
            logger.error("Woolworths: failed to parse __NEXT_DATA__ JSON: %s", exc)
            return []

        # Navigate the Next.js page props to find product list
        page_props = data.get("props", {}).get("pageProps", {})

        # Try multiple possible locations for products in the page props
        products_raw = []

        # Location 1: searchResults.Products bundles
        search_results = page_props.get("searchResults", {}) or {}
        for bundle in search_results.get("Products", []):
            products_raw.extend(bundle.get("Products", []))

        # Location 2: products list directly
        if not products_raw:
            products_raw = page_props.get("products", []) or []

        # Location 3: search.products
        if not products_raw:
            search = page_props.get("search", {}) or {}
            for bundle in search.get("Products", []):
                products_raw.extend(bundle.get("Products", []))

        logger.info("Woolworths HTML: found %d raw products", len(products_raw))

        results = []
        for item in products_raw:
            parsed = _parse_nextdata_product(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break

        return results

    async def _search_via_api(self, query: str, limit: int) -> list[SearchResult]:
        """POST to Woolworths internal API directly (works on residential IPs)."""
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
            headers=API_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        products = []
        for bundle in data.get("Products", []):
            products.extend(bundle.get("Products", []))
        return [_parse_product(p) for p in products if p.get("Stockcode")]

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        client = await self._get_client()
        target = f"https://www.woolworths.com.au/api/v3/ui/schemaorg/product/{external_id}"
        if _use_scraperapi():
            resp = await client.get(_scraperapi_url(target))
        else:
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
        image = data.get("image", f"https://cdn0.woolworths.media/content/wowproductimages/large/{external_id}.jpg")

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
            unit=None,
        )
