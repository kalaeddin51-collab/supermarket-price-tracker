# Plan — Agentic Features

---

## Group 1 — Dependencies & Config

1. Add `anthropic` to `requirements.txt`
2. Add `anthropic_api_key: str = ""` to `Settings` in `app/config.py`
3. Add `get_anthropic_key()` / `set_anthropic_key()` runtime helpers to `config.py`
4. Add `ANTHROPIC_API_KEY=` to `.env.example`

---

## Group 2 — Data Model

5. Add `ConsumptionItem` model to `app/models.py`
   - `id`, `user_id` (FK users), `item_name`, `brand_preference` (nullable),
     `notes` (nullable), `created_at`
   - SQLite/Postgres: `create_all(checkfirst=True)` auto-creates table on startup

---

## Group 3 — AI Module

6. Create `app/ai/__init__.py` (empty)
7. Create `app/ai/agent.py`
   - `SCRAPER_MAP` dict: store slug → importable class path
   - `_store_display_name(slug)` helper
   - `_search_one_store_ai(store_slug, query, limit)` — single store, returns list[dict]
   - `search_stores(query, stores, limit)` — parallel across multiple stores
8. Create `app/ai/nl_search.py`
   - `NL_TOOLS` list (search_products tool schema)
   - `_format_profile(profile)` helper
   - `run_nl_search(query, profile, user_stores)` — agentic loop, returns {summary, results, error}
9. Create `app/ai/deal_detector.py`
   - `_search_for_specials(item_name, user_stores)` — search + filter on_special items
   - `find_deals(profile, user_stores, db)` — parallel search + Claude curation

---

## Group 4 — Routes (app/main.py)

10. `GET /profile` — render profile.html with user's ConsumptionItems
11. `POST /api/profile/items` — HTMX: add item, return updated items partial
12. `DELETE /api/profile/items/{id}` — HTMX: remove item, return updated items partial
13. `POST /api/nl-search` — HTMX: run NL search, return nl_results partial
14. `GET /partials/deals` — HTMX lazy load: run deal detector, return deals_panel partial

---

## Group 5 — Templates

15. Create `app/templates/profile.html` — consumption profile management page
16. Create `app/templates/partials/consumption_items.html` — item list (HTMX swap target)
17. Create `app/templates/partials/nl_results.html` — NL search results partial
18. Create `app/templates/partials/deals_panel.html` — curated deals cards
19. Update `app/templates/search.html`:
    - Add lazy-loading deals panel (hx-get="/partials/deals" hx-trigger="load")
    - Add "✨ Ask AI" toggle button + NL search input (Alpine x-show)
    - HTMX posts to /api/nl-search, swaps result into #search-results
20. Update `app/templates/base.html` — add "Profile" nav item

---

## Group 6 — Deploy

21. Commit all changes
22. Push to `main` → Railway auto-deploys
23. Set `ANTHROPIC_API_KEY` in Railway Variables
