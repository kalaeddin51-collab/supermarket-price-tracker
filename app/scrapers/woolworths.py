"""
Woolworths scraper — Akamai bypass via Chrome TLS impersonation.

Strategy:
  • Uses curl_cffi which impersonates Chrome's TLS fingerprint (JA3/JA4).
  • Combined with ScraperAPI residential AU proxies, this fools Akamai.
  • If curl_cffi unavailable, falls back to httpx (may be blocked).

Endpoint: POST https://www.woolworths.com.au/apis/ui/Search/products
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
    logger.info("curl_cffi available — Woolworths will use Chrome TLS impersonation")
except ImportError:
    _HAS_CURL_CFFI = False
    logger.warning("curl_cffi not available — Woolworths may be blocked by Akamai")


def _scraperapi_proxy_url() -> str:
    """Return ScraperAPI as an HTTPS proxy URL for curl_cffi."""
    key = get_scraperapi_key()
    return f"http://scraperapi.country_code=au:{key}@proxy-server.scraperapi.com:8001"


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
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Fallback httpx client (used only when curl_cffi is unavailable)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=BROWSER_HEADERS,
                timeout=60,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
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
        params = {}
        if settings.woolworths_store_id:
            params["store_id"] = settings.woolworths_store_id

        url = SEARCH_API
        if params:
            url += "?" + urllib.parse.urlencode(params)

        if _HAS_CURL_CFFI:
            data = await self._post_curl(url, payload)
        else:
            data = await self._post_httpx(url, payload)

        products_raw = []
        for bundle in data.get("Products", []):
            products_raw.extend(bundle.get("Products", []))

        logger.info("Woolworths search: %d products for %r", len(products_raw), query)
        return [p for p in (_parse_product(x) for x in products_raw) if p]

    async def _post_curl(self, url: str, payload: dict) -> dict:
        """POST using curl_cffi with Chrome TLS fingerprint + ScraperAPI residential proxy."""
        proxies = None
        if _use_scraperapi():
            proxy_url = _scraperapi_proxy_url()
            proxies = {"https": proxy_url, "http": proxy_url}
            logger.info("Woolworths: curl_cffi POST via ScraperAPI proxy for %s", url[:60])
        else:
            logger.info("Woolworths: curl_cffi POST direct for %s", url[:60])

        async with CurlSession(impersonate="chrome124") as session:
            resp = await session.post(
                url,
                json=payload,
                headers=BROWSER_HEADERS,
                proxies=proxies,
                timeout=60,
                verify=False,  # ScraperAPI proxy uses its own cert
            )
        logger.info("Woolworths curl_cffi response: status=%d len=%d", resp.status_code, len(resp.text))
        if resp.status_code != 200:
            logger.warning("Woolworths non-200 body: %s", resp.text[:400])
        resp.raise_for_status()
        return resp.json()

    async def _post_httpx(self, url: str, payload: dict) -> dict:
        """Fallback: POST using httpx (may be blocked by Akamai)."""
        client = await self._get_client()
        resp = await client.post(url, json=payload)
        logger.info("Woolworths httpx response: status=%d", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        target = f"{DETAIL_API}/{external_id}"

        if _HAS_CURL_CFFI:
            proxies = None
            if _use_scraperapi():
                proxy_url = _scraperapi_proxy_url()
                proxies = {"https": proxy_url, "http": proxy_url}
            async with CurlSession(impersonate="chrome124") as session:
                resp = await session.get(
                    target,
                    headers=BROWSER_HEADERS,
                    proxies=proxies,
                    timeout=60,
                    verify=False,
                )
        else:
            client = await self._get_client()
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
