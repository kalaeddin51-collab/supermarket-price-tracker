# Plan — Costco Scraper

## Implementation Steps

1. **`app/scrapers/costco.py`** (new file)
   - `_parse_price_str(s)` — regex float extractor
   - `_parse_products_from_html(html)` — BeautifulSoup Magento 2 parser
     (selectors: `li.product-item`, `.product-item-name a`, `.price-box .price`, `.old-price .price`, `img.product-image-photo`)
   - `_parse_products_from_json_ld(soup)` — JSON-LD fallback
   - `_parse_detail_page(html, external_id, url)` — product detail page parser
   - `CostcoScraper(BaseScraper)` with `store_slug = "costco"`, `search()`, `fetch_price()`

2. **`app/models.py`**
   - Add `costco = "costco"` to `Store` enum (after `aldi`)

3. **`app/database.py`**
   - Add `_migrate_enum_values()` — runs `ALTER TYPE store ADD VALUE IF NOT EXISTS 'costco'` on PostgreSQL
   - Call it from `init_db()` after `_migrate_columns()`

4. **`app/main.py`**
   - `STORE_LABELS`: add `"costco": "Costco"`
   - `STORE_COLORS`: add `"costco": "#E2231A"`
   - `STORE_INFO`: add costco entry with both Sydney warehouse addresses
   - `ALL_STORE_SLUGS`: add `"costco"` after `"aldi"`
   - `_search_one_store`: add `elif store_slug == "costco"` branch
   - `_scraper_map` (search route): add `"costco": CostcoScraper`
   - Shopping list single-item search: add `CostcoScraper` import + task
   - Shopping list search-all: add `CostcoScraper` import + task
   - Shopping list bulk-search: add `CostcoScraper` import + task

5. **`app/suburbs.py`**
   - After `SUBURB_STORES` dict definition, add post-processing:
     `SUBURB_STORES = {k: (v + ["costco"] if "costco" not in v else v) for k, v in SUBURB_STORES.items()}`

6. **`app/templates/search.html`**
   - Extend the pill-building loop to include `('aldi', '#0050AA')` and `('costco', '#E2231A')`
   - Update the no-preference fallback to also include aldi and costco pills
