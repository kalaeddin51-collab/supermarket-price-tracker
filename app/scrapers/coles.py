"""
Coles scraper using the Next.js data endpoints reverse-engineered from the website.

Coles uses Next.js SSR — product data is served via:
  GET /_next/data/{BUILD_ID}/en/search/products.json?q={query}
  GET /_next/data/{BUILD_ID}/en/product/{id}/{slug}.json

The BUILD_ID rotates with each deployment, so we fetch it dynamically from
the __NEXT_DATA__ JSON embedded in any Coles page.

Image CDN: https://cdn.productimages.coles.com.au/productimages{uri}
"""
import re
import json
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings, get_scraperapi_key

COLES_BASE = "https://www.coles.com.au"
IMAGE_CDN = "https://cdn.productimages.coles.com.au/productimages"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.coles.com.au/",
}


def _scraperapi_url(target_url: str) -> str:
    """Wrap a target URL with ScraperAPI if a key is configured."""
    return f"http://api.scraperapi.com?api_key={get_scraperapi_key()}&url={urllib.parse.quote(target_url, safe='')}"


def _use_scraperapi() -> bool:
    return bool(get_scraperapi_key())


def _parse_product(item: dict) -> SearchResult | None:
    if item.get("_type") != "PRODUCT":
        return None
    product_id = str(item.get("id", ""))
    name = item.get("name", "")
    brand = item.get("brand", "")
    size = item.get("size", "")
    full_name = f"{brand} {name} {size}".strip()

    pricing = item.get("pricing") or {}
    price = pricing.get("now")
    unit = pricing.get("comparable")

    image_uri = None
    for img in item.get("imageUris") or []:
        if img.get("type") == "default":
            image_uri = IMAGE_CDN + img["uri"]
            break

    slug = re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")
    url = f"{COLES_BASE}/product/{slug}-{product_id}"

    return SearchResult(
        external_id=product_id,
        name=full_name,
        price=float(price) if price else None,
        url=url,
        store="coles",
        image_url=image_uri,
        unit=unit,
    )


class ColesScraper(BaseScraper):
    store_slug = "coles"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._build_id: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            proxy = settings.scraper_proxy or None
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=60,  # longer timeout for proxy/ScraperAPI
                follow_redirects=True,
                proxy=proxy if not _use_scraperapi() else None,
            )
        return self._client

    async def _get_build_id(self) -> str:
        """Fetch the current Next.js build ID.

        Uses a non-existent API route which returns a Next.js 404 HTML page
        containing __NEXT_DATA__ (and therefore the buildId). This page is
        served without Incapsula bot protection, unlike the main homepage.
        """
        if self._build_id:
            return self._build_id

        client = await self._get_client()
        target = f"{COLES_BASE}/api/_build_id_probe"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(target))
        else:
            r = await client.get(target)
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text,
            re.DOTALL,
        )
        if match:
            data = json.loads(match.group(1))
            self._build_id = data.get("buildId")
        if not self._build_id:
            raise RuntimeError("Could not determine Coles Next.js build ID")
        return self._build_id

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        client = await self._get_client()
        build_id = await self._get_build_id()

        target = f"{COLES_BASE}/_next/data/{build_id}/en/search/products.json?q={urllib.parse.quote(query)}"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(target))
        else:
            r = await client.get(
                f"{COLES_BASE}/_next/data/{build_id}/en/search/products.json",
                params={"q": query},
            )
        r.raise_for_status()
        data = r.json()

        search_results = data.get("pageProps", {}).get("searchResults", {})
        raw_products = search_results.get("results", [])

        results = []
        for item in raw_products:
            parsed = _parse_product(item)
            if parsed:
                results.append(parsed)
            if len(results) >= limit:
                break
        return results

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        client = await self._get_client()
        build_id = await self._get_build_id()

        # URL format: /product/{slug}-{id}  e.g. /product/coles-full-cream-milk-3l-8150288
        slug_with_id = url.rstrip("/").split("/product/")[-1]
        target = f"{COLES_BASE}/_next/data/{build_id}/en/product/{slug_with_id}.json"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(target))
        else:
            r = await client.get(target)

        if r.status_code == 404:
            return await self._fetch_via_search(external_id, url)

        r.raise_for_status()
        page_props = r.json().get("pageProps", {})

        # If the endpoint returns a redirect, follow it to the canonical slug
        redirect = page_props.get("__N_REDIRECT")
        if redirect:
            # redirect is like "/product/coles-full-cream-milk-3l-8150288"
            canonical = redirect.split("/product/")[-1]
            target2 = f"{COLES_BASE}/_next/data/{build_id}/en/product/{canonical}.json"
            if _use_scraperapi():
                r = await client.get(_scraperapi_url(target2))
            else:
                r = await client.get(target2)
            r.raise_for_status()
            page_props = r.json().get("pageProps", {})

        data = r.json()
        product = page_props.get("product") or {}

        pricing = product.get("pricing") or {}
        price = pricing.get("now")
        was_raw = pricing.get("was", 0)
        was_price = float(was_raw) if was_raw else None
        on_special = bool(pricing.get("onlineSpecial") or (was_price and was_price != price))
        in_stock = product.get("availability", True)
        unit = pricing.get("comparable")

        name_parts = [product.get("brand", ""), product.get("name", ""), product.get("size", "")]
        name = " ".join(p for p in name_parts if p).strip()

        image_uri = None
        for img in product.get("imageUris") or []:
            if img.get("type") == "default":
                image_uri = IMAGE_CDN + img["uri"]
                break

        return PriceResult(
            external_id=external_id,
            name=name,
            price=float(price) if price is not None else None,
            was_price=was_price,
            url=url,
            store=self.store_slug,
            in_stock=bool(in_stock),
            on_special=on_special,
            image_url=image_uri,
            unit=unit,
        )

    async def _fetch_via_search(self, external_id: str, url: str) -> PriceResult:
        """Fallback: find a product by searching its ID."""
        client = await self._get_client()
        build_id = await self._get_build_id()
        target = f"{COLES_BASE}/_next/data/{build_id}/en/search/products.json?q={urllib.parse.quote(external_id)}"
        if _use_scraperapi():
            r = await client.get(_scraperapi_url(target))
        else:
            r = await client.get(
                f"{COLES_BASE}/_next/data/{build_id}/en/search/products.json",
                params={"q": external_id},
            )
        r.raise_for_status()
        data = r.json()
        for item in data.get("pageProps", {}).get("searchResults", {}).get("results", []):
            if str(item.get("id")) == external_id:
                parsed = _parse_product(item)
                if parsed:
                    pricing = item.get("pricing") or {}
                    was_raw = pricing.get("was", 0)
                    return PriceResult(
                        external_id=external_id,
                        name=parsed.name,
                        price=parsed.price,
                        was_price=float(was_raw) if was_raw else None,
                        url=parsed.url,
                        store=self.store_slug,
                        in_stock=item.get("availability", True),
                        on_special=bool(pricing.get("onlineSpecial")),
                        image_url=parsed.image_url,
                        unit=parsed.unit,
                    )
        return PriceResult(
            external_id=external_id, name="", price=None, url=url,
            store=self.store_slug, error=True, error_message="Product not found",
        )
