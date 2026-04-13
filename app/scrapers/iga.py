"""
IGA scraper for North Sydney area stores.

Uses the igashop.com.au Storefront API (Metcash):
  Search: GET https://www.igashop.com.au/api/storefront/stores/{store_id}/search
            ?q=QUERY&take=20&skip=0
  Product: GET https://www.igashop.com.au/api/storefront/stores/{store_id}/products/{sku}

Store IDs for the area:
  21283   — IGA North Sydney (Romeo's IGA, Greenwood Plaza)
  239417  — IGA Local Grocer Milsons Point
  19133   — IGA Greenwich  (nearest to Crows Nest; no dedicated Crows Nest store)
"""
import re
import httpx

from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

BASE_URL = "https://www.igashop.com.au/api/storefront"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer":         "https://www.igashop.com.au/",
    "Origin":          "https://www.igashop.com.au",
}

STORE_IDS = {
    # Lower North Shore
    "iga_north_sydney":  21283,    # Romeo's IGA, Greenwood Plaza
    "iga_milsons_point": 239417,   # IGA Local Grocer Milsons Point
    "iga_crows_nest":    19133,    # IGA Greenwich (nearest to Crows Nest)
    # Inner West / Newtown
    "iga_newtown":       8863,     # Lloyds IGA Newtown, 259 King St
    "iga_king_st":       95625,    # IGA Local Grocer King Street, 40 King St
}

STORE_DISPLAY = {
    "iga_north_sydney":  "Romeo's IGA Greenwood Plaza",
    "iga_milsons_point": "IGA Local Grocer Milsons Point",
    "iga_crows_nest":    "IGA Greenwich",
    "iga_newtown":       "Lloyds IGA Newtown",
    "iga_king_st":       "IGA Local Grocer King Street",
}


def _extract_unit(title: str) -> str | None:
    """Pull a size/unit out of a product title, e.g. '500ml', '1kg', '6 Pack'."""
    m = re.search(
        r"(\d+(?:\.\d+)?\s*(?:ml|mL|L|ltr|kg|g|Kg|Pk|pk|Pack|pack|x\s*\d+))\b",
        title,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def _parse_hit(hit: dict, store_slug: str) -> SearchResult:
    """Parse one product object from the IGA search response."""
    name      = hit.get("name", "")
    sku       = str(hit.get("sku") or hit.get("id") or "")
    url_slug  = hit.get("urlFriendlyName") or hit.get("slug") or sku
    store_id  = STORE_IDS.get(store_slug, "")

    # Price: priceNumeric is the plain float price
    price = hit.get("priceNumeric")
    if price is not None:
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = None

    # Was-price: wasPrice or tprPrice (temporary price reduction)
    was_price = None
    for key in ("wasPrice", "tprPrice", "originalPrice"):
        wp = hit.get(key)
        if wp:
            try:
                wp = float(wp)
                if wp > 0 and (price is None or wp > price):
                    was_price = wp
                    break
            except (ValueError, TypeError):
                pass

    on_special = was_price is not None

    # Image
    img_block = hit.get("image") or {}
    image_url = (
        img_block.get("default")
        or img_block.get("url")
        or img_block.get("src")
        or hit.get("imageUrl")
        or None
    )

    # Build canonical product URL
    product_url = (
        f"https://www.igashop.com.au/sm/planning/rsid/{store_id}/product/{url_slug}"
    )

    # pricePerUnit is a handy string like "$1.20/100g" — use as unit if regex fails
    unit = _extract_unit(name) or hit.get("pricePerUnit") or None

    return SearchResult(
        external_id = sku,
        name        = name,
        price       = price,
        url         = product_url,
        store       = store_slug,
        image_url   = image_url,
        category    = hit.get("category") or hit.get("categoryName"),
        unit        = unit,
    )


class IGAScraper(BaseScraper):
    """
    Base IGA scraper — parameterised by store_slug which resolves to a store_id.
    Subclass with store_slug set to one of the STORE_IDS keys.
    """

    store_slug: str  # must be overridden

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def _store_id(self) -> int:
        return STORE_IDS[self.store_slug]

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

    # ── Search ──────────────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """
        Search the IGA Storefront API for products at this store.
        Returns up to `limit` results.
        """
        client = await self._get_client()

        params = {
            "q":    query,
            "take": min(limit, 48),   # API allows up to 48 per page
            "skip": 0,
        }

        resp = await client.get(
            f"{BASE_URL}/stores/{self._store_id}/search",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        # Response shape: { "items": [...], "total": N }
        # Sometimes it's just a list at the top level.
        if isinstance(data, list):
            items = data
        else:
            items = data.get("items") or data.get("products") or data.get("results") or []

        return [_parse_hit(item, self.store_slug) for item in items[:limit]]

    # ── Price refresh ────────────────────────────────────────────────────────

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        """
        Fetch live price for a product using the IGA Storefront API.
        external_id is the product SKU.
        """
        client = await self._get_client()

        # Try the SKU endpoint first
        resp = await client.get(
            f"{BASE_URL}/stores/{self._store_id}/products/{external_id}",
        )

        if resp.status_code == 404:
            return PriceResult(
                external_id   = external_id,
                name          = "",
                price         = None,
                url           = url,
                store         = self.store_slug,
                error         = True,
                error_message = "Product not found (404)",
            )

        resp.raise_for_status()
        hit = resp.json()

        # Price
        price = hit.get("priceNumeric")
        try:
            price = float(price) if price is not None else None
        except (ValueError, TypeError):
            price = None

        # Was-price
        was_price = None
        for key in ("wasPrice", "tprPrice", "originalPrice"):
            wp = hit.get(key)
            if wp:
                try:
                    wp = float(wp)
                    if wp > 0 and (price is None or wp > price):
                        was_price = wp
                        break
                except (ValueError, TypeError):
                    pass

        on_special = was_price is not None

        # Image
        img_block = hit.get("image") or {}
        image_url = (
            img_block.get("default")
            or img_block.get("url")
            or hit.get("imageUrl")
            or None
        )

        # Stock
        in_stock = hit.get("available", True)
        if isinstance(in_stock, str):
            in_stock = in_stock.lower() not in ("false", "0", "no", "out of stock")

        name = hit.get("name", "")

        return PriceResult(
            external_id = external_id,
            name        = name,
            price       = price,
            was_price   = was_price,
            url         = url,
            store       = self.store_slug,
            in_stock    = bool(in_stock),
            on_special  = on_special,
            image_url   = image_url,
            unit        = _extract_unit(name) or hit.get("pricePerUnit"),
            category    = hit.get("category") or hit.get("categoryName"),
        )


# ── Convenience subclasses ───────────────────────────────────────────────────

class IGANorthSydneyScraper(IGAScraper):
    store_slug = "iga_north_sydney"


class IGAMilsonsPointScraper(IGAScraper):
    store_slug = "iga_milsons_point"


class IGACrowsNestScraper(IGAScraper):
    """Maps to IGA Greenwich — the nearest IGA to Crows Nest."""
    store_slug = "iga_crows_nest"


class IGANewtownScraper(IGAScraper):
    """Lloyds IGA Newtown, 259 King St."""
    store_slug = "iga_newtown"


class IGAKingStreetScraper(IGAScraper):
    """IGA Local Grocer King Street, 40 King St, Newtown."""
    store_slug = "iga_king_st"
