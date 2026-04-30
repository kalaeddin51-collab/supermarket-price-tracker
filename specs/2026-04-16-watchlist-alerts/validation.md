# Validation — Phase 3: Watchlist & Alerts

Phase 3 is complete and ready to merge when all criteria below pass.

---

## 1. Watchlist Flow (Browser)

- [ ] Anonymous user: click ☆ Watch on a search result → inline "Please log in to watch items" message appears (no page reload, no 401)
- [ ] Logged-in user: click ☆ Watch → button replaced with "✓ Watching" confirmation (HTMX swap)
- [ ] `/watchlist` shows the added product with latest price (scrape price may be None if no poll has run yet)
- [ ] Edit alert threshold: inline form appears, save → row updates without page reload
- [ ] Remove: watchlist row disappears on click (HTMX outerHTML removes it)
- [ ] Attempting to watch the same product twice: second click should not create a duplicate entry (idempotent add)

---

## 2. Settings

- [ ] `GET /settings` → HTTP 200, settings form renders with current values
- [ ] `POST /settings/save` → "✓ Saved" confirmation appears inline
- [ ] After save: `NotificationSettings` row updated in DB (verify via SQL or `/debug/search-error`)
- [ ] ScraperAPI key entered in Settings UI takes effect immediately for the next search (check `/health` endpoint shows `scraperapi_configured: true`)

---

## 3. Price Polling

```bash
python manage.py scrape-now
```

- Runs without error
- At least one new `PriceRecord` row created per watched product
- `AlertEvent` created if price crossed a threshold (verify in DB: `SELECT * FROM alert_events`)

---

## 4. Alert Delivery

With a valid Resend API key configured:
- Manually lower `alert_price_below` on a watchlist entry to below the current price
- Run `manage.py scrape-now`
- [ ] `AlertEvent` row created with `trigger_type = 'price_below'`
- [ ] Email arrives at the configured recipient (may take up to 2 minutes via Resend)
- [ ] ntfy.sh push arrives if topic configured (verify on https://ntfy.sh/{topic})

---

## 5. Error Handling

- [ ] DB error in `/watchlist/add` (e.g., invalid store enum value): returns visible error message HTML, not a 500
- [ ] Resend API failure (wrong key): `AlertEvent` created, `notified_at` remains null, error logged — scheduler continues
- [ ] One `fetch_price()` failure: other watchlist products still polled (no full job abort)

---

## 6. Manual Checklist

- [ ] APScheduler job appears in Railway logs on startup: "Added job 'poll_watchlist_prices'..."
- [ ] `watchlist.html` renders correctly with 0 watched items ("Your watchlist is empty" state)
- [ ] `watchlist.html` renders correctly with 3+ watched items (multiple rows, no layout breakage)
- [ ] Settings form survives a round-trip: save → reload page → saved values still shown
