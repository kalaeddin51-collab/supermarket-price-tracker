# Requirements — Phase 1: Foundation

## Scope

Phase 1 establishes the complete project scaffold: web framework, database, auth, and the primary UI surfaces (landing + search). This phase is the base all subsequent phases build on.

## Decisions

### Web Framework
- **FastAPI** with Uvicorn as the ASGI server. Chosen for async-native HTTP handling (scrapers are all `async`), automatic request validation, and Jinja2 template integration.
- **Jinja2** templates for server-rendered HTML. No SPA framework — avoids a build step and keeps the server as the single source of truth for HTML.
- **HTMX** for partial page updates (search results replace the results div without a full page reload). No client-side JavaScript routing.
- **Alpine.js** for local UI state only (store checkbox selection, modal toggles). Loaded via CDN.

### Database
- **SQLAlchemy 2.0** with `mapped_column` / `Mapped` type annotations for type-safe ORM.
- **SQLite** (`prices.db`) locally; **PostgreSQL** (Neon via Railway) in production.
- `DATABASE_URL` environment variable switches between the two — no code changes.
- `init_db()` calls `Base.metadata.create_all()` at startup to create missing tables. Schema changes in later phases use Alembic migrations.

### Authentication
- Email + password auth. No third-party OAuth in MVP.
- Passwords hashed with **bcrypt** (passlib).
- Sessions via **Starlette SessionMiddleware** with signed cookies (HMAC). Cookie max-age: 30 days.
- `SESSION_SECRET_KEY` env var must be set to a long random string in production.
- Login rate limiting: 5 failed attempts within 15 minutes → IP locked out. Implemented in-memory (resets on restart — acceptable for MVP).

### Templates
- Base layout via Jinja2 `{% extends %}` (if needed) or self-contained templates per page.
- Landing page (`landing.html`): suburb text input, store checkboxes (Alpine.js), search button.
- Search page (`search.html`): HTMX target `#results`; renders product groups as cards.
- Login / register: standard form pages.

### Deployment
- **Railway** — single service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- `Dockerfile` (Python 3.11 slim) for Railway build.
- `railway.json` pointing at the Dockerfile.
- GitHub auto-deploy: push to `main` → Railway rebuilds.

## Context

This phase lays the structural foundation:
- The FastAPI app instance, middleware config, and template engine are shared by all later phases.
- The SQLAlchemy `Base` is imported by all model files in Phases 2–4.
- The session/auth system is used by Phases 3 (watchlist), 4 (saved preferences).

See `specs/mission.md` for domain context and `specs/tech-stack.md` for stack decisions.

## Out of Scope
- Store scrapers (Phase 2)
- Watchlist, alerts, price history (Phase 3)
- Suburb → store mapping, saved preferences (Phase 4)
- Email/push notification wiring (Phase 3)
