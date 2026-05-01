# Roadmap

Phases are intentionally focused — each one is a shippable slice of work, independently reviewable and testable.

---

## Phase 1 — Foundation ✅
_March 2026_

- FastAPI project scaffold with Uvicorn, Jinja2 templates, static files
- SQLAlchemy ORM with SQLite (dev) and PostgreSQL (prod via Neon)
- User authentication: registration, login, session (Starlette SessionMiddleware + bcrypt)
- Landing page with suburb selector and store checkbox grid
- Basic search form (HTMX POST → server renders results)
- Railway deployment with GitHub auto-deploy
- `.env.example` with all required variables documented

---

## Phase 2 — Store Scrapers ✅
_April 2026 (early)_

- `BaseScraper` ABC with `SearchResult` and `PriceResult` dataclasses
- **Woolworths scraper** — ScraperAPI residential proxy + `__NEXT_DATA__` HTML parse (Akamai bypass)
- **Coles scraper** — Direct Coles JSON search API
- **Harris Farm scraper** — Shopify Predictive Search API with per-location slug mapping
- **IGA scraper** — Metcash Storefront API with per-store store_id mapping
- **Aldi scraper** — Weekly catalogue HTML parse
- `unit_parser.py` — Parse cup strings (e.g., "$3.50 / 100g") into normalised per-unit values
- Product grouping (`_group_search_results`) — cross-store merging by brand + name similarity
- Per-unit savings display (e.g., "$1.20/100g cheaper at Coles")
- `/debug/woolworths` diagnostic endpoint

---

## Phase 3 — Watchlist & Alerts ✅
_April 2026 (mid)_

- `WatchlistEntry` model with per-entry `alert_drop_pct` and `alert_price_below` thresholds
- `PriceRecord` model for price history time-series per product
- Watchlist page — list all watched products with latest price and trend
- HTMX watchlist add / remove / edit (inline, no page reload)
- APScheduler background jobs:
  - `poll_watchlist_prices` — scrapes prices for all watched products on schedule
  - `send_digest_email` — weekly/daily summary email
- Resend API email integration (transactional alerts + digest)
- ntfy.sh push notification integration
- `NotificationSettings` singleton config (email, push, schedule, API keys)
- Settings page — configure all notification options and API keys via UI
- `AlertEvent` model to track notification history

---

## Phase 4 — Suburb & Store Selection ✅
_April 2026 (late)_

- 600+ Sydney suburb → store mapping in `suburbs.py` (all LGAs covered)
- Suburb coverage expanded: Canterbury/Bankstown, Blacktown, Fairfield/Cabramatta, South West, Penrith, Hawkesbury, Blue Mountains, Sutherland Shire, Hills District
- `geo.py` with haversine-based `nearby_suburbs()` for radius-based store discovery
- `UserPreference` model to persist suburb + store selections per user account
- Landing page: suburb search → shows nearby stores as a visual card grid
- Search page: active stores shown as colored pills; Harris Farm pill uses location-specific slug logic
- `STORE_INFO` dict with full store name, street address, and Google Maps link for each store
- Harris Farm and IGA checkboxes correctly map generic brand selection → location-specific slugs

---

## Costco Scraper ✅
_May 2026_

- **Costco scraper** — Hybris autocomplete JSON API (`/search/autocomplete/SearchBox`)
- `costco` slug added to Store enum, store labels/colors/info, ALL_STORE_SLUGS
- Costco included in all suburb store lists (national online pricing, like Aldi)
- Costco filter pill on search page (brand red `#E2231A`)
- PostgreSQL enum migration via `_migrate_enum_values()` in `database.py`
- Spec: `specs/2026-05-01-costco/`

---

## Phase 5 — Price History Charts 🔜
_Planned_

- Time-series chart per product on watchlist detail page (recharts or Chart.js)
- Price trend over 30 / 90 days with specials highlighted
- "Lowest ever" and "highest ever" price markers
- Chart rendered server-side SVG (no JS dependency) or via lightweight Alpine.js chart component

---

## Phase 6 — Shopping List (Beta → Complete) 🔜
_In progress_

- Shopping list model (`ShoppingList`, `ShoppingListItem`) exists — schema done
- UI: add items by keyword, mark as checked
- Background: search all user's stores for each list item, populate best match per store
- Output: "Cheapest cart" — total per store based on best matches
- Export: print-friendly list grouped by store aisle

---

## Phase 7 — Woolworths Reliability 🔜
_Blocked: requires paid ScraperAPI plan_

- Upgrade ScraperAPI to paid plan ($49/month) to get dedicated residential IPs not shared with other free-tier users
- Alternatively: evaluate [Bright Data](https://brightdata.com) residential proxies as a cheaper alternative
- Add Woolworths cache layer: cache search results for 2 hours to reduce ScraperAPI credit usage
- Retry logic with exponential backoff for 499 (concurrent request limit) errors

---

## Phase 8 — PWA & Mobile 🔜
_Planned_

- Web App Manifest + Service Worker (offline caching of watchlist page)
- Home screen install prompt
- VAPID-based browser push notifications (replaces/supplements ntfy.sh)
- Mobile-optimised search results layout (single-column, larger touch targets)
- Barcode scanner: camera API → scan product barcode → auto-search

---

## Phase 9 — Coles Store-Level Pricing 🔜
_Research needed_

- Coles API currently returns national shelf prices
- In-store specials require an authenticated session with a selected postcode
- Investigate Coles loyalty card API or cookie-based session approach

---

Later phases (not yet specified): multi-user households, social price sharing ("4 people are watching this"), integration with Everyday Rewards / Flybuys price tracking.
