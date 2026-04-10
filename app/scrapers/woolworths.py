"""
Woolworths scraper — mobile app API approach.

The Woolworths mobile app uses the same backend API (/apis/ui/Search/products)
but with iOS/Android app headers. Mobile apps bypass Akamai's JavaScript
challenge requirement since native apps don't run browser JavaScript.

Falls back to direct POST (no proxy) if no ScraperAPI key.
"""
import json as _json
import logging
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings, get_scraperapi_key

logger = logging.getLogger(__name__)

WOW_HOME = "https://www.woolworths.com.au"
SEARCH_API = f"{WOW_HOME}/apis/ui/Search/products"
DETAIL_API = f"{WOW_HOME}/api/v3/ui/schemaorg/product"

# Mobile app headers — bypasses Akamai web bot detection
MOBILE_HEADERS = {
    "User-Agent": "Woolworths/10.6.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU",
    "Content-Type": "application/json",
    "Origin": WOW_HOME,
    "Referer": f"{WOW_HOME}/",
    "x-requested-with": "au.com.woolworths",
    "wow-app-info": "platform=ios,version=10.6.0",
}

# Also try desktop browser headers as fallback
BROWSER_HEADERS = {
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
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "request-id": "|abc123.def456",
}

# Try to import curl_cffi for Chrome TLS fingerprint impersonation
try:
    from curl_cffi.requests import AsyncSession as CurlSession
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False
    logger.warning("curl_cffi not available")


def _scraperapi_proxy_url() -> str:
    key = get_scraperapi_key()
    return f"http://scraperapi.country_code=au:{key}@proxy-server.scraperapi.com:8001"


def _scraperapi_url(target_url: str) -> str:
    """URL rewriting mode for simple GET requests."""
    return (
        f"http://api.scraperapi.com"
        f"?api_key={get_scraperapi_key()}"
        f"&url={urllib.parse.quote(target_url, safe='')}"
        f"&country_code=au"
        f"&keep_headers=true"
    )


def _use_scraperapi() -> bool:
    return bool(get_scraperapi_key())


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
        self._httpx_client: httpx.AsyncClient | None = None

    async def _get_httpx_client(self) -> httpx.AsyncClient:
        if self._httpx_client is None or self._httpx_client.is_closed:
            self._httpx_client = httpx.AsyncClient(
                headers=MOBILE_HEADERS,
                timeout=60,
                follow_redirects=True,
            )
        return self._httpx_client

    async def close(self):
        if self._httpx_client and not self._httpx_client.is_closed:
            await self._httpx_client.aclose()

    def _build_payload(self, query: str, limit: int) -> dict:
        return {
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

    def _build_url(self) -> str:
        url = SEARCH_API
        if settings.woolworths_store_id:
            url += f"?store_id={settings.woolworths_store_id}"
        return url

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        url = self._build_url()
        payload = self._build_payload(query, limit)

        # Strategy 1: curl_cffi with mobile headers (bypasses Akamai JS challenge)
        if _HAS_CURL_CFFI:
            try:
                data = await self._post_with_curl(url, payload, MOBILE_HEADERS)
                products_raw = []
                for bundle in data.get("Products", []):
                    products_raw.extend(bundle.get("Products", []))
                if products_raw:
                    logger.info("Woolworths mobile API: %d products for %r", len(products_raw), query)
                    return [p for p in (_parse_product(x) for x in products_raw) if p]
                logger.info("Woolworths mobile API returned 0 — trying browser headers")
            except Exception as exc:
                logger.warning("Woolworths mobile headers failed (%s) — trying browser headers", exc)

            # Strategy 2: curl_cffi with browser headers
            try:
                data = await self._post_with_curl(url, payload, BROWSER_HEADERS)
                products_raw = []
                for bundle in data.get("Products", []):
                    products_raw.extend(bundle.get("Products", []))
                logger.info("Woolworths browser headers: %d products for %r", len(products_raw), query)
                return [p for p in (_parse_product(x) for x in products_raw) if p]
            except Exception as exc:
                logger.warning("Woolworths browser headers also failed: %s", exc)
                raise

        # Fallback: plain httpx (may be blocked)
        client = await self._get_httpx_client()
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        products_raw = []
        for bundle in data.get("Products", []):
            products_raw.extend(bundle.get("Products", []))
        return [p for p in (_parse_product(x) for x in products_raw) if p]

    async def _post_with_curl(self, url: str, payload: dict, headers: dict) -> dict:
        """POST using curl_cffi + ScraperAPI proxy."""
        proxies = None
        if _use_scraperapi():
            proxy_url = _scraperapi_proxy_url()
            proxies = {"https": proxy_url, "http": proxy_url}

        async with CurlSession(impersonate="chrome124") as session:
            resp = await session.post(
                url,
                json=payload,
                headers=headers,
                proxies=proxies,
                timeout=60,
                verify=False,
            )

        logger.info("Woolworths curl POST: status=%d len=%d headers_ua=%s",
                    resp.status_code, len(resp.text), headers.get("User-Agent", "")[:40])
        if resp.status_code != 200:
            logger.warning("Woolworths non-200 body: %s", resp.text[:300])
        resp.raise_for_status()
        return resp.json()

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        target = f"{DETAIL_API}/{external_id}"

        if _HAS_CURL_CFFI and _use_scraperapi():
            proxy_url = _scraperapi_proxy_url()
            proxies = {"https": proxy_url, "http": proxy_url}
            async with CurlSession(impersonate="chrome124") as session:
                resp = await session.get(target, headers=BROWSER_HEADERS,
                                         proxies=proxies, timeout=60, verify=False)
        else:
            client = await self._get_httpx_client()
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
