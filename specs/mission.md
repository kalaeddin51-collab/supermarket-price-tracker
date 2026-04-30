# Supermarket Price Tracker — Mission

## Overview

**Supermarket Price Tracker** is a web application that lets Sydney households compare grocery prices across major supermarkets in real time and receive automatic alerts when watched products drop in price.

The app:

1. **Searches** product catalogues across Woolworths, Coles, Aldi, Harris Farm, and IGA simultaneously, returning ranked results with per-unit price comparisons
2. **Groups** matching products across stores so shoppers can see side-by-side prices for the same item in a single row
3. **Watches** products a user selects, recording price history over time
4. **Alerts** users via email (Resend API) or push notification (ntfy.sh) when a watched product drops below a threshold or goes on special
5. **Surfaces nearby stores** based on the user's Sydney suburb, so results are relevant to where they shop

## Motivation

Grocery prices in Australia are volatile and opaque. The major supermarkets (Woolworths, Coles) actively prevent price comparison by restricting API access and deploying bot-protection (Akamai). Independent stores like Harris Farm and IGA use completely different technology stacks. No single free tool gives a Sydney household a unified, real-time comparison.

Specific problems this solves:

- **No unified view.** Shoppers must visit 4–5 separate websites and remember prices manually to compare.
- **Specials are easy to miss.** A product may go on special for only one week; by the time a shopper visits that store, the deal is gone.
- **Location matters.** A Woolworths shopper in Mosman and a Woolworths shopper in Penrith face completely different store contexts. Results should reflect the suburb the shopper actually lives in.
- **Harris Farm is worth watching.** Harris Farm carries premium produce at competitive prices, but is excluded from mainstream comparison tools because it isn't a publicly listed company with API access.

## User Personas

### The Weekly Shopper
Does one big grocery run per week. Wants to know in advance whether to go to Woolworths or Coles for their staples, and whether Harris Farm is cheaper for produce this week.

### The Brand-Loyal Switcher
Buys specific brands but is open to switching stores when their preferred brand is on special. Wants a watchlist alert when "Barilla Pasta 500g" drops below $2.50 at any store.

### The Budget Tracker
Manages a strict household food budget. Wants a weekly digest email showing price movements for their regular 15–20 items, with the cheapest store highlighted.

## Store Coverage

| Store | Coverage | API Method | Status |
|-------|----------|-----------|--------|
| **Woolworths** | Nationwide (uniform pricing) | ScraperAPI → `__NEXT_DATA__` HTML parse | ⚠️ Requires paid ScraperAPI plan on Railway |
| **Coles** | Nationwide (uniform pricing) | Direct JSON search API | ✅ Working |
| **Aldi** | Nationwide (weekly specials catalogue only) | HTML catalogue scrape | ✅ Working |
| **Harris Farm** | Sydney stores only | Shopify Predictive Search API (per-location slug) | ✅ Working |
| **IGA** | Sydney stores only | Metcash Storefront API (per-store store_id) | ✅ Working |

## Product Model

Each search returns `SearchResult` objects that are grouped by product similarity for cross-store comparison:

- **Name matching:** Products are grouped when names share ≥65% key words and the same brand, excluding size/weight suffixes so "Milk 2L" and "Milk 3L" stay separate groups
- **Per-unit pricing:** Unit prices (per 100g, per L, per ea) are parsed and displayed to allow fair comparison across different pack sizes
- **Price history:** When a user watches a product, prices are scraped on a schedule (daily or weekly) and stored in a time-series table

## Core User Journey

```
Landing Page
  → Enter suburb OR allow location → Nearby stores shown
  → Select stores to include
  → Search for a product
  → Results page: grouped products, cheapest store first, savings highlighted
  → Click ☆ Watch → Watchlist entry created
  → Alert fires when price drops (email or push)
  → Click product → Full price history shown
```

## Constraints and Key Decisions

### Woolworths Bot Protection
Woolworths uses Akamai bot detection that blocks all cloud-datacenter IP ranges (Railway, AWS, GCP). The HTML search page (`/shop/search/products`) embeds product data in a `__NEXT_DATA__` JSON block. ScraperAPI residential proxies bypass Akamai; `render=false` (static HTML, no headless browser) reduces latency to ~5–10s.

### No Playwright / Headless Browsers
Headless browsers are too slow (15–30s per request), consume excessive memory on Railway free tier, and are reliably blocked by Akamai regardless.

### SQLite in Dev, PostgreSQL in Prod
SQLite requires zero infrastructure for local development. Railway's PostgreSQL service (Neon) provides production persistence. SQLAlchemy abstracts the difference.

### Session-based Auth (No JWT)
Starlette `SessionMiddleware` with signed cookies. Simple for this use case; no need for stateless JWT since the server is single-process on Railway.

### HTMX + Alpine.js (No SPA Framework)
Server-rendered Jinja2 templates with HTMX for partial page updates (search results load without full reload) and Alpine.js for local UI state (store checkbox selection, watchlist badge toggling). Zero JavaScript build step required.

## Success Metrics

| Metric | Target |
|--------|--------|
| Search response time (p95) | < 8 seconds (across 3+ stores) |
| Watchlist alert delivery time | < 5 minutes after price scrape |
| Suburb coverage | ≥ 90% of Sydney LGAs |
| Store scraper uptime | Coles + Harris Farm + IGA: 99%; Woolworths: best-effort (ScraperAPI dependency) |
| Price accuracy | Scraped price matches live store price within the same calendar day |

## Scope

### Delivered (v0.4, April 2026)
- Multi-store search with product grouping and per-unit price comparison
- Suburb-based nearby store selection (600+ Sydney suburbs)
- User accounts with saved suburb and store preferences
- Watchlist with configurable drop % and below-price alerts
- Price history recording per product
- Email alerts via Resend API
- Push alerts via ntfy.sh
- Weekly/daily digest email
- Shopping list (beta)
- Railway deployment (PostgreSQL, auto-deploy from GitHub)

### Deferred
- **Woolworths reliable search** — blocked on paid ScraperAPI plan ($49/month)
- **Price history charts** — time-series charts per watchlist product
- **Coles store-level pricing** — Coles API returns national prices; store-specific pricing requires authenticated session
- **Aldi weekly specials calendar** — automated catalogue parsing
- **Mobile PWA** — offline support, home screen install, push via VAPID
- **Multiple users / households** — currently single-account-focused
- **Social proof** — "3 people are watching this" popularity signals
