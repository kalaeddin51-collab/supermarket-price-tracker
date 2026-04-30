# Requirements — Phase 3: Watchlist & Alerts

## Scope

Phase 3 adds price tracking over time and proactive alerts. Users can save products to a watchlist, configure alert thresholds, and receive notifications via email or push when prices move.

## Decisions

### Watchlist Data Model
- `WatchlistEntry` links a `User` to a `Product`, with optional per-entry alert config.
- `Product` stores the product metadata (name, store, external_id, url, image, unit).
- `PriceRecord` stores a time-stamped price snapshot per product — this is the price history time-series.
- `AlertEvent` records each notification that fired: trigger type, old/new prices, notification timestamp.

### Alert Thresholds (per WatchlistEntry)
- `alert_drop_pct`: fire when `new_price < baseline_price * (1 - alert_drop_pct/100)`
- `alert_price_below`: fire when `new_price < alert_price_below`
- Either or both can be set. If both are set, either condition triggers an alert.
- Baseline price: the price at the time the item was added to the watchlist (first `PriceRecord`).

### Price Polling
- APScheduler `BlockingScheduler` configured in `main.py` startup.
- Poll job calls `scraper.fetch_price(external_id, url)` for each watchlist product.
- New `PriceRecord` created for each poll regardless of whether price changed.
- Alert conditions checked after each new `PriceRecord`. If threshold crossed, `AlertEvent` created and notification sent.
- Polling schedule: `daily` or `weekly`, configured in `NotificationSettings`. Default: weekly.

### Email Notifications (Resend)
- **Resend API** (not SMTP) — works on Railway without opening outbound SMTP ports.
- `resend.send_email()` from the `resend` Python package.
- API key stored in `NotificationSettings.resend_api_key` (loaded from env or via Settings UI).
- From address: must be a Resend-verified domain address. Falls back to `onboarding@resend.dev` for testing.
- Two email types:
  1. **Instant alert**: fired immediately when an alert condition is triggered. Single product, price details, direct link.
  2. **Digest**: weekly or daily summary of all watchlist items with current prices and any movements. Formatted as a price table.

### Push Notifications (ntfy.sh)
- `ntfy.sh` free tier: push via HTTP POST to `https://ntfy.sh/{topic}`.
- No authentication required for public topics. Topic name is the secret.
- `ntfy_topic` stored in `NotificationSettings`.
- Push fires for the same alert conditions as email (both can be enabled simultaneously).
- Push is best-effort: `ntfy.sh` downtime does not block price polling.

### Settings UI
- Settings page (`GET /settings`) renders all `NotificationSettings` fields as form inputs.
- `POST /settings/save` updates the DB record and refreshes the runtime key cache.
- ScraperAPI key and Resend key are editable in the Settings UI (not just env vars) for Railway deployments where the user doesn't want to redeploy to change keys.
- HTMX swap on save: "Saved ✓" confirmation appears inline without page reload.

### Watchlist UI
- Watchlist page (`GET /watchlist`) lists all entries for the current user with:
  - Latest price + baseline price
  - Price trend indicator (↑ / ↓ / =)
  - Alert threshold display
  - Inline edit form (HTMX swap) to update thresholds
  - Remove button (HTMX delete)
- ☆ Watch button on search results: HTMX `POST /watchlist/add` → server creates entry → button replaced with ✓ confirmation

### Auth Requirement
- Watchlist routes require authentication. Anonymous users are redirected to `/login`.
- `watchlist/add` gracefully handles the case where the user is not logged in (returns a "Please log in" message inline instead of a 401, since HTMX ignores non-2xx responses).

## Context
- `Product.store` uses the `Store` enum — validated at the database level (SAEnum).
- `external_id` is the store's own product identifier (Woolworths stockcode, Shopify variant ID, etc.).
- `fetch_price()` on each scraper must remain in sync with `search()` — the external_id format must be consistent.

See `specs/tech-stack.md` for notifier architecture details.

## Out of Scope
- Price history charts (Phase 5)
- Shopping list integration with watchlist (Phase 6)
- Multiple alert recipients per entry (current: global email_to setting only)
- Price prediction / "best time to buy" ML features
