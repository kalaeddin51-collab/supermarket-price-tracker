"""
Costco Australia scraper.

Costco Australia (costco.com.au) uses SAP Commerce Cloud (Hybris).
The frontend is an Angular SPA — server-rendered HTML contains no product data.
Instead we call the Hybris autocomplete JSON endpoint, which returns full
product details without authentication.

Search endpoint:
    GET https://www.costco.com.au/search/autocomplete/SearchBox
        ?term={query}&max={limit}

Price refresh (fetch_price):
    Same endpoint, searching by a short keyword derived from the product URL slug,
    then matching on the stored product code.

Pricing is uniform nationally — Costco operates a single Australian online store.
"""
import re
import httpx

from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

BASE_URL = "https://www.costco.com.au"
AUTOCOMPLETE_URL = f"{BASE_URL}/search/autocomplete/SearchBox"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer":         BASE_URL + "/",
}


def _product_url(relative: str) -> str:
    if relative.startswith("http"):
        return relative
    return BASE_URL + relative


def _image_url(images: list) -> str | None:
    """Return the best available image URL from the Hybris images list."""
    # Prefer 'product' format, fall back to 'thumbnail'
    for fmt in ("product", "thumbnail", "zoom"):
        for img in images:
            if isinstance(img, dict) and img.get("format") == fmt:
                url = img.get("url", "")
                if url:
                    return _product_url(url)
    # Fallback: first image with any URL
    for img in images:
        if isinstance(img, dict):
            url = img.get("url", "")
            if url:
                return _product_url(url)
    return None


def _parse_price(product: dict) -> tuple[float | None, float | None, bool]:
    """Return (current_price, was_price, on_special).

    Costco Hybris fields:
      price        — current selling price (may be None for warehouse-only items)
      basePrice    — RRP / regular price
      discountPrice — discounted price when a promotion is active
    """
    price_obj = product.get("price") or {}
    base_obj  = product.get("basePrice") or {}
    disc_obj  = product.get("discountPrice") or {}

    current: float | None = None
    if isinstance(price_obj, dict) and price_obj.get("value") is not None:
        try:
            current = float(price_obj["value"])
        except (TypeError, ValueError):
            pass

    if current is None and isinstance(base_obj, dict) and base_obj.get("value") is not None:
        try:
            current = float(base_obj["value"])
        except (TypeError, ValueError):
            pass

    # Was-price: use basePrice as was-price when discountPrice is the active price
    was_price: float | None = None
    if isinstance(disc_obj, dict) and disc_obj.get("value") is not None:
        try:
            disc_val = float(disc_obj["value"])
            base_val = float(base_obj.get("value", 0) or 0)
            if base_val and disc_val < base_val:
                was_price = base_val
                current   = disc_val
        except (TypeError, ValueError):
            pass

    on_special = was_price is not None and current is not None and was_price > current
    if not on_special:
        was_price = None

    return current, was_price, on_special


def _parse_unit(product: dict) -> str | None:
    """Extract per-unit price string if available."""
    if not product.get("hasPricePerUnit"):
        return None
    ppu = product.get("pricePerUnit") or {}
    if isinstance(ppu, dict):
        return ppu.get("formattedValue") or None
    return None


def _parse_in_stock(product: dict) -> bool:
    stock = product.get("stock") or {}
    status = (stock.get("stockLevelStatus") or {}).get("code", "inStock")
    return status != "outOfStock"


def _code_from_url(url: str) -> str:
    """Extract the Costco product code from a URL like /c/name/p/33912."""
    m = re.search(r"/p/(\d+)", url)
    return m.group(1) if m else ""


def _search_term_from_url(url: str) -> str:
    """Derive a short search keyword from a product URL slug."""
    # URL pattern: /c/Product-Name-With-Hyphens/p/33912
    m = re.search(r"/c/([^/]+)/p/", url)
    if not m:
        return ""
    slug = m.group(1).replace("-", " ")
    # Use first 3–4 meaningful words as the search term
    words = [w for w in slug.split() if len(w) > 2]
    return " ".join(words[:4])


def _hit_to_search_result(p: dict) -> SearchResult | None:
    name = (p.get("name") or "").strip()
    rel_url = p.get("url") or ""
    code = p.get("code") or _code_from_url(rel_url)
    if not name or not code:
        return None

    price, was_price, on_special = _parse_price(p)
    images = p.get("images") or []
    category: str | None = None
    cats = p.get("categories") or p.get("firstCategoryNameList") or []
    if cats and isinstance(cats[0], dict):
        category = cats[0].get("name")
    elif cats and isinstance(cats[0], str):
        category = cats[0]

    return SearchResult(
        external_id=str(code),
        name=name,
        price=price,
        was_price=was_price,
        on_special=on_special,
        url=_product_url(rel_url),
        store="costco",
        image_url=_image_url(images),
        category=category,
        unit=_parse_unit(p),
    )


class CostcoScraper(BaseScraper):
    """
    Scraper for Costco Australia (costco.com.au).

    Uses the Hybris autocomplete JSON API — no HTML parsing needed.
    """

    store_slug = "costco"

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

    async def _autocomplete(self, term: str, max_results: int = 20) -> list[dict]:
        """Call the Hybris autocomplete endpoint and return raw product dicts."""
        client = await self._get_client()
        resp = await client.get(
            AUTOCOMPLETE_URL,
            params={"term": term, "max": max_results},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("products") or []

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        try:
            raw = await self._autocomplete(query, max_results=limit)
        except Exception:
            return []

        query_tokens = {t for t in query.lower().split() if len(t) > 2}
        results: list[SearchResult] = []
        seen: set[str] = set()

        for p in raw:
            r = _hit_to_search_result(p)
            if not r:
                continue
            # Filter: product name must contain at least one query token
            if query_tokens and not any(tok in r.name.lower() for tok in query_tokens):
                continue
            if r.external_id not in seen:
                seen.add(r.external_id)
                results.append(r)
            if len(results) >= limit:
                break

        return results

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        """
        Re-fetch the current price for a product by code.

        Strategy: derive a short search term from the stored URL slug,
        query autocomplete, find the product whose code matches external_id.
        """
        term = _search_term_from_url(url)
        if not term:
            # Fall back: use the external_id itself as a keyword
            term = external_id

        try:
            raw = await self._autocomplete(term, max_results=20)
        except Exception as exc:
            return PriceResult(
                external_id=external_id, name="", price=None, url=url,
                store="costco", error=True, error_message=str(exc),
            )

        # Find the product whose code matches
        match = next((p for p in raw if str(p.get("code", "")) == str(external_id)), None)
        if not match and raw:
            match = raw[0]

        if not match:
            return PriceResult(
                external_id=external_id, name="", price=None, url=url,
                store="costco", error=True, error_message="Product not found",
            )

        price, was_price, on_special = _parse_price(match)
        images = match.get("images") or []
        return PriceResult(
            external_id=external_id,
            name=(match.get("name") or "").strip(),
            price=price,
            was_price=was_price,
            on_special=on_special,
            url=url,
            store="costco",
            in_stock=_parse_in_stock(match),
            image_url=_image_url(images),
            unit=_parse_unit(match),
            error=price is None,
        )
