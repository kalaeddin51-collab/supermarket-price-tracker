"""
Woolworths scraper — Playwright headless Chromium for Akamai bypass.

Woolworths uses Akamai Bot Manager with JavaScript challenges that
cannot be bypassed by any HTTP-only approach from cloud servers.
A real headless browser (Playwright + Chromium) generates valid
session tokens by executing Akamai's JS, allowing search API calls.

Strategy:
  1. If USE_PLAYWRIGHT=true (default): use Playwright async Chromium
     - Navigate to search page, intercept the API response via network events
     - 5–10s per search but actually works from cloud
  2. Fallback: direct POST (works on residential IPs, blocked on cloud)

Toggle off: set env var USE_PLAYWRIGHT=false on Railway to revert to
the fast-but-blocked HTTP approach if Playwright causes memory issues.
"""
import asyncio
import json as _json
import logging
import urllib.parse
import httpx
from app.scrapers.base import BaseScraper, PriceResult, SearchResult
from app.config import settings

logger = logging.getLogger(__name__)

WOW_HOME = "https://www.woolworths.com.au"
SEARCH_API_PATH = "/apis/ui/Search/products"

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


def _use_playwright() -> bool:
    return settings.use_playwright.lower() not in ("false", "0", "no", "off")


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
        if _use_playwright():
            try:
                return await self._search_playwright(query, limit)
            except Exception as exc:
                logger.error("Woolworths Playwright search failed: %s", exc)
                raise
        return await self._search_direct(query, limit)

    async def _search_playwright(self, query: str, limit: int) -> list[SearchResult]:
        """Use Playwright headless Chromium to bypass Akamai JS challenge.

        Strategy: navigate to the search page and use wait_for_response()
        to capture the search API JSON response as it's triggered by the page.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("Playwright not installed — set USE_PLAYWRIGHT=false")

        import re

        search_url = (
            f"{WOW_HOME}/shop/search/products"
            f"?searchTerm={urllib.parse.quote(query)}"
        )

        logger.info("Woolworths Playwright: launching browser for %r", query)

        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-first-run",
            "--disable-extensions",
            "--disable-background-networking",
            "--mute-audio",
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=launch_args)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-AU",
                timezone_id="Australia/Sydney",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Accept-Language": "en-AU,en;q=0.9"},
            )
            page = await context.new_page()

            try:
                logger.info("Woolworths: navigating to search page")

                # Start navigation and wait for the API call simultaneously
                async with page.expect_response(
                    lambda r: SEARCH_API_PATH in r.url,
                    timeout=45_000
                ) as response_info:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)

                api_response = await response_info.value
                logger.info("Woolworths: API response captured (status=%d url=%s)",
                            api_response.status, api_response.url)

                try:
                    data = await api_response.json()
                except Exception:
                    body_text = await api_response.text()
                    logger.warning("Woolworths: API non-JSON body: %s", body_text[:300])
                    data = {}

            except Exception as exc:
                logger.warning("Woolworths: expect_response failed (%s) — parsing DOM", exc)
                # Fallback: parse products from the fully rendered DOM
                try:
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
                content = await page.content()
                match = re.search(
                    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                    content, re.DOTALL
                )
                if match:
                    nd = _json.loads(match.group(1))
                    data = nd.get("props", {}).get("pageProps", {})
                    logger.info("Woolworths: parsed __NEXT_DATA__ from DOM, keys=%s",
                                list(data.keys())[:10])
                else:
                    logger.error("Woolworths: no API response or __NEXT_DATA__ in DOM")
                    data = {}
            finally:
                await context.close()
                await browser.close()

        # Parse results — API shape: {"Products": [{"Products": [...]}]}
        products_raw = []
        for bundle in data.get("Products", []):
            if isinstance(bundle, dict):
                products_raw.extend(bundle.get("Products", []))

        # Fallback: pageProps shape from __NEXT_DATA__
        if not products_raw:
            sr = data.get("searchResults") or data.get("search") or {}
            if isinstance(sr, dict):
                for bundle in sr.get("Products", []):
                    if isinstance(bundle, dict):
                        products_raw.extend(bundle.get("Products", []))

        logger.info("Woolworths Playwright: %d raw products for %r", len(products_raw), query)
        results = [p for p in (_parse_product(x) for x in products_raw) if p]
        return results[:limit]

    async def _search_direct(self, query: str, limit: int) -> list[SearchResult]:
        """Direct POST — only works on residential IPs, blocked on cloud servers."""
        client = await self._get_client()
        try:
            await client.get(f"{WOW_HOME}/")
        except Exception:
            pass

        payload = {
            "Filters": [], "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={query}",
            "PageNumber": 1, "PageSize": limit,
            "SearchTerm": query, "SortType": "TraderRelevance",
            "token": "", "gpBoost": 0, "CategoryVersion": "v2",
        }
        resp = await client.post(
            f"{WOW_HOME}{SEARCH_API_PATH}", json=payload,
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        products_raw = []
        for bundle in data.get("Products", []):
            products_raw.extend(bundle.get("Products", []))
        logger.info("Woolworths direct: %d products for %r", len(products_raw), query)
        return [p for p in (_parse_product(x) for x in products_raw) if p]

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        """Fetch current price — uses Playwright if available, else direct GET."""
        if _use_playwright():
            try:
                return await self._fetch_price_playwright(external_id, url)
            except Exception as exc:
                logger.error("Woolworths fetch_price Playwright failed: %s", exc)
                raise

        client = await self._get_client()
        target = f"{WOW_HOME}/api/v3/ui/schemaorg/product/{external_id}"
        resp = await client.get(target)
        resp.raise_for_status()
        return self._parse_price_response(external_id, url, resp.json())

    async def _fetch_price_playwright(self, external_id: str, url: str) -> PriceResult:
        """Use Playwright to fetch product price (bypasses Akamai)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("Playwright not installed")

        product_url = f"{WOW_HOME}/shop/productdetails/{external_id}"
        api_future: asyncio.Future = asyncio.get_running_loop().create_future()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu",
                      "--disable-extensions"],
            )
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-AU",
                timezone_id="Australia/Sydney",
            )
            page = await context.new_page()

            async def handle_response(response):
                if f"/product/detail?stockcode={external_id}" in response.url \
                        and not api_future.done():
                    try:
                        body = await response.json()
                        api_future.set_result(body)
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    data = await asyncio.wait_for(asyncio.shield(api_future), timeout=15.0)
                except asyncio.TimeoutError:
                    # Fallback: parse schema.org JSON-LD from the page
                    import re
                    content = await page.content()
                    match = re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                      content, re.DOTALL)
                    if match:
                        data = _json.loads(match.group(1))
                    else:
                        raise RuntimeError(f"Could not fetch price for {external_id}")
            finally:
                await context.close()
                await browser.close()

        return self._parse_price_response(external_id, url, data)

    def _parse_price_response(self, external_id: str, url: str, data: dict) -> PriceResult:
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
