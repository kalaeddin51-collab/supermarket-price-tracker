"""
Aldi Australia scraper.

Aldi's website is a Nuxt 3 SSR app (Spryker commerce backend).
All product data for a given page is embedded server-side inside:
    <script id="__NUXT_DATA__" type="application/json">…</script>

The JSON uses the @nuxt/devalue flat-array format where integer values
are cross-references to other positions in the array.  Rather than
implementing a full devalue deserialiser we walk the entire structure
recursively and collect any object that has the product-shaped keys
(name + price sub-object).  This is robust to Nuxt/devalue version
changes because we rely on shape, not position.

Search endpoint:
    GET https://www.aldi.com.au/products?q={query}

Pricing is national / uniform — Aldi has no store-specific variants.
"""
import json
import re
import httpx

from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

BASE_URL = "https://www.aldi.com.au"
SEARCH_URL = f"{BASE_URL}/products"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": BASE_URL + "/",
}

# ── Nuxt devalue recursive scanner ──────────────────────────────────────────

def _walk(obj, seen: set | None = None, depth: int = 0) -> list[dict]:
    """
    Recursively walk any JSON value (list / dict / scalar) and return
    every dict that looks like an Aldi product record.

    The devalue flat array contains many dicts; we identify products by
    requiring BOTH a non-empty 'name' string AND a 'price' sub-object
    that has at least one displayable price key.
    """
    if depth > 40:
        return []
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return []
    seen.add(obj_id)

    found: list[dict] = []

    if isinstance(obj, dict):
        if _is_product(obj):
            found.append(obj)
        else:
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    found.extend(_walk(v, seen, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                found.extend(_walk(item, seen, depth + 1))

    return found


def _is_product(obj: dict) -> bool:
    """Return True if dict looks like an Aldi product node."""
    if not isinstance(obj.get("name"), str) or not obj["name"]:
        return False
    price = obj.get("price")
    if not isinstance(price, dict):
        return False
    # Must have at least one readable price field
    return bool(
        price.get("amountRelevantDisplay")
        or price.get("amount") is not None
    )


def _parse_price(price: dict) -> tuple[float | None, float | None, bool]:
    """Return (price, was_price, on_special)."""
    raw_price: float | None = None

    # Prefer the human-readable display price (already in dollars)
    display = price.get("amountRelevantDisplay") or ""
    m = re.search(r"[\d]+\.[\d]+|[\d]+", display.replace(",", ""))
    if m:
        raw_price = float(m.group())
    elif price.get("amount") is not None:
        # amount is in cents
        try:
            raw_price = float(price["amount"]) / 100
        except (TypeError, ValueError):
            pass

    # Was-price (sale)
    was_price: float | None = None
    was_display = price.get("wasPriceDisplay") or price.get("pseudoPrice") or ""
    if was_display:
        m2 = re.search(r"[\d]+\.[\d]+|[\d]+", str(was_display).replace(",", ""))
        if m2:
            was_price = float(m2.group())

    on_special = (
        was_price is not None
        and raw_price is not None
        and was_price > raw_price
    )
    if not on_special:
        was_price = None

    return raw_price, was_price, on_special


def _parse_unit(product: dict) -> str | None:
    """Extract comparison / unit label from product."""
    price = product.get("price", {})
    comparison = price.get("comparisonDisplay") or price.get("unitPriceDisplay") or ""
    if comparison:
        # e.g. "$2.20 per 100g" → "100g"
        m = re.search(r"per\s+(.+)", comparison, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    # Fall back to sellingSize
    return product.get("sellingSize") or product.get("quantityUnit") or None


def _parse_image(product: dict) -> str | None:
    """Best-effort image URL from product assets."""
    assets = product.get("assets") or []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        # Aldi CDN pattern seen on the live site
        for key in ("url", "externalUrl", "src"):
            val = asset.get(key)
            if val and isinstance(val, str) and val.startswith("http"):
                return val
        # UUID-style asset id → construct CDN URL
        asset_id = asset.get("id") or asset.get("assetId")
        if asset_id and isinstance(asset_id, str) and len(asset_id) > 8:
            return (
                f"https://www.aldi.com.au/fileadmin/_processed_/"
                f"{asset_id[:1]}/{asset_id[1:3]}/csm_{asset_id}.jpg"
            )
    return None


def _build_url(product: dict) -> str:
    slug = product.get("urlSlugText") or product.get("url") or ""
    if slug.startswith("http"):
        return slug
    if slug.startswith("/"):
        return BASE_URL + slug
    if slug:
        # Try to find a category slug
        cats = product.get("categories") or []
        cat_slug = ""
        if cats and isinstance(cats[0], dict):
            cat_slug = cats[0].get("urlSlugText") or ""
        if cat_slug:
            return f"{BASE_URL}/products/{cat_slug}/{slug}"
        return f"{BASE_URL}/products/{slug}"
    return BASE_URL


def _product_to_result(p: dict) -> SearchResult | None:
    name = (p.get("name") or "").strip()
    if not name:
        return None

    price_obj = p.get("price") or {}
    price, was_price, on_special = _parse_price(price_obj)

    sku = str(p.get("sku") or p.get("abstractSku") or p.get("id") or "")
    url = _build_url(p)
    category = None
    cats = p.get("categories") or []
    if cats and isinstance(cats[0], dict):
        category = cats[0].get("name") or cats[0].get("label")

    return SearchResult(
        external_id=sku or url,
        name=name,
        price=price,
        was_price=was_price,
        on_special=on_special,
        url=url,
        store="aldi",
        image_url=_parse_image(p),
        category=category,
        unit=_parse_unit(p),
    )


# ── Scraper class ────────────────────────────────────────────────────────────

class AldiScraper(BaseScraper):
    """
    Scraper for Aldi Australia (national pricing, single store entry).

    Aldi does not expose a public JSON API.  We fetch the SSR-rendered
    search page and extract the embedded __NUXT_DATA__ payload.
    """

    store_slug = "aldi"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── internal helpers ──────────────────────────────────────────────────

    async def _fetch_page(self, query: str) -> list[dict]:
        """Fetch search page HTML and extract raw product dicts."""
        from app.config import get_scraperapi_key
        client = await self._get_client()

        scraperapi_key = get_scraperapi_key()
        if scraperapi_key:
            target = (
                f"https://api.scraperapi.com/?api_key={scraperapi_key}"
                f"&url={SEARCH_URL}%3Fq%3D{query.replace(' ', '+')}"
                f"&render=false"
            )
            resp = await client.get(target, timeout=30)
        else:
            resp = await client.get(SEARCH_URL, params={"q": query}, timeout=20)

        if resp.status_code == 403:
            raise RuntimeError(
                "Aldi is blocking this server's IP. "
                "Add a ScraperAPI key in Settings to enable Aldi results."
            )
        resp.raise_for_status()
        return self._extract_from_html(resp.text)

    @staticmethod
    def _extract_from_html(html: str) -> list[dict]:
        """Parse __NUXT_DATA__ from page HTML and return product dicts."""
        m = re.search(
            r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            return []

        # Resolve devalue references: integers in the flat array that point
        # to other indices.  We dereference the entire tree so _walk sees
        # plain Python objects.
        if isinstance(data, list):
            data = _resolve_devalue(data)

        return _walk(data)

    # ── public interface ──────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        try:
            raw = await self._fetch_page(query)
        except Exception:
            return []

        # Aldi's search returns category-level matches (e.g. searching "eggs"
        # returns all of "Dairy, Eggs & Fridge").  Keep only products whose
        # name contains at least one query token so we drop irrelevant hits.
        query_tokens = {t.lower() for t in query.split() if len(t) > 2}

        results: list[SearchResult] = []
        seen: set[str] = set()
        for p in raw:
            r = _product_to_result(p)
            if not r:
                continue
            if query_tokens:
                name_lower = r.name.lower()
                if not any(tok in name_lower for tok in query_tokens):
                    continue
            if r.external_id not in seen:
                seen.add(r.external_id)
                results.append(r)
            if len(results) >= limit:
                break
        return results

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        """
        Re-scrape the product detail page to get the current price.
        Aldi has no JSON product API so we re-use the search approach.
        """
        from app.config import get_scraperapi_key
        client = await self._get_client()
        scraperapi_key = get_scraperapi_key()

        # Fetch the product detail page
        if scraperapi_key:
            target = (
                f"https://api.scraperapi.com/?api_key={scraperapi_key}"
                f"&url={url}&render=false"
            )
            resp = await client.get(target, timeout=30)
        else:
            resp = await client.get(url, timeout=20)

        error = resp.status_code != 200
        products = self._extract_from_html(resp.text) if not error else []

        # Find the matching product (by sku or the first one)
        match = None
        for p in products:
            if str(p.get("sku", "")) == external_id or str(p.get("abstractSku", "")) == external_id:
                match = p
                break
        if not match and products:
            match = products[0]

        if not match:
            return PriceResult(
                external_id=external_id,
                name="",
                price=None,
                url=url,
                store="aldi",
                error=True,
                error_message="Product not found on page",
            )

        price_obj = match.get("price") or {}
        price, was_price, on_special = _parse_price(price_obj)
        return PriceResult(
            external_id=external_id,
            name=(match.get("name") or "").strip(),
            price=price,
            was_price=was_price,
            on_special=on_special,
            url=url,
            store="aldi",
            in_stock=True,
            image_url=_parse_image(match),
            unit=_parse_unit(match),
            category=None,
        )


# ── devalue resolver ────────────────────────────────────────────────────────

def _resolve_devalue(arr: list) -> object:
    """
    Resolve a @nuxt/devalue flat array into a standard Python object tree.

    In the devalue format every element of the array is a value; when a
    value (in an object or array) is an *integer* it is a back-reference
    to another index in the same flat array.  Strings, booleans, None
    and floats are stored verbatim.

    We materialise the whole tree so that the generic _walk() scanner
    can look for product-shaped dicts without caring about the encoding.
    """
    cache: dict[int, object] = {}

    def resolve(idx: int, depth: int = 0) -> object:
        if depth > 60 or idx >= len(arr):
            return None
        if idx in cache:
            return cache[idx]

        val = arr[idx]

        # Scalar – store & return as-is
        if val is None or isinstance(val, (bool, str, float)):
            cache[idx] = val
            return val

        # Integer – in devalue an int stored *in the array* is itself
        # a reference; but an int stored as a *dict value or list element*
        # is a reference.  Here we're at the array level so treat as-is.
        if isinstance(val, int):
            cache[idx] = val
            return val

        # Dict – resolve each value that is an integer ref
        if isinstance(val, dict):
            result = {}
            cache[idx] = result  # set early to break cycles
            for k, v in val.items():
                result[k] = resolve(v, depth + 1) if isinstance(v, int) else _deep_resolve(v, arr, depth + 1)
            return result

        # List – same treatment
        if isinstance(val, list):
            result2: list = []
            cache[idx] = result2
            for item in val:
                result2.append(
                    resolve(item, depth + 1) if isinstance(item, int)
                    else _deep_resolve(item, arr, depth + 1)
                )
            return result2

        cache[idx] = val
        return val

    def _deep_resolve(obj: object, flat: list, depth: int) -> object:
        """Resolve integer refs inside nested dicts/lists."""
        if depth > 60:
            return obj
        if isinstance(obj, int):
            return resolve(obj, depth + 1)
        if isinstance(obj, dict):
            return {k: _deep_resolve(v, flat, depth + 1) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_deep_resolve(item, flat, depth + 1) for item in obj]
        return obj

    # The Nuxt payload wraps the devalue array; the top-level element
    # (index 0) is usually the root data node.
    if not arr:
        return {}
    return resolve(0)
