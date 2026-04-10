"""
Woolworths scraper — two strategies:

1. ScraperAPI mode: GET /_next/data/{BUILD_ID}/en-AU/shop/search/products.json
   This is a pure GET JSON endpoint embedded in their Next.js build, just like Coles.
   We first fetch any Woolworths page to extract the buildId, then query the data endpoint.

2. Direct API (no proxy): POST to internal /apis/ui/Search/products
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

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
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


def _parse_product_api(item: dict) -> SearchResult | None:
    """Parse a product from the internal POST API response."""
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


def _parse_product_nextjs(item: dict) -> SearchResult | None:
    """Parse a product from the Next.js data API response."""
    # Items can be nested: {"Products": [...]} or flat product dicts
    stockcode = str(item.get("Stockcode", "") or item.get("stockcode", ""))
    if not stockcode:
        return None
    name = item.get("Name", "") or item.get("name", "")
    price = item.get("Price") or item.get("price") or item.get("InstorePrice")
    cup_string = item.get("CupString") or item.get("cupString")
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


def _scraperapi_url(target_url: str, country: str = "au") -> str:
    """Wrap a target URL with ScraperAPI using Australian residential IPs."""
    return (
        f"http://api.scraperapi.com"
        f"?api_key={get_scraperapi_key()}"
        f"&url={urllib.parse.quote(target_url, safe='')}"
        f"&country_code={country}"
        f"&keep_headers=true"
    )


def _use_scraperapi() -> bool:
    return bool(get_scraperapi_key())


class WoolworthsScraper(BaseScraper):
    store_slug = "woolworths"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._build_id: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            proxy = settings.scraper_proxy or None
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=90,
                follow_redirects=True,
                proxy=proxy if not _use_scraperapi() else None,
            )
            if not _use_scraperapi():
                try:
                    await self._client.get(f"{WOW_HOME}/")
                except Exception:
                    pass
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get_build_id(self) -> str:
        """Fetch the current Next.js build ID from any Woolworths page."""
        if self._build_id:
            return self._build_id

        client = await self._get_client()
        # Use a lightweight page that doesn't require auth — the specials page
        probe_url = f"{WOW_HOME}/shop/specials/browse"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(probe_url))
        else:
            r = await client.get(probe_url)

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text,
            re.DOTALL,
        )
        if match:
            try:
                data = _json.loads(match.group(1))
                self._build_id = data.get("buildId")
            except Exception:
                pass

        if not self._build_id:
            # Fallback: extract buildId from /_next/static chunk path
            bm = re.search(r'/_next/static/([a-zA-Z0-9_-]+)/_buildManifest', r.text)
            if bm:
                self._build_id = bm.group(1)

        if not self._build_id:
            raise RuntimeError(f"Could not determine Woolworths buildId (status={r.status_code})")

        logger.info("Woolworths buildId: %s", self._build_id)
        return self._build_id

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        if _use_scraperapi():
            return await self._search_via_nextjs(query, limit)
        return await self._search_via_api(query, limit)

    async def _search_via_nextjs(self, query: str, limit: int) -> list[SearchResult]:
        """GET Woolworths Next.js data API — pure JSON, works through ScraperAPI."""
        client = await self._get_client()
        build_id = await self._get_build_id()

        # Woolworths Next.js data endpoint for search
        target = (
            f"{WOW_HOME}/_next/data/{build_id}/en/shop/search/products.json"
            f"?searchTerm={urllib.parse.quote(query)}"
        )
        logger.info("Woolworths Next.js search: %s", target)

        if _use_scraperapi():
            r = await client.get(_scraperapi_url(target))
        else:
            r = await client.get(target)

        logger.info("Woolworths Next.js resp: status=%d len=%d", r.status_code, len(r.text))

        if r.status_code == 404:
            # buildId may have changed — reset and try once more
            self._build_id = None
            build_id = await self._get_build_id()
            target = (
                f"{WOW_HOME}/_next/data/{build_id}/en/shop/search/products.json"
                f"?searchTerm={urllib.parse.quote(query)}"
            )
            if _use_scraperapi():
                r = await client.get(_scraperapi_url(target))
            else:
                r = await client.get(target)

        r.raise_for_status()

        try:
            data = r.json()
        except Exception:
            logger.warning("Woolworths Next.js: non-JSON response: %s", r.text[:300])
            return []

        page_props = data.get("pageProps", {}) or {}

        # Navigate the page props for product bundles
        products_raw = []
        search_results = page_props.get("searchResults") or page_props.get("search") or {}
        if isinstance(search_results, dict):
            for bundle in search_results.get("Products", []):
                if isinstance(bundle, dict):
                    products_raw.extend(bundle.get("Products", []))

        # Fallback: flat products list
        if not products_raw:
            products_raw = page_props.get("products") or page_props.get("Products") or []

        logger.info("Woolworths Next.js: found %d raw products for %r", len(products_raw), query)

        results = []
        for item in products_raw:
            parsed = _parse_product_nextjs(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        return results

    async def _search_via_api(self, query: str, limit: int) -> list[SearchResult]:
        """POST to Woolworths internal API (only works on non-datacenter IPs)."""
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
        return [p for p in (_parse_product_api(x) for x in products) if p]

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        client = await self._get_client()
        target = f"{WOW_HOME}/api/v3/ui/schemaorg/product/{external_id}"
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
