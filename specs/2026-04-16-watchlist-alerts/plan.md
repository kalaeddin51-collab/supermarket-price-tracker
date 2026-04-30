# Plan — Phase 3: Watchlist & Alerts

Numbered task groups in implementation order. Each group is independently reviewable.

---

## Group 1 — Notifiers

1. Create `app/notifiers/__init__.py` (empty).
2. Create `app/notifiers/email.py`:
   - `send_alert_email(product_name, store, old_price, new_price, url, recipient)` — instant alert email via Resend API
   - `send_digest_email(entries, recipient)` — weekly/daily digest with price table
   - Import `resend` package; call `resend.Emails.send({...})` with API key from `get_resend_key()`
   - Handle Resend API errors gracefully — log, do not raise
3. Create `app/notifiers/push.py`:
   - `send_push(title, body, url, topic, server="https://ntfy.sh")` — HTTP POST to ntfy.sh
   - Use `httpx.post()` (sync, called from scheduler context)
4. Create `app/notifiers/alerts.py`:
   - `check_alerts(watchlist_entry, new_price_record, db)` — evaluate alert conditions
   - Compute baseline price: first `PriceRecord` for the product
   - Check `alert_drop_pct` threshold: `new_price < baseline * (1 - pct/100)`
   - Check `alert_price_below` threshold: `new_price < alert_price_below`
   - Check `on_special` and `back_in_stock` if global settings enable them
   - If any condition met: create `AlertEvent`, call email/push notifiers
5. Create `app/notifiers/shopping_email.py`:
   - `send_shopping_list_email(list_items, recipient)` — shopping list digest (Phase 6 preview)

## Group 2 — APScheduler Integration

6. In `main.py`, import `apscheduler.schedulers.asyncio.AsyncIOScheduler`.
7. On startup, instantiate scheduler and add jobs:
   - `poll_watchlist_prices` job: async function that iterates all `WatchlistEntry` rows, calls `scraper.fetch_price()` per product, saves new `PriceRecord`, calls `check_alerts()`.
   - `send_digest_email_job` job: runs on `NotificationSettings.digest_frequency` cadence.
8. Schedule both jobs based on `NotificationSettings` from DB. Re-read settings each time the job fires (so settings changes take effect without restart).
9. Add `manage.py` CLI command `scrape-now` to trigger a manual price poll for testing.

## Group 3 — Watchlist Routes

10. `POST /watchlist/add` route in `main.py`:
    - Accept form fields: `name`, `store`, `external_id`, `url`, `image_url`, `unit`
    - Look up or create `Product` row (match by `external_id` + `store`)
    - Create `WatchlistEntry` with `user_id` from session
    - Return inline HTML confirmation (HTMX `outerHTML` swap on the ☆ button)
    - If user not logged in: return "Please log in to watch items" HTML (HTTP 200, so HTMX swaps it)
    - Wrap in `try/except`: on DB error, return error message HTML (HTTP 200)
11. `GET /watchlist` route:
    - Require auth (redirect to `/login` if anonymous)
    - Query all `WatchlistEntry` for current user with `product` + `price_history` eager loaded
    - Pass `entries` with `latest_price()` and baseline price to `watchlist.html`
12. `POST /watchlist/remove/{id}` route:
    - Verify the entry belongs to the current user
    - Delete `WatchlistEntry` (cascades to `AlertEvent`)
    - Return empty `<span>` (HTMX `outerHTML` swap removes the row)
13. `POST /watchlist/edit/{id}` route:
    - Accept `alert_drop_pct` and `alert_price_below` form fields
    - Update the `WatchlistEntry` row
    - Return updated row HTML (HTMX swap)

## Group 4 — Settings Routes

14. `GET /settings` route:
    - Require auth
    - Query `NotificationSettings` row (create if missing)
    - Render `settings.html` with all settings fields
15. `POST /settings/save` route:
    - Accept all settings form fields
    - Upsert `NotificationSettings` row
    - Call `set_scraperapi_key()` and `set_resend_key()` to update runtime cache
    - Return `partials/settings_saved.html` partial (HTMX swap)

## Group 5 — Templates

16. Create `app/templates/watchlist.html`:
    - Authenticated only (redirect handled in route)
    - For each entry: product image, name, store pill, latest price, baseline, trend arrow
    - Inline edit form trigger (HTMX `hx-get="/watchlist/edit-form/{id}"`)
    - Remove button (HTMX `hx-delete="/watchlist/remove/{id}"`)
17. Create `app/templates/settings.html`:
    - Form sections: Email (Resend key, from address, recipients), Push (ntfy topic, server), Schedule (poll frequency, digest frequency), Thresholds (global min drop %, on-special toggle)
    - Save button: HTMX `hx-post="/settings/save" hx-target="#save-status"`
    - `#save-status` div shows `partials/settings_saved.html` on success
18. Create `app/templates/partials/settings_saved.html` — "✓ Saved" badge HTML snippet.
19. Create `app/templates/partials/watchlist_edit_form.html` — inline edit form for thresholds.
20. Update `search.html` ☆ Watch button:
    - `hx-post="/watchlist/add"`
    - Hidden fields: `name`, `store`, `external_id`, `url`, `image_url`, `unit`
    - `hx-target="closest .watch-btn" hx-swap="outerHTML"`

## Group 6 — Verification

21. Test: add a product to watchlist → appears on `/watchlist`
22. Test: `manage.py scrape-now` → new `PriceRecord` rows created
23. Test: manually set `alert_price_below` to current price − $0.01 → trigger `check_alerts()` → `AlertEvent` created
24. Test: if Resend key set, confirm test email arrives
25. Push to Railway; confirm APScheduler starts without error (check logs)
