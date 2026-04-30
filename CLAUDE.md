# CLAUDE.md — Supermarket Price Tracker

This file provides guidance to Claude Code when working in this repository.

## Project Overview

A FastAPI + HTMX + Alpine.js web app for comparing supermarket prices across Sydney stores. Deployed on Railway with PostgreSQL (Neon). See `specs/mission.md` for full context.

## Spec-Driven Development

This project follows a spec-driven development approach. Before implementing any new feature:

1. Check `specs/roadmap.md` to find the relevant phase
2. Read the phase's `requirements.md` for scope and decisions
3. Follow the `plan.md` for implementation order
4. Validate against `validation.md` before committing

When adding a new feature phase:
- Create `specs/YYYY-MM-DD-feature-name/requirements.md` — scope, decisions, context
- Create `specs/YYYY-MM-DD-feature-name/plan.md` — numbered implementation steps
- Create `specs/YYYY-MM-DD-feature-name/validation.md` — acceptance criteria

## Architecture Quick Reference

```
app/main.py         — FastAPI routes, product grouping, store labels/colors/info
app/models.py       — SQLAlchemy ORM models (User, Product, WatchlistEntry, ...)
app/config.py       — pydantic-settings + runtime key cache (get_scraperapi_key, get_resend_key)
app/suburbs.py      — suburb → store slug mapping (600+ Sydney suburbs)
app/geo.py          — haversine nearby_suburbs()
app/scrapers/       — one scraper class per store (woolworths, coles, harris_farm, iga, aldi)
app/notifiers/      — email (Resend), push (ntfy.sh), alert logic
app/templates/      — Jinja2 HTML templates
```

## Key Decisions & Gotchas

### Woolworths
- Akamai blocks all cloud/datacenter IPs. Requires `SCRAPERAPI_KEY` env var on Railway.
- Free ScraperAPI tier (1000 req/month) hits concurrency limits on shared Railway IPs → HTTP 499.
- Paid ScraperAPI plan required for reliable Woolworths search.
- Use `render=false` (not `render=true`) — headless browser adds 15–30s latency.
- Parse `__NEXT_DATA__` Next.js SSR JSON from HTML. No JSON API call needed.

### Harris Farm Store Slugs
- There is NO generic `harris_farm` slug for new data. Existing DB rows may have `harris_farm` (legacy).
- Always use location-specific slugs: `harris_farm_cammeray`, `harris_farm_mosman`, `harris_farm_lane_cove`, `harris_farm_broadway`.
- Any new checkbox or filter that toggles Harris Farm must handle **all** HF location slugs as a group.
- Template check: use `slug.startswith('harris_farm_')` not `slug == 'harris_farm'`.

### IGA Store Slugs
- Same multi-slug pattern as Harris Farm: `iga_north_sydney`, `iga_milsons_point`, `iga_crows_nest`, `iga_newtown`, `iga_king_st`.

### Jinja2 Loop Variables
- Jinja2 does NOT support variable mutation inside `{% for %}` loops.
- Use `{% set ns = namespace(var=initial_value) %}` and `{% set ns.var = new_value %}` for loop-scoped accumulators.
- This pattern is used in `search.html` for building the non-IGA pill list and detecting the Harris Farm slug.

### HTMX Error Handling
- HTMX ignores non-2xx responses and does NOT swap the target.
- For user-facing errors (auth required, DB error), always return HTTP 200 with error HTML, not a 4xx/5xx.
- Example: `/watchlist/add` returns "Please log in" as 200 HTML if the user is anonymous.

### SQLAlchemy Enum
- `Product.store` uses `SAEnum(Store)` which validates at the DB level.
- Adding a new store: update the `Store` enum in `models.py` AND create an Alembic migration.
- Never write raw string store slugs to `Product.store` — must match the enum.

### Session Auth
- Sessions via Starlette `SessionMiddleware` (signed cookies).
- `SESSION_SECRET_KEY` must be set in Railway Variables.
- `get_current_user(request, db)` returns None for anonymous users (never raises).
- `require_user(request, db)` raises 303 redirect to `/login` — use for pages that require auth.

## Environment Variables (Railway)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL (auto-set by Railway Neon plugin) |
| `SESSION_SECRET_KEY` | Session signing — must be random long string |
| `SCRAPERAPI_KEY` | Woolworths bot bypass (paid plan required) |
| `RESEND_API_KEY` | Email alerts |

## Local Development

```bash
cp .env.example .env
# Edit .env with your values

pip install -r requirements.txt
uvicorn app.main:app --reload
# App at http://localhost:8000
```

## Deployment

Push to `main` → Railway auto-deploys. Check Railway dashboard for build logs.

Health check: `GET /health` — returns ScraperAPI configured status + DB reachable.

Debug: `GET /debug/woolworths?q=milk` — tests Woolworths scraper, returns raw diagnostic JSON.
