"""
Woolworths scraper — Next.js /_next/data/ JSON endpoint (mirrors Coles approach).

Woolworths uses Next.js. Their search page /shop/search/products has a
corresponding JSON data endpoint at:
  GET /_next/data/{BUILD_ID}/shop/search/products.json?searchTerm={q}

This is a pure GET JSON endpoint — no session cookies, no bot check.
We fetch the buildId from a lightweight probe page first.

Fallback (no ScraperAPI): POST to internal /apis/ui/Search/products directly.
"""
import json as _json
import logging
import re
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings, get_scraperapi_key

logger = logging.getLogger(__name__)

WOW_HOME = "https://www.woolworths.com.au"
SEARCH_API = f"{WOW_HOME}/apis/ui/Search/products"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-AU,en;q=0.9",
}


def _scraperapi_url(target_url: str) -> str:
    """GET-based URL rewriting — works for any GET endpoint."""
    return (
        f"http://api.scraperapi.com"
        f"?api_key={get_scraperapi_key()}"
        f"&url={urllib.parse.quote(target_url, safe='')}"
        f"&country_code=au"
    )


def _use_scraperapi() -> bool:
    return bool(get_scraperapi_key())


def _parse_product(item: dict) -> SearchResult | None:
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


class WoolworthsScraper(BaseScraper):
    store_slug = "woolworths"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._build_id: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=60,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get_build_id(self) -> str:
        """Extract Next.js buildId from a lightweight Woolworths page."""
        if self._build_id:
            return self._build_id

        client = await self._get_client()

        # Use a non-existent API path — returns a Next.js 404 page with __NEXT_DATA__
        # This is the same trick used for Coles and doesn't trigger Akamai
        probe_url = f"{WOW_HOME}/api/__build_probe"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(probe_url))
        else:
            r = await client.get(probe_url)

        logger.info("Woolworths build probe: status=%d len=%d", r.status_code, len(r.text))

        # Try __NEXT_DATA__ JSON block
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text, re.DOTALL
        )
        if match:
            try:
                data = _json.loads(match.group(1))
                self._build_id = data.get("buildId")
            except Exception:
                pass

        # Fallback: extract from _next/static chunk path
        if not self._build_id:
            bm = re.search(r'/_next/static/([a-zA-Z0-9_-]+)/_buildManifest', r.text)
            if bm:
                self._build_id = bm.group(1)

        if not self._build_id:
            logger.warning("Woolworths: could not find buildId in probe (len=%d), snippet: %s",
                           len(r.text), r.text[:200])
            raise RuntimeError("Could not determine Woolworths Next.js buildId")

        logger.info("Woolworths buildId: %s", self._build_id)
        return self._build_id

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        if _use_scraperapi():
            return await self._search_nextjs(query, limit)
        return await self._search_direct_api(query, limit)

    async def _search_nextjs(self, query: str, limit: int) -> list[SearchResult]:
        """GET Next.js data endpoint through ScraperAPI — pure JSON, no bot check."""
        client = await self._get_client()
        build_id = await self._get_build_id()

        target = (
            f"{WOW_HOME}/_next/data/{build_id}/shop/search/products.json"
            f"?searchTerm={urllib.parse.quote(query)}"
        )
        logger.info("Woolworths Next.js GET: %s", target)
        r = await client.get(_scraperapi_url(target))
        logger.info("Woolworths Next.js resp: status=%d len=%d", r.status_code, len(r.text))

        if r.status_code == 404:
            # buildId stale — reset and retry once
            logger.info("Woolworths: buildId stale, refreshing")
            self._build_id = None
            build_id = await self._get_build_id()
            target = (
                f"{WOW_HOME}/_next/data/{build_id}/shop/search/products.json"
                f"?searchTerm={urllib.parse.quote(query)}"
            )
            r = await client.get(_scraperapi_url(target))
            logger.info("Woolworths Next.js retry: status=%d len=%d", r.status_code, len(r.text))

        r.raise_for_status()

        try:
            data = r.json()
        except Exception:
            logger.warning("Woolworths Next.js non-JSON: %s", r.text[:300])
            return []

        page_props = data.get("pageProps", {}) or {}

        # Search for products in the page props
        products_raw = []

        # Try searchResults.Products bundles
        sr = page_props.get("searchResults") or page_props.get("search") or {}
        if isinstance(sr, dict):
            for bundle in sr.get("Products", []):
                if isinstance(bundle, dict):
                    products_raw.extend(bundle.get("Products", []))

        # Try direct products key
        if not products_raw:
            for key in ("products", "Products", "items"):
                if page_props.get(key):
                    products_raw = page_props[key]
                    break

        logger.info("Woolworths Next.js: %d raw products for %r", len(products_raw), query)
        if not products_raw:
            logger.debug("Woolworths page_props keys: %s", list(page_props.keys()))

        results = []
        for item in products_raw:
            parsed = _parse_product(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        return results

    async def _search_direct_api(self, query: str, limit: int) -> list[SearchResult]:
        """POST to internal API directly (only works on residential IPs, not cloud)."""
        client = await self._get_client()
        payload = {
            "Filters": [], "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={query}",
            "PageNumber": 1, "PageSize": limit,
            "SearchTerm": query, "SortType": "TraderRelevance",
        }
        resp = await client.post(
            SEARCH_API, json=payload,
            headers={**HEADERS, "Content-Type": "application/json",
                     "Origin": WOW_HOME, "request-id": "|abc123.def456"},
        )
        resp.raise_for_status()
        data = resp.json()
        products_raw = []
        for bundle in data.get("Products", []):
            products_raw.extend(bundle.get("Products", []))
        return [p for p in (_parse_product(x) for x in products_raw) if p]

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        client = await self._get_client()
        target = f"{WOW_HOME}/api/v3/ui/schemaorg/product/{external_id}"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(target))
        else:
            r = await client.get(target)
        r.raise_for_status()
        data = r.json()

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
            external_id=external_id, name=name,
            price=float(price) if price is not None else None,
            was_price=float(was_price) if was_price is not None else None,
            url=url, store=self.store_slug,
            in_stock=in_stock, on_special=on_special,
            image_url=image, unit=None,
        )
