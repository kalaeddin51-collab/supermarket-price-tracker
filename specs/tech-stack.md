# Supermarket Price Tracker — Tech Stack

## System Design

This is a **FastAPI server-rendered application** with HTMX partial updates and Alpine.js local state. The backend serves Jinja2 HTML templates. Scrapers run as async tasks within the request lifecycle (for search) or as APScheduler background jobs (for watchlist price polling).

**Two interaction surfaces, one server:**
- **Public-facing web app** (`GET /`, `GET /search`, `GET /watchlist`, etc.) — Jinja2 templates with HTMX for reactive updates, Alpine.js for client state
- **Background scheduler** — APScheduler jobs that scrape prices for all watchlist products on a configured cadence (daily or weekly) and fire alerts when thresholds are crossed

**Architectural layers:**
```
Frontend:    Jinja2 Templates + HTMX (partial page updates) + Alpine.js (local state)
Web Layer:   FastAPI routes + SessionMiddleware (Starlette)
Scrapers:    httpx async clients — one class per store (WoolworthsScraper, ColesScraper, ...)
Notifiers:   Resend API (email) + ntfy.sh HTTP API (push)
Storage:     SQLAlchemy ORM → SQLite (dev) / PostgreSQL (prod via Neon)
Scheduler:   APScheduler (background price polling + alert delivery)
Deploy:      Railway (auto-deploy from GitHub main branch)
```

## Configuration

Environment variables (`.env` / Railway Variables):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./prices.db` | Database connection string. Use `postgresql://...` on Railway |
| `SESSION_SECRET_KEY` | `price-tracker-secret-key-...` | Signs session cookies. Must be set to a long random string in prod |
| `SCRAPERAPI_KEY` | `""` | ScraperAPI key for Woolworths bypass. Free tier (1000 req/month) insufficient on Railway shared IPs; requires paid plan |
| `RESEND_API_KEY` | `""` | Resend API key for transactional email (alerts + digests) |
| `EMAIL_FROM` | `""` | Sender address — must be a verified domain in Resend |
| `EMAIL_TO` | `""` | Default recipient for alerts |
| `NTFY_TOPIC` | `""` | ntfy.sh topic for push notifications |
| `WOOLWORTHS_PROXY_URL` | `""` | Legacy Cloudflare Worker proxy (no longer functional — Akamai blocks CF IPs) |
| `SCRAPE_DELAY_SECONDS` | `3.0` | Delay between sequential scraper calls |
| `REQUEST_TIMEOUT_SECONDS` | `30` | HTTP timeout for scraper requests |

## Components

### Scrapers

Each store has a dedicated scraper class inheriting from `BaseScraper`. Every scraper implements:
- `async search(query: str, limit: int) -> list[SearchResult]`
- `async fetch_price(external_id: str, url: str) -> PriceResult`
- `async close()` — cleanup of httpx client

```
app/scrapers/
├── base.py          # BaseScraper ABC + SearchResult + PriceResult dataclasses
├── woolworths.py    # ScraperAPI → HTML → __NEXT_DATA__ JSON parse
├── coles.py         # Direct JSON API (v2/browse/products?storeId=...)
├── harris_farm.py   # Shopify Predictive Search API (per-location slug)
├── iga.py           # Metcash Storefront API (per-store store_id)
└── aldi.py          # HTML catalogue scrape (Aldi AU weekly specials page)
```

**SearchResult** (base.py):
```python
@dataclass
class SearchResult:
    external_id: str      # Store's product ID
    name: str
    price: float | None
    url: str
    store: str            # Store slug (e.g., "woolworths", "harris_farm_broadway")
    image_url: str | None
    unit: str | None      # Cup/unit string from store (e.g., "$3.50 / 100g")
    _brand: str | None    # Extracted brand for grouping
    _pu_value: float | None  # Normalised per-unit price value
    _pu_label: str | None    # Display label (e.g., "$3.50/100g")
```

#### Woolworths Scraper
Akamai bot-protection blocks all cloud datacenter IPs. Strategy:
1. If `SCRAPERAPI_KEY` is set → fetch `/shop/search/products?searchTerm=...` through ScraperAPI residential proxies with `render=false` (static HTML, ~5–10s) and `country_code=au`
2. Parse the embedded `__NEXT_DATA__` Next.js SSR blob to extract product arrays
3. Fall back to Cloudflare Worker proxy (legacy — also blocked now) then direct request (works on residential IPs only)

Key function: `_extract_from_html(html, limit)` — regex for `<script id="__NEXT_DATA__">`, then walks the JSON tree for product arrays via `_deep_get` / `_deep_search`.

#### Coles Scraper
Direct JSON API: `https://www.coles.com.au/api/2.0.0/category/search-results?storeId=...&q=...`. Returns standard Coles product JSON. No authentication required. Reliable on cloud IPs.

#### Harris Farm Scraper
Uses Shopify's Predictive Search API: `https://www.harrisfarm.com.au/search/suggest.json?q=...&resources[type]=product`. Each Harris Farm location has a different Shopify storefront slug — the scraper maps our internal store slugs to HF location slugs (e.g., `harris_farm_broadway` → `broadway`). Price is extracted from `variants[0].price`.

#### IGA Scraper
Uses the Metcash Storefront API: `https://storefronts.iga.com.au/api/2.0/products/search?q=...&storeId=...`. Each IGA store has a numeric `store_id` mapped in the scraper. Returns JSON with product name, price, and image.

#### Aldi Scraper
Fetches the Aldi AU weekly catalogue HTML page and parses product tiles. Aldi does not offer a search API; results are limited to whatever is in the current week's catalogue. Full product catalogue search is not supported.

### Product Grouping

`_group_search_results()` in `main.py` merges results from all scrapers into cross-store comparison groups:

1. Strip size/weight suffixes from names (`_base_name()`) so "Milk 2L" and "Milk 3L" are separate groups
2. Brand gate: different brands are never merged (both brands must be blank to skip brand check)
3. Name similarity: Jaccard-style word overlap ≥65% (`_names_similar()`)
4. Per-group: sort by per-unit price ascending, compute `savings` (max_pu − min_pu), tag `best_store`

### Suburb → Store Mapping

`app/suburbs.py` is a hand-curated lookup table mapping every Sydney suburb (600+) to a list of store slugs. Each suburb entry specifies which stores serve it.

Store list constants:
- `_W` = Woolworths
- `_C` = Coles  
- `_A` = Aldi
- `_HF_*` = Harris Farm location slugs (only suburbs near a Harris Farm)
- `_IGA_*` = IGA location slugs (only suburbs near a relevant IGA)

`app/geo.py` implements `nearby_suburbs(suburb, radius_km)` using a haversine distance table to expand a user's suburb to nearby ones (for broader store coverage).

### Notifiers

```
app/notifiers/
├── alerts.py         # Core alert logic: check watchlist prices, fire when threshold crossed
├── email.py          # Resend API integration (transactional + digest emails)
├── push.py           # ntfy.sh HTTP POST push notifications
└── shopping_email.py # Weekly shopping list digest email template
```

Alert triggers:
- `drop_pct`: fires when current price is ≥ N% below the recorded baseline price
- `price_below`: fires when price drops below an absolute threshold (e.g., under $2.50)
- `back_in_stock`: fires when `in_stock` transitions from False to True
- `on_special`: fires when `on_special` is True and `notify_on_special` is enabled globally

### Background Scheduler (APScheduler)

Configured in `main.py` on application startup. Two job types:

1. **Price poll job** (`poll_watchlist_prices`) — iterates all `WatchlistEntry` rows, calls `fetch_price` on each product's scraper, records a new `PriceRecord`, then checks alert conditions. Runs daily or weekly per `NotificationSettings.poll_frequency`.

2. **Digest email job** (`send_digest_email`) — sends a summary email of all watchlist items with current prices and any price movements. Runs on the schedule defined in `NotificationSettings.digest_frequency` (daily or weekly at a configured hour).

## Data Layer

SQLAlchemy 2.0 with `mapped_column` + `Mapped` type annotations. Single `Base` from `app/database.py`. Alembic for migrations (auto-generated, applied via `alembic upgrade head` at startup if env var `AUTO_MIGRATE=1`).

### Tables

**users**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| name | String(100) | |
| email | String(254) | unique, indexed |
| password_hash | String(200) | bcrypt |
| created_at | DateTime | UTC |

**user_preferences**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| user_id | FK → users | unique (one preference per user) |
| suburb | String(100) | e.g. "neutral bay" |
| stores | String(300) | comma-separated slugs e.g. "woolworths,coles,harris_farm_broadway" |
| updated_at | DateTime | |

**products**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| name | String(300) | |
| store | SAEnum(Store) | enum: woolworths, coles, harris_farm_broadway, iga_newtown, ... |
| external_id | String(100) | Store's own product ID / stockcode |
| url | Text | Direct product page URL |
| image_url | Text | nullable |
| unit | String(50) | e.g. "$3.50 / 100g" |
| created_at | DateTime | |

**price_history**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| product_id | FK → products | |
| price | Float | nullable (scrape may return None) |
| was_price | Float | nullable (original price before special) |
| in_stock | Boolean | |
| on_special | Boolean | |
| scrape_error | Boolean | True if scrape failed this run |
| scraped_at | DateTime | |

**watchlist**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| product_id | FK → products | |
| user_id | FK → users | nullable (legacy anonymous entries) |
| alert_drop_pct | Float | nullable — alert when price drops by this % |
| alert_price_below | Float | nullable — alert when price goes below this |
| notify_email | Boolean | |
| notify_push | Boolean | |
| created_at | DateTime | |

**alert_events**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| watchlist_entry_id | FK → watchlist | |
| trigger_type | String(50) | "drop_pct" / "price_below" / "back_in_stock" / "on_special" |
| old_price | Float | nullable |
| new_price | Float | nullable |
| triggered_at | DateTime | |
| notified_at | DateTime | nullable — set after successful notification delivery |

**notification_settings**
Singleton config table (one row). Stores Resend API key, ScraperAPI key, ntfy topic, email recipients, poll schedule, and global alert sensitivity thresholds. Keys stored here are loaded into the runtime cache (`config.py` module-level variables) at startup.

**shopping_lists / shopping_list_items**
Shopping list feature (beta). Each list item stores a search keyword; the background job can search all stores and populate `matched_results` (JSON) with best-match per store.

### Store Enum

```python
class Store(enum.Enum):
    woolworths            = "woolworths"
    coles                 = "coles"
    aldi                  = "aldi"
    harris_farm           = "harris_farm"           # legacy (kept for existing DB rows)
    harris_farm_cammeray  = "harris_farm_cammeray"
    harris_farm_mosman    = "harris_farm_mosman"
    harris_farm_lane_cove = "harris_farm_lane_cove"
    harris_farm_broadway  = "harris_farm_broadway"
    iga_crows_nest        = "iga_crows_nest"
    iga_milsons_point     = "iga_milsons_point"
    iga_north_sydney      = "iga_north_sydney"
    iga_newtown           = "iga_newtown"
    iga_king_st           = "iga_king_st"
```

Note: `harris_farm` is a legacy value kept to avoid breaking existing DB rows. All new entries use the location-specific slug (e.g., `harris_farm_broadway`).

## Routes (FastAPI)

### Page Routes
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Landing page — suburb selector, store checkboxes, search entry |
| `GET` | `/search` | Search results page (HTMX target for search form) |
| `GET` | `/watchlist` | Watchlist page — user's watched products with latest prices |
| `GET` | `/settings` | Settings page — notification config, ScraperAPI key, Resend key |
| `GET` | `/login` | Login form |
| `POST` | `/login` | Authenticate and create session |
| `GET` | `/register` | Registration form |
| `POST` | `/register` | Create user account |
| `POST` | `/logout` | Clear session |

### HTMX Partial Routes
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/search` | Returns `search.html` partial with grouped product results |
| `POST` | `/watchlist/add` | Add product to watchlist; returns inline ✓ confirmation HTML |
| `POST` | `/watchlist/remove/{id}` | Remove watchlist entry; returns empty response (removes row via HTMX `outerHTML` swap) |
| `POST` | `/watchlist/edit/{id}` | Update alert thresholds; returns updated row HTML |
| `POST` | `/settings/save` | Save notification settings; returns saved confirmation partial |
| `GET` | `/stores-for-suburb` | Returns store chip HTML for a given suburb (used by landing page suburb selector) |

### API / Debug Routes
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check: ScraperAPI configured, DB reachable |
| `GET` | `/debug/woolworths` | Diagnostic: test Woolworths scraper, return raw HTML length + product count |
| `GET` | `/debug/search-error` | Diagnostic: verify DB schema is consistent |

## Frontend Architecture

### Templates (`app/templates/`)
```
templates/
├── landing.html              # Main landing page (suburb selector, store grid)
├── search.html               # Search results + watchlist integration
├── watchlist.html            # Watchlist management page
├── settings.html             # Notification + API key settings
├── login.html / register.html
└── partials/
    ├── settings_saved.html   # HTMX swap target for settings save confirmation
    └── watchlist_edit_form.html  # Inline watchlist edit form (HTMX swap)
```

### Alpine.js State
The landing page uses Alpine.js `x-data` for:
- `selectedStores: []` — array of active store slugs
- `toggleStore(slug)` / `isSelected(slug)` — toggle + check helpers
- `savePreferences()` — persist `selectedStores` to localStorage
- `loadPreferences()` — restore on page load

The search page passes `selectedStores` as a hidden form field to the HTMX search POST. The server reads the store list and queries only those scrapers.

### HTMX Patterns
- Search form: `hx-post="/search" hx-target="#results" hx-swap="innerHTML"` — replaces the results div
- Watchlist add: `hx-post="/watchlist/add" hx-target="closest .watch-btn" hx-swap="outerHTML"` — replaces the button with a ✓ confirmation
- Settings save: `hx-post="/settings/save" hx-target="#save-status" hx-swap="innerHTML"` — shows "Saved ✓"

## Deployment

**Platform:** Railway (https://railway.app)

**Service layout:**
- One Railway service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Attached Neon PostgreSQL database (Railway Plugin)
- GitHub auto-deploy: `main` branch → Railway rebuilds on push

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Railway Variables required:**
| Variable | Required for |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection (auto-set by Railway Neon plugin) |
| `SESSION_SECRET_KEY` | Auth — must be set |
| `SCRAPERAPI_KEY` | Woolworths search |
| `RESEND_API_KEY` | Email alerts |

## Project Layout

```
supermarket-price-tracker/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, all routes, grouping logic
│   ├── models.py             # SQLAlchemy ORM models
│   ├── database.py           # Engine + Session + Base + init_db()
│   ├── config.py             # Settings (pydantic-settings) + runtime key cache
│   ├── suburbs.py            # Suburb → store slug mapping (600+ Sydney suburbs)
│   ├── geo.py                # Haversine distance + nearby_suburbs()
│   ├── unit_parser.py        # Parse cup/unit strings → normalised per-unit price
│   ├── scrapers/
│   │   ├── base.py           # BaseScraper ABC, SearchResult, PriceResult
│   │   ├── woolworths.py     # ScraperAPI + __NEXT_DATA__ parse
│   │   ├── coles.py          # Direct Coles JSON API
│   │   ├── harris_farm.py    # Shopify Predictive Search (per-location)
│   │   ├── iga.py            # Metcash Storefront API (per-store)
│   │   └── aldi.py           # HTML catalogue scrape
│   ├── notifiers/
│   │   ├── alerts.py         # Alert trigger logic
│   │   ├── email.py          # Resend API email sender
│   │   ├── push.py           # ntfy.sh push sender
│   │   └── shopping_email.py # Shopping list digest email
│   └── templates/
│       ├── landing.html
│       ├── search.html
│       ├── watchlist.html
│       ├── settings.html
│       ├── login.html
│       ├── register.html
│       └── partials/
│           ├── settings_saved.html
│           └── watchlist_edit_form.html
├── specs/                    # ← Spec-driven development documents
│   ├── mission.md
│   ├── tech-stack.md
│   ├── roadmap.md
│   └── YYYY-MM-DD-phase-name/
│       ├── requirements.md
│       ├── plan.md
│       └── validation.md
├── tests/
├── alembic/
├── Dockerfile
├── docker-compose.yml
├── railway.json
├── requirements.txt
├── manage.py                 # CLI: init-db, migrate, seed, scrape-now
└── .env.example
```

## Open Questions

1. **Woolworths ScraperAPI free tier.** Free tier (1000 req/month) triggers concurrency errors on Railway's shared IP. Paid plan ($49/month) needed for reliable Woolworths search. Until then, Woolworths returns empty results on Railway but works on residential IPs.

2. **Coles store-level pricing.** The Coles API returns national shelf prices. In-store specials (e.g., "half price at your local Coles only") require an authenticated Coles session tied to a postcode. Not currently implemented.

3. **Harris Farm online prices vs in-store.** Harris Farm's Shopify storefront shows online prices which may differ from in-store. No way to distinguish from the API.

4. **IGA stock data.** The Metcash API sometimes returns `in_stock: false` for items that are actually stocked in-store. Stock data accuracy varies by store.

5. **Aldi catalogue freshness.** Aldi updates their catalogue weekly. The scraper fetches the current week's catalogue, but there's no notification when a new catalogue drops. A scheduled weekly re-scrape would improve freshness.

6. **Database migration in prod.** Currently `init_db()` calls `Base.metadata.create_all()` which only creates missing tables. Schema changes require manual Alembic migration execution. A `manage.py migrate` command exists for this but isn't auto-run on deploy.
