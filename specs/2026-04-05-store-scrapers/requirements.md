# Requirements — Phase 2: Store Scrapers

## Scope

Phase 2 wires real product search results into the search page. Each supported store gets a dedicated async scraper class. A product grouping layer merges results across stores for side-by-side comparison.

## Decisions

### BaseScraper Contract
All scrapers implement a common interface:
```python
class BaseScraper:
    store_slug: str

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        ...

    async def fetch_price(self, external_id: str, url: str) -> PriceResult:
        ...

    async def close(self):
        ...
```

`SearchResult` and `PriceResult` are frozen dataclasses defined in `base.py`. The rest of the app imports from `base.py` only — scrapers are internal implementation details.

### Concurrency
All scraper `search()` calls are fired concurrently with `asyncio.gather()` inside the `/search` route. Each scraper maintains its own `httpx.AsyncClient` instance, reused across requests.

### Woolworths Bot Bypass
- Akamai bot-detection blocks all Railway/cloud datacenter IPs — both the JSON API and the HTML search page.
- Solution: **ScraperAPI residential proxies** with `render=false` (static HTML parse) and `country_code=au`.
- The `__NEXT_DATA__` Next.js SSR JSON blob embedded in the HTML page contains all product data without needing JavaScript execution.
- `render=false` latency: ~5–10 seconds. `render=true` (headless browser): 15–30 seconds — too slow.
- Fallback chain: ScraperAPI → legacy Cloudflare Worker (now also blocked) → direct request (works on residential IPs only).
- If no `SCRAPERAPI_KEY` is set on Railway, Woolworths returns `[]` gracefully — other stores still return results.

### Harris Farm
- Uses Shopify Predictive Search API (`/search/suggest.json`) — no authentication required.
- Each physical location has its own Shopify storefront domain: `https://{location}.harrisfarm.com.au`
- Internal slug → Shopify domain mapping is hardcoded in the scraper (4 locations: Cammeray, Mosman, Lane Cove, Broadway).

### IGA
- Uses Metcash Storefront API (`storefronts.iga.com.au/api/2.0/products/search`).
- Each IGA store has a numeric `store_id`. Mapping is hardcoded: 5 stores (North Sydney, Milsons Point, Crows Nest, Newtown, King St).
- Returns JSON product data without authentication.

### Aldi
- No search API. Scrapes Aldi AU weekly specials catalogue HTML.
- Results limited to current week's catalogue items.
- Not expected to match all search queries — "no results" is acceptable for many queries.

### Product Grouping
- Products across stores are merged into comparison groups using brand gating + name similarity.
- **Brand gate**: if both products have non-empty brands, they must match to be grouped.
- **Name similarity**: ≥65% Jaccard word overlap (after stripping size tokens like "2L", "500g").
- Groups are sorted by cheapest per-unit price, with `savings` computed as `max_pu − min_pu`.
- Per-unit values are parsed from the store's "cup string" (e.g., "$3.50 / 100g") via `unit_parser.py`.

### Error Handling
Each scraper call is wrapped in `try/except` inside `asyncio.gather()`. A failing scraper returns `[]` — the search page still shows results from other stores. Errors are logged but not surfaced to the user.

## Context
- The store slug system established here is reused by Phase 3 (watchlist stores) and Phase 4 (suburb → store mapping).
- `SearchResult.external_id` is the key used in Phase 3 to look up a product for price polling.
- The grouping algorithm must stay stable as stores are added — changes to grouping logic can change which products appear together.

## Out of Scope
- Price history recording (Phase 3 — `fetch_price` is implemented here but only called by Phase 3's scheduler)
- Suburb-based store filtering (Phase 4)
- ALDI full product catalogue (Aldi only exposes weekly specials)
- Coles store-level pricing (requires authenticated session — post-MVP)
