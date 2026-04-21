"""
Woolworths scraper.

Woolworths blocks all cloud-datacenter IPs (Railway, AWS, GCP) via Akamai —
both the JSON search API and the HTML search page are affected.

── Option 1 (FREE, recommended): ScraperAPI residential proxy ──────────────
  Sign up at https://scraperapi.com (1 000 free credits/month).
  Set  SCRAPERAPI_KEY  in Railway.  This scraper fetches the Woolworths HTML
  search page through ScraperAPI's residential pool, then parses the embedded
  __NEXT_DATA__ JSON — no JSON API needed.

── Option 2 (FREE): Cloudflare Worker proxy ────────────────────────────────
  Cloudflare Workers IPs are ALSO blocked by Akamai for Woolworths search,
  so this option no longer works.  Kept as legacy fallback only.

── Option 3 (dev / residential only): direct request ───────────────────────
  Works on home broadband but not on any cloud provider.
"""
import json
import logging
import os
import re
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings, get_scraperapi_key

logger = logging.getLogger(__name__)

WOW_HOME    = "https://www.woolworths.com.au"
SEARCH_API  = f"{WOW_HOME}/apis/ui/Search/products"
SEARCH_HTML = f"{WOW_HOME}/shop/search/products"

# Optional Cloudflare Worker proxy (legacy — Akamai now blocks CF IPs too).
PROXY_URL   = os.environ.get("WOOLWORTHS_PROXY_URL", "").rstrip("/")
PROXY_TOKEN = os.environ.get("WOOLWORTHS_PROXY_TOKEN", "")

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

HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "Upgrade-Insecure-Requests": "1",
}


# ── HTML / __NEXT_DATA__ parsing (mirrors the Cloudflare Worker logic) ────────

def _extract_from_html(html: str, limit: int) -> list[dict]:
    """Parse Woolworths search HTML and return raw product dicts."""
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return []
    try:
        next_data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []
    return _extract_products(next_data, limit)


def _extract_products(next_data: dict, limit: int) -> list[dict]:
    """Walk __NEXT_DATA__ looking for product arrays."""
    candidates = [
        _deep_get(next_data, "props", "pageProps", "searchResults", "Products"),
        _deep_get(next_data, "props", "pageProps", "initialState", "search", "products", "items"),
        _deep_get(next_data, "props", "pageProps", "products"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        flat = candidate if isinstance(candidate, list) else list(candidate.values())
        mapped = [_map_product(p) for p in flat[:limit]]
        mapped = [p for p in mapped if p]
        if mapped:
            return mapped

    # Deep-search fallback: walk the entire tree for product-shaped arrays
    found: list[dict] = []
    _deep_search(next_data, found, limit)
    return found[:limit]


def _deep_get(obj, *keys):
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _map_product(p: dict) -> dict | None:
    """Normalise a raw product node from __NEXT_DATA__."""
    # Handle bundled shape {Products: [...]}
    item = (p.get("Products") or [None])[0] if isinstance(p.get("Products"), list) else p
    if not item or not item.get("Name"):
        return None
    return {
        "Stockcode":   str(item.get("Stockcode") or item.get("stockcode") or ""),
        "Name":        item.get("Name")        or item.get("name")        or "",
        "Price":       item.get("Price")        or item.get("price")        or item.get("InstorePrice"),
        "CupString":   item.get("CupString")    or item.get("cupString"),
        "IsOnSpecial": item.get("IsOnSpecial")  or item.get("isOnSpecial")  or False,
        "WasPrice":    item.get("WasPrice")      or item.get("wasPrice"),
        "ImageUrl":    item.get("MediumImageFile") or item.get("mediumImageFile"),
    }


def _deep_search(obj, found: list, limit: int, depth: int = 0):
    if depth > 8 or len(found) >= limit:
        return
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and obj[0].get("Name") and obj[0].get("Price") is not None:
            for item in obj:
                mapped = _map_product(item)
                if mapped and mapped.get("Name"):
                    found.append(mapped)
                if len(found) >= limit:
                    return
        else:
            for item in obj:
                _deep_search(item, found, limit, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            _deep_search(v, found, limit, depth + 1)


# ── Product parsing (raw dict → SearchResult) ─────────────────────────────────

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


# ── Scraper class ─────────────────────────────────────────────────────────────

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
        client = await self._get_client()

        # ── 1. ScraperAPI — HTML page + __NEXT_DATA__ parsing (recommended) ───
        scraperapi_key = get_scraperapi_key()
        if scraperapi_key:
            target_url = (
                f"{SEARCH_HTML}?searchTerm={urllib.parse.quote(query)}"
                f"&hideUnavailable=true&pageNumber=1"
            )
            scraper_url = (
                f"https://api.scraperapi.com/?api_key={scraperapi_key}"
                f"&url={urllib.parse.quote(target_url, safe='')}"
                f"&render=true"
                f"&country_code=au"
            )
            try:
                resp = await client.get(scraper_url, headers=HTML_HEADERS, timeout=45)
                if resp.status_code == 200:
                    raw = _extract_from_html(resp.text, limit)
                    products = [p for p in (_parse_product(x) for x in raw) if p]
                    if products:
                        logger.info("Woolworths (ScraperAPI): %d products for %r", len(products), query)
                        return products
                    logger.warning("Woolworths (ScraperAPI): got HTML but no products for %r", query)
                else:
                    logger.warning("Woolworths (ScraperAPI): HTTP %s for %r", resp.status_code, query)
            except Exception as exc:
                logger.error("Woolworths (ScraperAPI) failed: %s", exc)
            return []

        # ── 2. Cloudflare Worker proxy (legacy — may not work) ────────────────
        if PROXY_URL:
            params = {"q": query, "limit": str(limit)}
            if PROXY_TOKEN:
                params["token"] = PROXY_TOKEN
            try:
                resp = await client.get(PROXY_URL, params=params, timeout=25)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    logger.warning("Woolworths proxy error: %s", data)
                    return []
            except Exception as exc:
                logger.error("Woolworths proxy failed: %s", exc)
                return []

            products_raw: list[dict] = []
            for bundle in data.get("Products", []):
                products_raw.extend(bundle.get("Products", []))
            logger.info("Woolworths (proxy): %d products for %r", len(products_raw), query)
            return [p for p in (_parse_product(x) for x in products_raw) if p]

        # ── 3. Direct request (residential / local dev only) ──────────────────
        try:
            r = await client.get(f"{WOW_HOME}/")
            if "Access Denied" in r.text or r.status_code == 403:
                logger.warning(
                    "Woolworths: Akamai IP block. Set SCRAPERAPI_KEY in Railway to enable."
                )
                return []
        except httpx.HTTPError as exc:
            logger.error("Woolworths connection failed: %s", exc)
            return []

        payload = {
            "Filters": [], "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={query}",
            "PageNumber": 1, "PageSize": limit,
            "SearchTerm": query, "SortType": "TraderRelevance",
            "token": "", "gpBoost": 0, "CategoryVersion": "v2",
        }
        resp = await client.post(SEARCH_API, json=payload)
        if resp.status_code in (403, 429, 503):
            logger.warning("Woolworths: blocked (%s). Set SCRAPERAPI_KEY in Railway.", resp.status_code)
            return []
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
