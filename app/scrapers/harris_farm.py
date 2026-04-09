"""
Harris Farm Markets scraper — Cammeray store.

Uses Shopify's Predictive Search API (no auth required):
  GET https://www.harrisfarm.com.au/search/suggest.json

For price refresh:
  GET https://www.harrisfarm.com.au/products/{handle}.json
"""
import re
import httpx

from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

BASE_URL = "https://www.harrisfarm.com.au"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer":         "https://www.harrisfarm.com.au/",
}

# Harris Farm store IDs (picking_store cookie)
# 52 = Cammeray   28 = Mosman   72 = Lane Cove   37 = Broadway
# We search against the online catalogue (default) which is store-neutral.


def _extract_unit(title: str) -> str | None:
    """Pull a size/unit out of a product title, e.g. '500ml', '1kg', '6 Pack'."""
    m = re.search(
        r"(\d+(?:\.\d+)?\s*(?:ml|mL|L|ltr|kg|g|Kg|g|Pk|pk|Pack|pack|x\s*\d+))\b",
        title,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def _parse_suggest_hit(hit: dict) -> SearchResult:
    title = hit.get("title", "")

    # Shopify price strings like "12.69"
    price_str = hit.get("price") or "0"
    try:
        price = float(price_str)
    except (ValueError, TypeError):
        price = None

    # compare_at_price_max non-zero → product is on sale
    compare_str = hit.get("compare_at_price_max") or "0"
    try:
        compare = float(compare_str)
    except (ValueError, TypeError):
        compare = 0.0
    on_special = compare > 0 and price is not None and compare > price
    was_price  = compare if on_special else None

    # Image
    fi        = hit.get("featured_image") or {}
    image_url = fi.get("url") or fi.get("src") or hit.get("image") or None

    # URL — strip tracking query params
    url_path = hit.get("url", "").split("?")[0]
    full_url = f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path

    return SearchResult(
        external_id = str(hit.get("id", "")),
        name        = title,
        price       = price,
        url         = full_url,
        store       = "harris_farm",
        image_url   = image_url,
        category    = hit.get("type"),
        unit        = _extract_unit(title),
    )


class HarrisFarmScraper(BaseScraper):
    store_slug = "harris_farm"

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

    # ── Search ────────────────────────────────────────────────────────────

    # Target store IDs for accurate pricing (variant title prefix)
    # 52 = Cammeray  28 = Mosman  72 = Lane Cove  37 = Broadway
    _TARGET_STORE_IDS = ("52", "28", "72", "37")

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """
        Shopify Predictive Search — returns up to 10 products per call.
        Prices from the suggest API are the minimum across all store variants,
        so we enrich each result with the accurate store-specific price from
        the product JSON endpoint.
        """
        import asyncio as _asyncio

        client = await self._get_client()

        params = {
            "q":                                   query,
            "resources[type]":                     "product",
            "resources[limit]":                    min(limit, 10),
            "resources[options][unavailable_products]": "last",
        }

        resp = await client.get(f"{BASE_URL}/search/suggest.json", params=params)
        resp.raise_for_status()
        data = resp.json()

        products = (
            data.get("resources", {})
                .get("results", {})
                .get("products", [])
        )
        base_results = [_parse_suggest_hit(p) for p in products]

        # Enrich with store-accurate prices (concurrent fetches)
        enriched = await _asyncio.gather(
            *[self._enrich_price(r) for r in base_results],
            return_exceptions=True,
        )
        return [r for r in enriched if isinstance(r, SearchResult)]

    async def _enrich_price(self, result: SearchResult) -> SearchResult:
        """
        Fetch product JSON and extract the price for our target store variants.
        Harris Farm stores each store's price as a Shopify variant with title
        like '{store_id} / {origin} / Default' (regular) or
        '{store_id} / {origin} / Special{store_id}' (on special).
        """
        if "/products/" not in result.url:
            return result
        handle = result.url.rstrip("/").split("/products/")[-1].split("?")[0]
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{BASE_URL}/products/{handle}.json",
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json().get("product", {})
            variants = data.get("variants", [])
            if not variants:
                return result

            # Group variants by store ID from their title prefix
            store_regular: dict[str, float] = {}
            store_special: dict[str, float] = {}
            all_prices: list[float] = []

            for v in variants:
                title = str(v.get("title", ""))
                price_str = v.get("price")
                if not price_str:
                    continue
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue
                all_prices.append(price)
                parts = [p.strip() for p in title.split("/")]
                store_id = parts[0] if parts else ""
                tier = parts[2] if len(parts) >= 3 else "Default"
                if "Special" in tier:
                    store_special[store_id] = price
                else:
                    store_regular[store_id] = price

            # Find regular price for our target stores
            regular_price = None
            for sid in self._TARGET_STORE_IDS:
                if sid in store_regular:
                    regular_price = store_regular[sid]
                    break

            # Fall back to most common non-minimum price if no target store found
            if regular_price is None and all_prices:
                from collections import Counter
                # Exclude outlier low prices (online/export variants)
                if len(all_prices) > 1:
                    filtered = [p for p in all_prices if p > min(all_prices)]
                    regular_price = Counter(filtered).most_common(1)[0][0] if filtered else all_prices[0]
                else:
                    regular_price = all_prices[0]

            # Check if any store currently has a special (promotion tier variants)
            # Special variants have titles like '{id} / {origin} / Special{tier}'
            special_prices = list(store_special.values())
            on_special_price = min(special_prices) if special_prices else None

            if on_special_price is not None and regular_price is not None and on_special_price < regular_price:
                result.price = on_special_price
                result.was_price = regular_price
                result.on_special = True
            elif regular_price is not None:
                result.price = regular_price

        except Exception:
            pass  # Keep original suggest price on any error

        return result

    # ── Price refresh ─────────────────────────────────────────────────────

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        """
        Fetch live price using the Shopify product JSON endpoint.
        URL must be a harrisfarm.com.au/products/{handle} URL.
        """
        client = await self._get_client()

        # Derive handle from URL
        if "/products/" in url:
            handle = url.rstrip("/").split("/products/")[-1].split("?")[0]
        else:
            # Fall back: external_id may be a numeric Shopify product ID —
            # re-search by id isn't easily supported so we'll try the search API.
            handle = None

        if handle:
            resp = await client.get(f"{BASE_URL}/products/{handle}.json")
            resp.raise_for_status()
            data = resp.json().get("product", {})
        else:
            return PriceResult(
                external_id   = external_id,
                name          = "",
                price         = None,
                url           = url,
                store         = self.store_slug,
                error         = True,
                error_message = "Cannot resolve product handle from URL",
            )

        variants  = data.get("variants", [])
        first     = variants[0] if variants else {}

        price_str    = first.get("price") or "0"
        compare_str  = first.get("compare_at_price") or "0"
        try:
            price   = float(price_str) or None
            compare = float(compare_str)
        except (ValueError, TypeError):
            price, compare = None, 0.0

        on_special = compare > 0 and price is not None and compare > price
        was_price  = compare if on_special else None

        images    = data.get("images", [])
        image_url = images[0].get("src") if images else None
        in_stock  = any(v.get("available", True) for v in variants) if variants else True

        return PriceResult(
            external_id = external_id,
            name        = data.get("title", ""),
            price       = price,
            was_price   = was_price,
            url         = url,
            store       = self.store_slug,
            in_stock    = in_stock,
            on_special  = bool(on_special),
            image_url   = image_url,
            unit        = _extract_unit(data.get("title", "")),
            category    = data.get("product_type"),
        )
