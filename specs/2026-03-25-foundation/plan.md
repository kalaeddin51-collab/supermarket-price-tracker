# Plan — Phase 1: Foundation

Numbered task groups in implementation order. Each group is independently reviewable.

---

## Group 1 — Project Scaffold

1. Initialise Python project: `requirements.txt` with `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `sqlalchemy`, `alembic`, `python-dotenv`, `pydantic-settings`.
2. Create `app/__init__.py` (empty).
3. Create `app/config.py` — `Settings` class via `pydantic-settings`, reading from `.env`. Expose `settings` singleton.
4. Create `app/main.py` — `FastAPI()` instance, mount `app/static/` for static files, attach `Jinja2Templates(directory="app/templates")`.
5. Create `.env.example` documenting all variables: `DATABASE_URL`, `SESSION_SECRET_KEY`, `SCRAPERAPI_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO`, `NTFY_TOPIC`.
6. Create `Dockerfile` (Python 3.11-slim, `pip install -r requirements.txt`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`).
7. Create `railway.json` pointing at the Dockerfile.

## Group 2 — Database Layer

8. Create `app/database.py`:
   - `engine = create_engine(settings.database_url, ...)` with `connect_args={"check_same_thread": False}` for SQLite.
   - `SessionLocal = sessionmaker(...)` + `get_db()` FastAPI dependency.
   - `Base = declarative_base()`.
   - `init_db()` function calling `Base.metadata.create_all(engine)`.
9. Create `app/models.py` — define `User`, `UserPreference`, `Product`, `PriceRecord`, `WatchlistEntry`, `AlertEvent`, `NotificationSettings`, `ShoppingList`, `ShoppingListItem`.
10. Call `init_db()` in `main.py` on startup via `@app.on_event("startup")` or lifespan context.

## Group 3 — Authentication

11. Add `SessionMiddleware` to `app` in `main.py` with `secret_key=settings.session_secret_key`, `max_age=60*60*24*30`, `https_only=True`.
12. Implement `hash_password(password)` → bcrypt hash string.
13. Implement `verify_password(password, hashed)` → bool.
14. Implement `get_current_user(request, db)` → User | None (reads `user_id` from session).
15. Implement `require_user(request, db)` → User (raises 303 redirect to `/login` if not authenticated).
16. Create `GET /register` + `POST /register` routes: render `register.html`, create user, redirect to `/`.
17. Create `GET /login` + `POST /login` routes: render `login.html`, verify password, set `request.session["user_id"]`, redirect to `/`. Include login rate limiting (max 5 attempts / 15 min per IP).
18. Create `POST /logout` route: clear session, redirect to `/`.
19. Create `app/templates/login.html` and `app/templates/register.html`.

## Group 4 — Landing Page

20. Create `GET /` route in `main.py`:
    - Reads `request.session.get("user_id")` to determine auth state.
    - Passes store list and suburb options to the template.
21. Create `app/templates/landing.html`:
    - Header with logo, login/register links (or logout if authenticated).
    - Suburb text input with Alpine.js state.
    - Store checkbox grid (Woolworths, Coles, Aldi, Harris Farm, IGA) — Alpine.js `selectedStores` array.
    - Search form: HTMX `hx-post="/search" hx-target="#results" hx-swap="innerHTML"` with suburb + stores as hidden fields.
    - `#results` div (initially empty).

## Group 5 — Search Route (Skeleton)

22. Create `POST /search` route:
    - Accept `query: str`, `suburb: str`, `stores: str` (comma-separated slugs) from form data.
    - Return `search.html` with empty results list (scrapers wired in Phase 2).
23. Create `app/templates/search.html` — render product group cards, each with store name, price, per-unit price, and ☆ Watch button placeholder.

## Group 6 — Health + Debug Routes

24. Create `GET /health` → JSON: `{"status": "ok", "scraperapi_configured": bool}`.
25. Verify: `uvicorn app.main:app --reload`, visit `/` — landing page renders with Alpine.js store checkboxes functional.
26. Push to GitHub → confirm Railway build succeeds and `/health` returns 200.
