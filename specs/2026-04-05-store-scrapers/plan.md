# Plan — Phase 2: Store Scrapers

Numbered task groups in implementation order. Each group is independently reviewable.

---

## Group 1 — Base Types

1. Create `app/scrapers/__init__.py` (empty).
2. Create `app/scrapers/base.py`:
   - `SearchResult` dataclass: `external_id`, `name`, `price`, `url`, `store`, `image_url`, `unit`, `_brand`, `_pu_value`, `_pu_label`
   - `PriceResult` dataclass: `external_id`, `name`, `price`, `was_price`, `url`, `store`, `in_stock`, `on_special`, `image_url`, `unit`
   - `BaseScraper` abstract class with `store_slug`, `search()`, `fetch_price()`, `close()`

## Group 2 — Unit Parser

3. Create `app/unit_parser.py`:
   - `parse_unit_price(cup_string: str, price: float) -> tuple[float | None, str | None]`
   - Handles formats: `"$3.50 / 100g"`, `"$14.00 / L"`, `"$31.20 / kg"`, `"$0.85 / ea"`, `"$12.60 / 100mL"`
   - Returns `(normalised_value_in_base_unit, display_label)` e.g. `(0.035, "$3.50/100g")`
   - Base units: per-100g (weight), per-100mL (volume), per-ea
   - Returns `(None, None)` if format not recognised

## Group 3 — Woolworths Scraper

4. Create `app/scrapers/woolworths.py`:
   - Import `get_scraperapi_key` from `app.config`
   - ScraperAPI integration: build URL `https://api.scraperapi.com/?api_key={key}&url={encoded_target}&render=false&country_code=au`
   - Target: `https://www.woolworths.com.au/shop/search/products?searchTerm={q}&hideUnavailable=true&pageNumber=1`
   - `_extract_from_html(html, limit)` → parse `<script id="__NEXT_DATA__">` → walk JSON for product arrays
   - `_deep_get(obj, *keys)` helper for safe nested dict access
   - `_map_product(p)` — normalise raw product node → `{"Stockcode", "Name", "Price", "CupString", ...}`
   - `_deep_search(obj, found, limit)` — fallback tree walker for non-standard `__NEXT_DATA__` shapes
   - `_parse_product(item)` → `SearchResult`
   - `fetch_price()` via Woolworths schema.org API: `https://www.woolworths.com.au/api/v3/ui/schemaorg/product/{stockcode}`
   - Timeout: 15 seconds for ScraperAPI calls; return `[]` on any error
5. Add `/debug/woolworths?q=milk` endpoint in `main.py` for diagnostics.

## Group 4 — Coles Scraper

6. Create `app/scrapers/coles.py`:
   - Search endpoint: `https://www.coles.com.au/api/2.0.0/category/search-results?storeId=0&q={q}&pageSize={limit}`
   - Parse JSON response: `results[].products[]` with `name`, `pricing.now`, `pricing.unit.quantity`, `imageUris`
   - `fetch_price()` via Coles product detail API
   - Headers: include `User-Agent` and Coles-specific `sec-fetch-*` headers to avoid 403

## Group 5 — Harris Farm Scraper

7. Create `app/scrapers/harris_farm.py`:
   - Location slug map: `{"harris_farm_cammeray": "cammeray", "harris_farm_mosman": "mosman", "harris_farm_lane_cove": "lane-cove", "harris_farm_broadway": "broadway"}`
   - Search via Shopify: `https://{location}.harrisfarm.com.au/search/suggest.json?q={q}&resources[type]=product&resources[limit]={limit}`
   - Parse `resources.results.products[].variants[0].price` for price
   - `search(query, limit, store_slug)` — accepts a specific location slug; called once per enabled HF location
   - `fetch_price()` via Shopify product JSON endpoint

## Group 6 — IGA Scraper

8. Create `app/scrapers/iga.py`:
   - Store ID map: `{"iga_north_sydney": "7391", "iga_milsons_point": "7392", "iga_crows_nest": "6802", "iga_newtown": "3174", "iga_king_st": "7393"}` (placeholder IDs — confirm with live API)
   - Search: `https://storefronts.iga.com.au/api/2.0/products/search?q={q}&storeId={store_id}&limit={limit}`
   - Parse `products[].name`, `products[].price`, `products[].imageUrl`

## Group 7 — Aldi Scraper

9. Create `app/scrapers/aldi.py`:
   - Fetch Aldi AU specials catalogue page: `https://www.aldi.com.au/en/groceries/`
   - Parse product tiles from HTML with BeautifulSoup: product name, price, image
   - Return matching products for the query using simple keyword substring match
   - Limit to 20 results; cache HTML for 1 hour to avoid hammering Aldi (in-memory cache)

## Group 8 — Search Route Integration

10. Update `POST /search` in `main.py`:
    - Parse `stores` form field → list of enabled store slugs
    - Instantiate scraper for each enabled store (reuse persistent instances)
    - `asyncio.gather()` all `scraper.search(query, limit=20)` calls with per-task exception handling
    - Flatten results list, pass to `_group_search_results()`
    - Render `search.html` with `groups` template variable
11. Update `app/templates/search.html`:
    - For each group: show canonical name, image, best price + store badge, savings indicator
    - For each entry in group: show store pill (colored), price, per-unit price
    - ☆ Watch button per group entry (HTMX `hx-post="/watchlist/add"`)

## Group 9 — Product Grouping Logic

12. Implement `_group_search_results(results)` in `main.py`:
    - `_base_name(name)` — strip size/weight suffixes (`\d+(\.\d+)?\s*(ml|l|g|kg|pk|pack)$`)
    - `_names_similar(a, b, threshold=0.65)` — Jaccard overlap of non-stop words
    - Group by brand gate + name similarity
    - Sort each group by per-unit price ascending
    - Compute `savings` = `max_pu − min_pu` per group
    - Return list of group dicts with `canonical`, `image_url`, `brand`, `entries`, `min_price`, `max_price`, `savings_label`, `best_store`

## Group 10 — Verification

13. Test manually: search "milk" with Woolworths + Coles selected — should return grouped results with prices.
14. Test: search "olive oil" with Harris Farm Broadway selected — should return Harris Farm results.
15. Test: `/debug/woolworths?q=milk` returns diagnostic JSON with `has_next_data: true` and `raw_products_found > 0`.
16. Push to Railway; confirm search works for Coles (Woolworths requires ScraperAPI key).
