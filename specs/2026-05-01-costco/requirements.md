# Requirements — Costco Scraper

## Context

The app currently covers Woolworths, Coles, Aldi, Harris Farm, and IGA.
Costco Australia has two Sydney warehouses (Auburn, Marsden Park) and a
national online store at costco.com.au with publicly visible pricing.

## Scope

Add Costco as a searchable store in the price tracker.

### In scope
- New `CostcoScraper` that fetches search results from costco.com.au
- `costco` slug added to the `Store` enum, STORE_LABELS/COLORS/INFO, and ALL_STORE_SLUGS
- Costco included in all suburb store lists (national pricing, same as Aldi)
- Costco filter pill on the search page
- PostgreSQL enum migration so existing DB installs gain the new `costco` value
- Costco included in all shopping list search routes

### Out of scope
- Location-specific Costco slugs (Auburn vs Marsden Park) — online pricing is uniform nationally
- Membership-gated features — costco.com.au is publicly browsable without login
- Costco-specific unit parsing or category filtering (handled by generic logic)

## Key Decisions

### Single slug `costco` (not `costco_auburn` / `costco_marsden_park`)
Costco operates one national online store; prices are the same regardless of
which warehouse you visit. We follow the Aldi pattern: one slug, included for
all suburbs.

### Magento 2 HTML parsing (no JSON API)
Costco Australia's website is Magento 2. There is no public product JSON API.
We parse `li.product-item` HTML from the search results page, with a JSON-LD
fallback in case the HTML structure changes.

### ScraperAPI pass-through
Costco's site does not currently block cloud IPs, but we route through
ScraperAPI if a key is configured (consistent with other scrapers) so that
if blocking is introduced in future, enabling a key is sufficient.

### Pill colour `#E2231A`
Matches Costco's brand red used on their logo and website.

## Environment / Dependencies

No new dependencies. `beautifulsoup4` and `lxml` are already in requirements.txt.
