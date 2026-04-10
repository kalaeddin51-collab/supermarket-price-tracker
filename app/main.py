import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
import bcrypt

from app.config import settings, get_scraperapi_key, set_scraperapi_key
from app.database import get_db, init_db
from app import models
from app.suburbs import SUBURB_STORES, ALL_SUBURBS, POSTCODE_NAMES
from app.geo import nearby_suburbs

app = FastAPI(title="Supermarket Price Tracker")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key, max_age=60*60*24*30, https_only=True)

# Simple in-memory rate limiter: track failed login attempts per IP
_login_attempts: dict[str, list] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60  # 15 minutes

def _base_name(n: str) -> str:
    """Strip trailing size/weight tokens for grouping watchlist entries."""
    return re.sub(r"\s+\d+(\.\d+)?\s*(ml|l|g|kg|pk|pack|x\d+)$", "", n.strip(), flags=re.IGNORECASE).lower().strip()


def _names_similar(name_a: str, name_b: str, threshold: float = 0.6) -> bool:
    """Return True if name_b shares enough key words with name_a."""
    stop = {"the", "a", "an", "and", "of", "with", "for", "in", "at", "co", "x"}
    def words(n):
        return {w.lower() for w in re.sub(r"[^a-z0-9 ]", "", n.lower()).split() if w not in stop and len(w) > 1}
    a, b = words(name_a), words(name_b)
    if not a:
        return True
    overlap = len(a & b) / len(a)
    return overlap >= threshold


def _check_rate_limit(ip: str) -> bool:
    """Return True if IP is locked out."""
    now = datetime.utcnow()
    attempts = _login_attempts.get(ip, [])
    # Drop attempts older than the lockout window
    attempts = [t for t in attempts if (now - t).total_seconds() < _LOCKOUT_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= _MAX_ATTEMPTS

def _record_failed_attempt(ip: str):
    _login_attempts.setdefault(ip, []).append(datetime.utcnow())

def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)
templates = Jinja2Templates(directory="app/templates")

@app.get("/health")
async def health_check():
    """Quick health/debug endpoint."""
    try:
        import playwright  # noqa
        playwright_ok = True
    except ImportError:
        playwright_ok = False
    return {
        "status": "ok",
        "scraperapi_configured": bool(get_scraperapi_key()),
        "scraperapi_key_prefix": get_scraperapi_key()[:6] + "..." if get_scraperapi_key() else "",
        "proxy_configured": bool(settings.scraper_proxy),
        "playwright_available": playwright_ok,
        "use_playwright": settings.use_playwright,
    }


@app.get("/debug/woolworths")
async def debug_woolworths(q: str = "milk"):
    """Debug endpoint: test Woolworths scraper and return raw response details."""
    import httpx as _httpx
    from app.config import get_scraperapi_key
    from app.scrapers.woolworths import WoolworthsScraper, _scraperapi_url, WOW_HOME

    scraper = WoolworthsScraper()
    debug_info = {}

    try:
        # 1. Get build ID
        build_id = await scraper._get_build_id()
        debug_info["build_id"] = build_id

        # 2. Fetch the Next.js data endpoint raw
        client = await scraper._get_client()
        target = (
            f"{WOW_HOME}/_next/data/{build_id}/shop/search/products.json"
            f"?searchTerm={q}"
        )
        api_url = _scraperapi_url(target)
        r = await client.get(api_url)
        debug_info["status_code"] = r.status_code
        debug_info["response_len"] = len(r.text)

        try:
            data = r.json()
            page_props = data.get("pageProps", {}) or {}
            debug_info["page_props_keys"] = list(page_props.keys())[:20]
            sr = page_props.get("searchResults") or page_props.get("search") or {}
            if isinstance(sr, dict):
                debug_info["searchResults_keys"] = list(sr.keys())[:10]
                bundles = sr.get("Products", [])
                debug_info["product_bundle_count"] = len(bundles)
                if bundles:
                    debug_info["first_bundle_keys"] = list(bundles[0].keys()) if isinstance(bundles[0], dict) else str(type(bundles[0]))
        except Exception as je:
            debug_info["json_error"] = str(je)
            debug_info["raw_snippet"] = r.text[:500]

        await scraper.close()
        return {"status": "ok", **debug_info}

    except Exception as exc:
        import traceback as _tb
        try:
            await scraper.close()
        except Exception:
            pass
        return JSONResponse(
            status_code=200,  # return 200 so the response body is readable
            content={"status": "error", "error": str(exc),
                     "debug": debug_info,
                     "traceback": _tb.format_exc()[-2000:]}
        )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

STORE_LABELS = {
    "woolworths": "Woolworths",
    "coles": "Coles",
    "harris_farm": "Harris Farm",
    "iga_crows_nest": "IGA Crows Nest",
    "iga_milsons_point": "IGA Milsons Point",
    "iga_north_sydney": "IGA North Sydney",
}

STORE_COLORS = {
    "woolworths": "#007D40",
    "coles": "#E31A2F",
    "harris_farm": "#F27200",
    "iga_crows_nest": "#D2232A",
    "iga_milsons_point": "#D2232A",
    "iga_north_sydney": "#D2232A",
}


ALL_STORE_SLUGS = [
    "woolworths", "coles", "harris_farm",
    "iga_north_sydney", "iga_milsons_point", "iga_crows_nest",
]


async def _search_one_store(store_slug: str, query: str):
    """Search a single store and return the top SearchResult, or None."""
    try:
        if store_slug == "woolworths":
            from app.scrapers.woolworths import WoolworthsScraper as Cls
        elif store_slug == "coles":
            from app.scrapers.coles import ColesScraper as Cls
        elif store_slug == "harris_farm":
            from app.scrapers.harris_farm import HarrisFarmScraper as Cls
        elif store_slug == "iga_north_sydney":
            from app.scrapers.iga import IGANorthSydneyScraper as Cls
        elif store_slug == "iga_milsons_point":
            from app.scrapers.iga import IGAMilsonsPointScraper as Cls
        elif store_slug == "iga_crows_nest":
            from app.scrapers.iga import IGACrowsNestScraper as Cls
        else:
            return None
        scraper = Cls()
        results = await scraper.search(query, limit=1)
        await scraper.close()
        return results[0] if results else None
    except Exception:
        return None


def _extract_brand(name: str) -> str:
    """Extract the brand name from a product title (first 1–2 significant words)."""
    import re
    words = name.split()
    if not words:
        return "Other"
    first = words[0]
    # Two-word brands: first word is short (≤3 chars) like "La", "Red", "St"
    # or both first two words are capitalised and non-numeric
    if (len(words) > 1
            and not re.match(r'^\d', words[1])
            and words[1][0].isupper()
            and (len(first) <= 3 or first.lower() in ("uncle", "mrs", "mr", "dr", "mc"))):
        return f"{first} {words[1]}"
    return first


def _time_ago(dt: datetime) -> str:
    if not dt:
        return "never"
    diff = datetime.utcnow() - dt
    if diff.seconds < 3600:
        return f"{diff.seconds // 60}m ago"
    if diff.days == 0:
        return f"{diff.seconds // 3600}h ago"
    return f"{diff.days}d ago"


def _sparkline_points(prices: list[float], width=80, height=28) -> str:
    """Convert a list of prices to SVG polyline points string."""
    if len(prices) < 2:
        return ""
    mn, mx = min(prices), max(prices)
    rng = mx - mn or 1
    pts = []
    for i, p in enumerate(prices):
        x = round(i / (len(prices) - 1) * width, 1)
        y = round(height - ((p - mn) / rng) * (height - 4) - 2, 1)
        pts.append(f"{x},{y}")
    return " ".join(pts)


def _store_key(s):
    """Accept both enum instances and plain strings."""
    return s.value if hasattr(s, "value") else str(s)


# Keywords that indicate a product is processed rather than fresh
_PROCESSED_KEYWORDS = re.compile(
    # Canned / bottled / preserved
    r'\b(canned|tinned|pickled|jarred|preserved'
    r'|paste|puree|concentrate|condensed|sauce|relish|chutney)\b'
    # Cured / dried / treated
    r'|\b(smoked|dried|dehydrated|cured|fermented)\b'
    # Potato & produce snack / processed products
    r'|\b(chips|crisps|fries|wedges|gratin|hash.?brown|instant|stix|crackers|tots)\b'
    # Packaged prepared / pre-cooked produce and meals
    r'|\b(frozen|battered|crumbed|crumble|coated|breaded|marinated|seasoned|flavoured|flavored)\b'
    r'|\b(slow.?cooked|pre.?cooked|ready.?to.?eat|ready.?meal)\b'
    # Stock / soup bases
    r'|\b(stock.?pot|stock.?cube|bouillon|bone.?broth)\b'
    # Processed / cured meats
    r'|\b(bacon|salami|pepperoni|chorizo|prosciutto|pancetta|pastrami|mortadella'
    r'|frankfurter|frankfurt|hot.?dog|sausage|bratwurst|biltong|jerky'
    r'|devon|luncheon|spam|twiggy|cabanossi|kabana|ham)\b'
    r'|\b(schnitzel|schnitzels)\b'
    # Snack / pet food context
    r'|\b(dog treat|cat treat|pet food|snack pack|multipack)\b'
    # "in X" liquid / sauce descriptors (marinated / braised / pre-cooked)
    r'|in (brine|oil|water|tomato|springwater|olive oil|syrup|juice|gravy|cream|broth)'
    # "In Onion & Red Wine", "In Red Wine", "In White Wine" style names
    r'|in (?:\w+ (?:& )?)?(?:red|white|rose) wine'
    r'|in (?:onion|garlic|herb|lemon|mustard|pepper|sweet chilli|teriyaki)',
    re.IGNORECASE,
)
_PROCESSED_CATEGORIES = re.compile(
    r'canned|tinned|pantry|condiment|preserve|pickle|sauce|snack|frozen|deli|pet',
    re.IGNORECASE,
)


def _calc_store_totals(sl) -> list:
    """
    Recalculate basket totals across stores from a ShoppingList's matched_results.
    Each item contributes at most ONE store entry (already enforced by _build_store_best).
    """
    from app.unit_parser import basket_cost as calc_basket_cost
    store_totals: dict[str, float] = {}
    store_item_counts: dict[str, int] = {}
    total_items = len(sl.items)
    for item in sl.items:
        results = []
        if item.matched_results:
            try:
                results = json.loads(item.matched_results)
            except Exception:
                results = []
        # results already has at most one entry per store (from _build_store_best)
        seen_stores: set = set()
        for r in results:
            store = r.get("store", "")
            price = r.get("price")
            if not price or not store or store in seen_stores:
                continue
            seen_stores.add(store)
            cost = calc_basket_cost(
                float(price), r.get("unit", ""),
                float(item.qty or 1.0), item.unit or "",
            )
            store_totals[store] = store_totals.get(store, 0.0) + cost
            store_item_counts[store] = store_item_counts.get(store, 0) + 1
    return [
        (store, round(total, 2), store_item_counts.get(store, 0), total_items)
        for store, total in sorted(store_totals.items(), key=lambda x: x[1])
    ]


def _build_store_best(all_results):
    """
    For each store keep the single best-value result, then split by unit category.

    Key rule: price/mL and price/g are NOT comparable numbers — a $4.50/500g product
    must NOT beat a $14/L product just because 0.009 < 0.014 in different base units.
    We therefore detect the DOMINANT unit category across all results and prefer that
    category when selecting the per-store winner.  Only if a store has no result in
    the dominant category do we fall back to its best result in any category.

    Additionally, results whose per-unit price is >8× the median within their
    category are treated as outliers (e.g. a 10-can catering pack slipping in) and
    dropped from per-store selection (but they still appear in display groups if they
    survived relevance filtering upstream).

    Returns (sorted_volume, sorted_weight, sorted_count, all_sorted)
    where all_sorted has at most one entry per store.
    """
    from app.unit_parser import comparison_key, per_unit_price as calc_per_unit, parse_unit
    from collections import Counter

    if not all_results:
        return [], [], [], []

    # ── Build enriched entry list ─────────────────────────────────────────────
    entries: list[dict] = []
    for r in all_results:
        price = r.price
        if price is None:
            continue
        _, cat = parse_unit(r.unit or "")
        ckey = comparison_key(float(price), r.unit or "")
        _, pu_label = calc_per_unit(float(price), r.unit or "")
        entries.append({
            "store":         r.store,
            "name":          r.name,
            "price":         float(price),
            "unit":          r.unit or "",
            "unit_cat":      cat,
            "per_unit_label": pu_label,
            "image_url":     r.image_url or "",
            "external_id":   r.external_id,
            "url":           r.url,
            "_ckey":         ckey,
        })

    # ── Dominant category ─────────────────────────────────────────────────────
    known_cats = [e["unit_cat"] for e in entries
                  if e["unit_cat"] in ("volume", "weight", "count")]
    dominant_cat = Counter(known_cats).most_common(1)[0][0] if known_cats else None

    # ── Outlier filter within the dominant category ───────────────────────────
    # Drop results whose per-unit cost is >8× the median in that category.
    outlier_ids: set[int] = set()
    if dominant_cat:
        dom_keys = sorted(
            e["_ckey"] for e in entries
            if e["unit_cat"] == dominant_cat and e["_ckey"] > 0
        )
        if len(dom_keys) >= 2:
            median_key = dom_keys[len(dom_keys) // 2]
            cutoff     = median_key * 8.0
            outlier_ids = {
                id(e) for e in entries
                if e["unit_cat"] == dominant_cat and e["_ckey"] > cutoff
            }

    # ── Per-store best: prefer dominant category, fall back if none ───────────
    # store → {cat → best_entry}
    store_by_cat: dict[str, dict[str, dict]] = {}
    for e in entries:
        if id(e) in outlier_ids:
            continue
        store, cat = e["store"], e["unit_cat"]
        if store not in store_by_cat:
            store_by_cat[store] = {}
        prev = store_by_cat[store].get(cat)
        if prev is None or e["_ckey"] < prev["_ckey"]:
            store_by_cat[store][cat] = e

    store_best: dict[str, dict] = {}
    for store, cat_bests in store_by_cat.items():
        if dominant_cat and dominant_cat in cat_bests:
            store_best[store] = cat_bests[dominant_cat]
        else:
            # No result in dominant category for this store — take overall best
            store_best[store] = min(cat_bests.values(), key=lambda x: x["_ckey"])

    all_sorted = sorted(store_best.values(), key=lambda x: x["_ckey"])
    for res in all_sorted:
        res.pop("_ckey", None)

    sorted_volume = [r for r in all_sorted if r["unit_cat"] == "volume"]
    sorted_weight = [r for r in all_sorted if r["unit_cat"] == "weight"]
    sorted_count  = [r for r in all_sorted if r["unit_cat"] not in ("volume", "weight")]
    return sorted_volume, sorted_weight, sorted_count, all_sorted


# Prepositions that indicate the query term is an ingredient/descriptor, not the main product
_INGREDIENT_PREPS = re.compile(
    r'\b(in|with|and|contains|infused with|flavou?red with|packed in|preserved in|'
    r'marinated in|cooked in|basted in|drizzled with|tossed in|coated in|'
    r'bathed in|soaked in|dressed with|served with|topped with|filled with)\b',
    re.IGNORECASE,
)


def _relevance_score(name: str, query: str) -> float:
    """
    Score how relevant a product name is to the search query (0.0–1.0).
    Penalises products where the query terms appear only as an ingredient/descriptor
    rather than as the primary subject of the product name.
    """
    name_lower = name.lower().strip()
    query_lower = query.lower().strip()
    query_words = query_lower.split()

    # Must contain all query words somewhere
    if not all(w in name_lower for w in query_words):
        return 0.0

    # Find position of the full query phrase (or first word)
    phrase_pos = name_lower.find(query_lower)
    word_pos = name_lower.find(query_words[0]) if query_words else 0

    pos = phrase_pos if phrase_pos >= 0 else word_pos

    # Check if a preposition precedes the query term — marks it as an ingredient
    prefix = name_lower[:pos].strip() if pos > 0 else ""
    if prefix and _INGREDIENT_PREPS.search(prefix):
        return 0.15  # Strong penalty — query is an ingredient/descriptor

    name_words = name_lower.split()

    # Full phrase starts the product name → best match
    if phrase_pos == 0:
        return 1.0

    # All query words are the first N words (ignoring leading brand words)
    if len(name_words) >= len(query_words):
        if name_words[:len(query_words)] == query_words:
            return 0.95

    # Query phrase appears early in the name (within first 3 words worth of chars)
    first_three = " ".join(name_words[:3])
    if query_lower in first_three:
        return 0.80

    # Query phrase present but not at the start
    if phrase_pos > 0:
        return 0.55

    # All words present but not as a contiguous phrase
    return 0.40


def _is_processed(name: str, category: str | None) -> bool:
    """Return True if the product appears to be canned/processed rather than fresh."""
    if _PROCESSED_KEYWORDS.search(name):
        return True
    if category and _PROCESSED_CATEGORIES.search(category):
        return True
    return False

templates.env.globals["store_label"] = lambda s: STORE_LABELS.get(_store_key(s), _store_key(s).replace("_", " ").title())
templates.env.globals["store_color"] = lambda s: STORE_COLORS.get(_store_key(s), "#666")
templates.env.globals["time_ago"] = _time_ago
templates.env.globals["sparkline_points"] = _sparkline_points
templates.env.globals["now"] = datetime.utcnow
templates.env.globals["enumerate"] = enumerate

# Make basket_cost available in all templates so items can show normalised prices
from app.unit_parser import basket_cost as _basket_cost_fn
templates.env.globals["basket_cost"] = _basket_cost_fn


# ─────────────────────────────── AUTH ROUTES ────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {
        "page": "login",
        "error": request.session.pop("auth_error", None),
        "success": request.session.pop("auth_success", None),
        "prefill_email": request.session.pop("prefill_email", ""),
    })


@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    if _check_rate_limit(ip):
        request.session["auth_error"] = "Too many failed attempts. Please wait 15 minutes and try again."
        request.session["prefill_email"] = email
        return RedirectResponse("/login", status_code=303)
    user = db.query(models.User).filter(models.User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        _record_failed_attempt(ip)
        request.session["auth_error"] = "That email or password is incorrect. Please try again."
        request.session["prefill_email"] = email
        return RedirectResponse("/login", status_code=303)
    _clear_attempts(ip)
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "register.html", {
        "page": "register", "error": request.session.pop("auth_error", None)
    })


@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    if db.query(models.User).filter(models.User.email == email).first():
        request.session["auth_error"] = "An account with that email already exists."
        return RedirectResponse("/register", status_code=303)
    user = models.User(
        name=name.strip(),
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    request.session["auth_success"] = "Account created! Sign in to continue."
    request.session["prefill_email"] = email
    return RedirectResponse("/login", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/api/suburb", response_class=JSONResponse)
async def get_suburb(request: Request, db: Session = Depends(get_db)):
    """Return the current user's saved suburb for the navbar."""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"suburb": ""})
    pref = db.query(models.UserPreference).filter(
        models.UserPreference.user_id == user_id
    ).first()
    return JSONResponse({"suburb": pref.suburb or "" if pref else ""})


@app.post("/api/send-test-email", response_class=JSONResponse)
async def send_test_email(request: Request, db: Session = Depends(get_db)):
    """Send a test digest email using the saved SMTP settings."""
    import os
    ns = db.query(models.NotificationSettings).first()
    if not ns or not ns.email_address:
        return JSONResponse({"ok": False, "error": "No recipient email configured in Settings."})

    recipients = [a for a in [ns.email_address, ns.email_address_2, ns.email_address_3] if a]

    # Use DB-stored credentials if env vars not set
    if ns.smtp_user:
        os.environ.setdefault("SMTP_USER", ns.smtp_user)
    if ns.smtp_password:
        os.environ.setdefault("SMTP_PASSWORD", ns.smtp_password)

    from app.notifiers.email import send_digest, build_digest_html
    # Build a sample digest
    html = build_digest_html([])  # empty — just a connectivity test
    # Override with a simple test body
    html = html.replace("<tbody></tbody>", "<tbody><tr><td colspan='4' style='padding:16px;text-align:center;color:#059669;font-weight:600'>✅ Test email from Price Tracker — everything is working!</td></tr></tbody>")
    ok = send_digest("Price Tracker — Test Email", html, recipients)
    if ok:
        return JSONResponse({"ok": True, "message": f"Test email sent to {', '.join(recipients)}"})
    else:
        return JSONResponse({"ok": False, "error": "Send failed — check your SMTP credentials in Settings."})


@app.post("/api/send-test-push", response_class=JSONResponse)
async def send_test_push(request: Request, db: Session = Depends(get_db)):
    """Send a test push notification via ntfy.sh."""
    ns = db.query(models.NotificationSettings).first()
    if not ns or not ns.ntfy_topic:
        return JSONResponse({"ok": False, "error": "No ntfy topic configured in Settings."})

    from app.notifiers.push import send_push
    ok = send_push(
        topic=ns.ntfy_topic,
        title="Price Tracker — Test Notification",
        message="✅ Push notifications are working!",
        server=ns.ntfy_server or "https://ntfy.sh",
        tags=["white_check_mark"],
    )
    if ok:
        return JSONResponse({"ok": True, "message": f"Push sent to ntfy topic: {ns.ntfy_topic}"})
    else:
        return JSONResponse({"ok": False, "error": "Push failed — check your ntfy topic in Settings."})


@app.post("/api/preferences", response_class=JSONResponse)
async def save_preferences(
    request: Request,
    db: Session = Depends(get_db),
    suburb: str = Form(default=""),
    stores: str = Form(default=""),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"ok": False}, status_code=401)
    pref = db.query(models.UserPreference).filter(models.UserPreference.user_id == user_id).first()
    if pref:
        pref.suburb = suburb
        pref.stores = stores
        pref.updated_at = datetime.utcnow()
    else:
        pref = models.UserPreference(user_id=user_id, suburb=suburb, stores=stores)
        db.add(pref)
    db.commit()
    return JSONResponse({"ok": True})


# ─────────────────────────────── PAGE ROUTES ────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse("/login", status_code=302)
    pref = db.query(models.UserPreference).filter(models.UserPreference.user_id == user_id).first()
    return templates.TemplateResponse(request, "landing.html", {
        "page": "landing",
        "all_suburbs": ALL_SUBURBS,
        "user": user,
        "saved_suburb": pref.suburb if pref else "",
        "saved_stores": pref.stores if pref else "",
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    entries = db.query(models.WatchlistEntry).join(models.Product).filter(
        models.WatchlistEntry.user_id == user_id
    ).all()

    # Attach latest price + price trend to each entry
    enriched = []
    drops_today = 0
    for entry in entries:
        product = entry.product
        history = (
            db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_id == product.id)
            .order_by(models.PriceRecord.scraped_at.desc())
            .limit(14)
            .all()
        )
        latest = history[0] if history else None
        prev = history[1] if len(history) > 1 else None
        drop_pct = None
        if latest and prev and latest.price and prev.price:
            drop_pct = round((prev.price - latest.price) / prev.price * 100, 1)
            if drop_pct > 0:
                drops_today += 1
        enriched.append({
            "entry": entry,
            "product": product,
            "latest": latest,
            "prev": prev,
            "drop_pct": drop_pct,
            "prices": [r.price for r in reversed(history) if r.price],
        })

    # Specials from watchlist
    specials = [e for e in enriched if e["latest"] and e["latest"].on_special]

    # Recent price changes: last 5 products where price changed between latest 2 records
    recent_changes = []
    for e in enriched:
        if e["latest"] and e["prev"] and e["latest"].price and e["prev"].price:
            if e["latest"].price != e["prev"].price:
                pct = round((e["prev"].price - e["latest"].price) / e["prev"].price * 100, 1)
                recent_changes.append({
                    "product": e["product"],
                    "latest": e["latest"],
                    "prev": e["prev"],
                    "drop_pct": pct,
                })
    # Sort by most recent scraped_at
    recent_changes.sort(key=lambda x: x["latest"].scraped_at, reverse=True)
    recent_changes = recent_changes[:5]

    return templates.TemplateResponse(request, "dashboard.html", {
        "enriched": enriched,
        "specials": specials,
        "drops_today": drops_today,
        "watchlist_count": len(entries),
        "recent_changes": recent_changes,
        "page": "dashboard",
    })


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, db: Session = Depends(get_db), q: str = "", store: str = "", stores: str = "", sort: str = ""):
    ns = db.query(models.NotificationSettings).first()
    effective_store = stores or store or (ns.default_store if ns else "all") or "all"
    effective_sort  = sort  or (ns.default_sort  if ns else "")    or ""

    # Load user's saved suburb + store preferences from landing page
    user_stores: list[str] = []
    user_suburb: str = ""
    user_id = request.session.get("user_id")
    if user_id:
        pref = db.query(models.UserPreference).filter(
            models.UserPreference.user_id == user_id
        ).first()
        if pref and pref.stores:
            user_stores = [s.strip() for s in pref.stores.split(",") if s.strip()]
        if pref and pref.suburb:
            user_suburb = pref.suburb

    # ── Trending Drops: up to 6 products currently on special or with was_price > price ──
    from sqlalchemy import func
    # Get the latest price record per product using a subquery
    latest_id_subq = (
        db.query(func.max(models.PriceRecord.id))
        .group_by(models.PriceRecord.product_id)
        .subquery()
    )
    trending_records = (
        db.query(models.PriceRecord, models.Product)
        .join(models.Product, models.PriceRecord.product_id == models.Product.id)
        .filter(models.PriceRecord.id.in_(latest_id_subq.select()))
        .filter(
            (models.PriceRecord.on_special == True) |
            (
                (models.PriceRecord.was_price != None) &
                (models.PriceRecord.was_price > models.PriceRecord.price)
            )
        )
        .filter(models.PriceRecord.price != None)
        .order_by(models.PriceRecord.scraped_at.desc())
        .limit(6)
        .all()
    )
    trending = [
        {"product": prod, "latest": rec}
        for rec, prod in trending_records
    ]

    return templates.TemplateResponse(request, "search.html", {
        "query": q,
        "store": effective_store,
        "default_sort": effective_sort,
        "trending": trending,
        "page": "search",
        "user_stores": user_stores,
        "user_suburb": user_suburb,
    })


@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    entries = db.query(models.WatchlistEntry).join(models.Product).filter(
        models.WatchlistEntry.user_id == user_id
    ).all()
    enriched = []
    for entry in entries:
        history = (
            db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_id == entry.product.id)
            .order_by(models.PriceRecord.scraped_at.desc())
            .limit(14)
            .all()
        )
        latest = history[0] if history else None
        prev = history[1] if len(history) > 1 else None
        drop_pct = None
        if latest and prev and latest.price and prev.price:
            drop_pct = round((prev.price - latest.price) / prev.price * 100, 1)
        enriched.append({
            "entry": entry,
            "product": entry.product,
            "latest": latest,
            "prev": prev,
            "drop_pct": drop_pct,
            "prices": [r.price for r in reversed(history) if r.price],
            "base_name": _base_name(entry.product.name),
        })
    # Group entries by normalized product name so same-product entries are adjacent
    enriched.sort(key=lambda e: e["base_name"])
    # Savings & alerts summary for hero cards
    potential_savings = 0.0
    active_alerts = 0
    for e in enriched:
        latest = e["latest"]
        entry = e["entry"]
        if latest and latest.was_price and latest.price and latest.was_price > latest.price:
            potential_savings += latest.was_price - latest.price
        if latest and latest.price:
            if entry.alert_price_below and latest.price <= entry.alert_price_below:
                active_alerts += 1
            if entry.alert_drop_pct and e["drop_pct"] and e["drop_pct"] >= entry.alert_drop_pct:
                active_alerts += 1

    return templates.TemplateResponse(request, "watchlist.html", {
        "enriched": enriched,
        "page": "watchlist",
        "potential_savings": round(potential_savings, 2),
        "active_alerts": active_alerts,
        "drops_today": sum(1 for e in enriched if e["drop_pct"] and e["drop_pct"] > 0),
    })


def _stores_for_suburb(suburb: str) -> list[str]:
    """Return deduplicated store slugs available near a suburb."""
    key = suburb.strip().lower()
    if not key or key not in SUBURB_STORES:
        return ALL_STORE_SLUGS  # fallback: show all stores
    nearby = nearby_suburbs(key, km=5.0)
    expanded = [k for k in nearby if k in SUBURB_STORES]
    if key not in expanded:
        expanded.insert(0, key)
    seen: set[str] = set()
    slugs: list[str] = []
    for k in expanded:
        for slug in SUBURB_STORES.get(k, []):
            if slug not in seen:
                seen.add(slug)
                slugs.append(slug)
    return slugs or ALL_STORE_SLUGS


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    ns = db.query(models.NotificationSettings).first()
    notify_days_list = [int(d) for d in (ns.notify_days or "").split(",") if d.strip().isdigit()]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # Ensure new fields have defaults when loaded from an older DB row
    if not hasattr(ns, "poll_frequency") or ns.poll_frequency is None:
        ns.poll_frequency = "weekly"
    if not hasattr(ns, "poll_day") or ns.poll_day is None:
        ns.poll_day = 0

    # Build dynamic store list based on user's saved suburb
    user_id = request.session.get("user_id")
    user_suburb = ""
    if user_id:
        pref = db.query(models.UserPreference).filter(
            models.UserPreference.user_id == user_id
        ).first()
        if pref and pref.suburb:
            user_suburb = pref.suburb

    store_options = [("all", "All Stores", "#374151")] + [
        (slug, STORE_LABELS.get(slug, slug.replace("_", " ").title()), STORE_COLORS.get(slug, "#666"))
        for slug in _stores_for_suburb(user_suburb)
    ]

    return templates.TemplateResponse(request, "settings.html", {
        "ns": ns,
        "notify_days_list": notify_days_list,
        "day_names": day_names,
        "page": "settings",
        "store_options": store_options,
    })


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(
    request: Request,
    product_id: str,
    store: str = "",
    db: Session = Depends(get_db),
):
    # Try lookup by internal DB id first (integer)
    product = None
    if product_id.isdigit():
        product = db.query(models.Product).filter(models.Product.id == int(product_id)).first()

    # Fall back: lookup by external_id + store (from search result links)
    if not product and store:
        product = (
            db.query(models.Product)
            .filter(
                models.Product.external_id == product_id,
                models.Product.store == store,
            )
            .first()
        )

    # If still not found, return a friendly page instead of a JSON error
    if not product:
        return templates.TemplateResponse(request, "product_detail.html", {
            "product": None,
            "history": [],
            "on_watchlist": None,
            "page": "search",
            "not_found": True,
            "external_id": product_id,
            "store": store,
        })
    history = (
        db.query(models.PriceRecord)
        .filter(models.PriceRecord.product_id == product_id)
        .order_by(models.PriceRecord.scraped_at.asc())
        .all()
    )
    user_id = request.session.get("user_id")
    on_watchlist = db.query(models.WatchlistEntry).filter(
        models.WatchlistEntry.product_id == product_id,
        models.WatchlistEntry.user_id == user_id,
    ).first()
    return templates.TemplateResponse(request, "product_detail.html", {
        "product": product,
        "history": history,
        "on_watchlist": on_watchlist,
        "page": "search",
    })


# ──────────────────────────── HTMX PARTIAL ROUTES ───────────────────────────

@app.get("/partials/suburb-stores", response_class=HTMLResponse)
async def suburb_stores_partial(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Return store chips for suburbs matching the query, expanded to 5 km radius."""
    q_norm = q.strip().lower()
    if len(q_norm) < 2:
        return HTMLResponse("")

    # Step 1 — direct text matches (suburb name contains query; no postcodes yet)
    direct_keys = [k for k in SUBURB_STORES if not k.isdigit() and q_norm in k]

    # Step 2 — fall back to postcode if nothing found
    if not direct_keys:
        direct_keys = [k for k in SUBURB_STORES if k.isdigit() and q_norm == k]

    if not direct_keys:
        return templates.TemplateResponse(request, "partials/suburb_stores.html", {
            "matches": {},
            "query": q,
            "store_labels": STORE_LABELS,
            "store_colors": STORE_COLORS,
            "selected_stores": [],
        })

    # Step 3 — for each direct match expand to 5 km radius and union stores
    # matches: display_name → deduplicated ordered list of store slugs
    matches: dict[str, list[str]] = {}
    per_suburb_slugs: dict[str, list[str]] = {}  # for per-suburb "select all" buttons

    for key in direct_keys:
        if key.isdigit():
            suburb_label = POSTCODE_NAMES.get(key, "")
            display = f"{key} — {suburb_label}" if suburb_label else key
        else:
            display = key.title()

        # Expand: own suburb + all suburbs within 5 km that exist in SUBURB_STORES
        nearby = nearby_suburbs(key, km=5.0)
        expanded_keys = [k for k in nearby if k in SUBURB_STORES]
        if key not in expanded_keys:
            expanded_keys.insert(0, key)

        # Deduplicate slugs, preserving a sensible order
        seen: set[str] = set()
        unique_slugs: list[str] = []
        for nk in expanded_keys:
            for slug in SUBURB_STORES.get(nk, []):
                if slug not in seen:
                    seen.add(slug)
                    unique_slugs.append(slug)

        matches[display] = unique_slugs
        per_suburb_slugs[display] = unique_slugs

    # Load user's saved store preferences for server-side initial rendering
    selected_stores: list[str] = []
    user_id = request.session.get("user_id")
    if user_id:
        pref = db.query(models.UserPreference).filter(
            models.UserPreference.user_id == user_id
        ).first()
        if pref and pref.stores:
            selected_stores = [s.strip() for s in pref.stores.split(",") if s.strip()]

    return templates.TemplateResponse(request, "partials/suburb_stores.html", {
        "matches": matches,
        "per_suburb_slugs": per_suburb_slugs,
        "query": q,
        "store_labels": STORE_LABELS,
        "store_colors": STORE_COLORS,
        "selected_stores": selected_stores,
    })


@app.get("/partials/search-results", response_class=HTMLResponse)
async def search_results(
    request: Request,
    q: str = "",
    store: str = "all",
    page: int = 0,
    price_min: Optional[str] = None,
    price_max: Optional[str] = None,
    sort: Optional[str] = None,
    brand: str = "",
    fresh: str = "",
):
    if not q or len(q) < 2:
        return HTMLResponse("")

    # Treat empty store value (pre-Alpine boot) same as "all"
    if not store:
        store = "all"

    # Parse price range filters
    p_min = float(price_min) if price_min else None
    p_max = float(price_max) if price_max else None

    import asyncio
    import logging
    all_results = []
    failed_stores: list[str] = []

    async def run_scraper(scraper_cls, store_slug):
        try:
            scraper = scraper_cls()
            hits = await scraper.search(q, limit=25)
            await scraper.close()
            return (store_slug, hits)
        except Exception as exc:
            logging.error("Scraper %s failed: %s", store_slug, exc)
            failed_stores.append(store_slug)
            return (store_slug, [])

    # Resolve active store slugs — supports "all", single slug, or comma-separated list
    if "," in store:
        active_slugs = [s.strip() for s in store.split(",") if s.strip()]
    elif store == "all" or not store:
        active_slugs = list(ALL_STORE_SLUGS)
    else:
        active_slugs = [store]

    from app.scrapers.woolworths import WoolworthsScraper
    from app.scrapers.coles import ColesScraper
    from app.scrapers.harris_farm import HarrisFarmScraper
    from app.scrapers.iga import IGANorthSydneyScraper, IGAMilsonsPointScraper, IGACrowsNestScraper

    _scraper_map = {
        "woolworths":       WoolworthsScraper,
        "coles":            ColesScraper,
        "harris_farm":      HarrisFarmScraper,
        "iga_north_sydney": IGANorthSydneyScraper,
        "iga_milsons_point": IGAMilsonsPointScraper,
        "iga_crows_nest":   IGACrowsNestScraper,
    }

    tasks = []
    for slug in active_slugs:
        if slug in _scraper_map:
            tasks.append(run_scraper(_scraper_map[slug], slug))

    task_results = await asyncio.gather(*tasks)
    for _slug, hits in task_results:
        all_results.extend(hits)

    # Apply price range filter
    if p_min is not None:
        all_results = [r for r in all_results if r.price is not None and r.price >= p_min]
    if p_max is not None:
        all_results = [r for r in all_results if r.price is not None and r.price <= p_max]

    # Apply sort
    if sort == "asc":
        all_results.sort(key=lambda r: r.price if r.price is not None else float("inf"))
    elif sort == "desc":
        all_results.sort(key=lambda r: r.price if r.price is not None else float("-inf"), reverse=True)

    # Attach brand, per-unit price label, processed flag, and relevance score
    from app.unit_parser import per_unit_price as _pu
    for r in all_results:
        r._brand = _extract_brand(r.name)
        if r.price:
            _, r._pu_label = _pu(float(r.price), r.unit or "")
        else:
            r._pu_label = ""
        r._is_processed = _is_processed(r.name, r.category)
        r._relevance = _relevance_score(r.name, q)

    # Filter out very low relevance results (ingredient-only matches)
    # unless the search itself is very short (e.g. single word like "milk")
    if len(q.split()) > 1:
        all_results = [r for r in all_results if r._relevance >= 0.2]

    # Apply fresh-only filter — exclude processed/canned/jarred products
    if fresh:
        all_results = [r for r in all_results if not r._is_processed]

    # Collect all unique brands BEFORE brand-filter (for sidebar list)
    all_brands = sorted({r._brand for r in all_results}, key=str.lower)

    # Apply brand filter
    selected_brands = [b.strip() for b in brand.split(",") if b.strip()] if brand else []
    if selected_brands:
        all_results = [r for r in all_results if r._brand in selected_brands]

    # Sort: by relevance first (descending), then by price (ascending) within same tier
    # Only apply relevance sort when no explicit sort is requested
    if not sort:
        all_results.sort(key=lambda r: (-r._relevance, r.price if r.price is not None else float("inf")))

    # Paginate — 25 per page
    page_size = 25
    total     = len(all_results)
    start     = page * page_size
    end       = start + page_size
    page_results = all_results[start:end]

    # Build human-readable labels for failed stores
    failed_labels = [STORE_LABELS.get(s, s) for s in failed_stores]

    return templates.TemplateResponse(request, "partials/search_results.html", {
        "results":         page_results,
        "all_brands":      all_brands,
        "selected_brands": selected_brands,
        "query":     q,
        "store":     store,
        "page":      page,
        "page_size": page_size,
        "total":     total,
        "has_prev":  page > 0,
        "has_next":  end < total,
        "price_min": price_min or "",
        "price_max": price_max or "",
        "sort":      sort or "",
        "brand":          brand or "",
        "failed_stores":  failed_labels,
    })


@app.post("/partials/watchlist/add", response_class=HTMLResponse)
async def watchlist_add(
    request: Request,
    db: Session = Depends(get_db),
    external_id: str = Form(...),
    store: str = Form(...),
    name: str = Form(...),
    url: str = Form(...),
    price: Optional[str] = Form(None),
    unit: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
):
    user_id = request.session.get("user_id")
    # Upsert product
    product = db.query(models.Product).filter(
        models.Product.external_id == external_id,
        models.Product.store == store,
    ).first()
    if not product:
        product = models.Product(
            name=name,
            store=store,
            external_id=external_id,
            url=url,
            image_url=image_url,
            unit=unit,
        )
        db.add(product)
        db.flush()

    # Store initial price record
    if price:
        try:
            price_val = float(price)
            db.add(models.PriceRecord(product_id=product.id, price=price_val))
        except ValueError:
            pass

    # Upsert watchlist entry for primary product (scoped to this user)
    entry = db.query(models.WatchlistEntry).filter(
        models.WatchlistEntry.product_id == product.id,
        models.WatchlistEntry.user_id == user_id,
    ).first()
    if not entry:
        entry = models.WatchlistEntry(product_id=product.id, user_id=user_id)
        db.add(entry)
    db.commit()

    # ── Cross-store search: find same product at all other stores ──────────
    other_stores = [s for s in ALL_STORE_SLUGS if s != store]
    # Use a simplified query (first 3 words of the product name)
    words = name.split()
    search_q = " ".join(words[:3]) if len(words) >= 3 else name

    cross_results = await asyncio.gather(
        *[_search_one_store(s, search_q) for s in other_stores]
    )

    stores_added = [store]  # primary store already added
    for result in cross_results:
        if result is None or not result.name:
            continue
        if not _names_similar(name, result.name):
            continue
        # Upsert product for this store
        p = db.query(models.Product).filter(
            models.Product.external_id == result.external_id,
            models.Product.store == result.store,
        ).first()
        if not p:
            p = models.Product(
                name=result.name,
                store=result.store,
                external_id=result.external_id,
                url=result.url,
                image_url=result.image_url,
                unit=result.unit,
            )
            db.add(p)
            db.flush()
        # Store initial price
        if result.price:
            db.add(models.PriceRecord(product_id=p.id, price=result.price))
        # Upsert watchlist entry (scoped to this user)
        we = db.query(models.WatchlistEntry).filter(
            models.WatchlistEntry.product_id == p.id,
            models.WatchlistEntry.user_id == user_id,
        ).first()
        if not we:
            we = models.WatchlistEntry(product_id=p.id, user_id=user_id)
            db.add(we)
        stores_added.append(result.store)
    db.commit()

    store_count = len(set(stores_added))
    label = STORE_LABELS.get(store, store)
    return HTMLResponse(f"""
      <span class="inline-flex items-center gap-1.5 text-xs font-semibold
                   bg-emerald-50 text-emerald-700 border border-emerald-200
                   px-3.5 py-2 rounded-xl">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
        </svg>
        Watching &middot; {store_count} store{'s' if store_count != 1 else ''}
      </span>
    """)


@app.get("/partials/watchlist/{entry_id}/edit", response_class=HTMLResponse)
async def watchlist_edit_form(request: Request, entry_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    entry = db.query(models.WatchlistEntry).filter(
        models.WatchlistEntry.id == entry_id,
        models.WatchlistEntry.user_id == user_id,
    ).first()
    if not entry:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "partials/watchlist_edit_form.html", {
        "entry": entry,
        "product": entry.product,
    })


@app.put("/partials/watchlist/{entry_id}", response_class=HTMLResponse)
async def watchlist_update(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
    alert_drop_pct: Optional[str] = Form(None),
    alert_price_below: Optional[str] = Form(None),
    notify_email: Optional[str] = Form(None),
    notify_push: Optional[str] = Form(None),
):
    user_id = request.session.get("user_id")
    entry = db.query(models.WatchlistEntry).filter(
        models.WatchlistEntry.id == entry_id,
        models.WatchlistEntry.user_id == user_id,
    ).first()
    if not entry:
        raise HTTPException(404)
    entry.alert_drop_pct = float(alert_drop_pct) if alert_drop_pct else None
    entry.alert_price_below = float(alert_price_below) if alert_price_below else None
    entry.notify_email = notify_email == "on"
    entry.notify_push = notify_push == "on"
    db.commit()
    db.refresh(entry)

    history = (
        db.query(models.PriceRecord)
        .filter(models.PriceRecord.product_id == entry.product.id)
        .order_by(models.PriceRecord.scraped_at.desc())
        .limit(14)
        .all()
    )
    latest = history[0] if history else None
    prev = history[1] if len(history) > 1 else None
    drop_pct = None
    if latest and prev and latest.price and prev.price:
        drop_pct = round((prev.price - latest.price) / prev.price * 100, 1)

    return templates.TemplateResponse(request, "partials/watchlist_card.html", {
        "e": {
            "entry": entry,
            "product": entry.product,
            "latest": latest,
            "prev": prev,
            "drop_pct": drop_pct,
            "prices": [r.price for r in reversed(history) if r.price],
        },
        "oob": False,
    })


@app.delete("/partials/watchlist/{entry_id}", response_class=HTMLResponse)
async def watchlist_delete(request: Request, entry_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    entry = db.query(models.WatchlistEntry).filter(
        models.WatchlistEntry.id == entry_id,
        models.WatchlistEntry.user_id == user_id,
    ).first()
    if entry:
        db.delete(entry)
        db.commit()
    return HTMLResponse("")


# ─────────────────────────── SETTINGS ROUTES ────────────────────────────────

@app.post("/settings/notifications", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    db: Session = Depends(get_db),
    email_address: str = Form(""),
    email_address_2: str = Form(""),
    email_address_3: str = Form(""),
    email_enabled: Optional[str] = Form(None),
    digest_frequency: str = Form("weekly"),
    notify_hour: int = Form(8),
    ntfy_enabled: Optional[str] = Form(None),
    ntfy_topic: str = Form(""),
    ntfy_server: str = Form("https://ntfy.sh"),
    quiet_hours_start: Optional[str] = Form(None),
    quiet_hours_end: Optional[str] = Form(None),
    global_min_drop_pct: float = Form(5.0),
    notify_back_in_stock: Optional[str] = Form(None),
    notify_on_special: Optional[str] = Form(None),
    poll_frequency: str = Form("weekly"),
    poll_day: int = Form(0),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    default_sort: str = Form(""),
    default_store: str = Form("all"),
    scraperapi_key: str = Form(""),
):
    form_data = await request.form()
    notify_days = ",".join(str(i) for i in range(7) if form_data.get(f"day_{i}") == "on")
    if not notify_days:
        notify_days = "0,1,2,3,4,5,6"

    ns = db.query(models.NotificationSettings).first()
    ns.email_address   = email_address   or None
    ns.email_address_2 = email_address_2 or None
    ns.email_address_3 = email_address_3 or None
    ns.email_enabled   = email_enabled == "on"
    ns.digest_frequency = digest_frequency
    ns.notify_hour     = notify_hour
    ns.notify_days     = notify_days
    ns.ntfy_enabled    = ntfy_enabled == "on"
    ns.ntfy_topic      = ntfy_topic or None
    ns.ntfy_server     = ntfy_server or "https://ntfy.sh"
    ns.quiet_hours_start = int(quiet_hours_start) if quiet_hours_start else None
    ns.quiet_hours_end   = int(quiet_hours_end)   if quiet_hours_end   else None
    ns.global_min_drop_pct  = global_min_drop_pct
    ns.notify_back_in_stock = notify_back_in_stock == "on"
    ns.notify_on_special    = notify_on_special    == "on"
    ns.poll_frequency = poll_frequency
    ns.poll_day       = poll_day
    ns.smtp_user      = smtp_user     or None
    # Only overwrite password if a new one was actually submitted
    if smtp_password:
        ns.smtp_password = smtp_password
    ns.default_sort  = default_sort  or ""
    ns.default_store = default_store or "all"
    # Save ScraperAPI key and update runtime settings
    if scraperapi_key:
        ns.scraperapi_key = scraperapi_key
        set_scraperapi_key(scraperapi_key)  # apply immediately for this process
    ns.updated_at     = datetime.utcnow()
    db.commit()

    return templates.TemplateResponse(request, "partials/settings_saved.html", {})


@app.post("/settings/test-email", response_class=HTMLResponse)
async def test_email(request: Request, db: Session = Depends(get_db)):
    from app.notifiers.email import send_digest, smtp_config_for
    ns = db.query(models.NotificationSettings).first()

    smtp_user = ns.smtp_user or ""
    smtp_pass = ns.smtp_password or ""
    recipients = [r for r in [ns.email_address, ns.email_address_2, ns.email_address_3] if r]

    if not smtp_user or not smtp_pass:
        return HTMLResponse(
            '<div class="rounded-xl px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-sm">'
            '⚠️ SMTP credentials not saved. Enter your sending email and app password in the SMTP section above and save first.'
            '</div>'
        )
    if not recipients:
        return HTMLResponse(
            '<div class="rounded-xl px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-sm">'
            '⚠️ No recipient email address configured.'
            '</div>'
        )

    import os
    os.environ["SMTP_USER"]     = smtp_user
    os.environ["SMTP_PASSWORD"] = smtp_pass

    # Build watchlist snapshot (scoped to requesting user)
    _uid = request.session.get("user_id")
    entries = db.query(models.WatchlistEntry).join(models.Product).filter(
        models.WatchlistEntry.user_id == _uid
    ).all()
    watchlist_rows = ""
    for entry in entries:
        product = entry.product
        history = (
            db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_id == product.id)
            .order_by(models.PriceRecord.scraped_at.desc())
            .limit(2)
            .all()
        )
        latest   = history[0] if history else None
        prev     = history[1] if len(history) > 1 else None
        price_str = f"${latest.price:.2f}" if latest and latest.price else "—"

        # Price change indicator
        change_html = ""
        if latest and prev and latest.price and prev.price:
            diff = latest.price - prev.price
            pct  = diff / prev.price * 100
            if diff < 0:
                change_html = f'<span style="color:#059669;font-size:11px">▼ {abs(pct):.1f}%</span>'
            elif diff > 0:
                change_html = f'<span style="color:#dc2626;font-size:11px">▲ {abs(pct):.1f}%</span>'

        special_badge = '<span style="background:#fef3c7;color:#92400e;font-size:10px;padding:1px 6px;border-radius:9999px;font-weight:600;margin-left:4px">SPECIAL</span>' if latest and latest.on_special else ""
        was_html      = f'<div style="font-size:11px;color:#9ca3af;text-decoration:line-through">${latest.was_price:.2f}</div>' if latest and latest.was_price else ""

        store_label = STORE_LABELS.get(str(product.store.value if hasattr(product.store, "value") else product.store), str(product.store))
        store_color = STORE_COLORS.get(str(product.store.value if hasattr(product.store, "value") else product.store), "#666")

        alert_parts = []
        if entry.alert_drop_pct:
            alert_parts.append(f"↓{entry.alert_drop_pct:.0f}%")
        if entry.alert_price_below:
            alert_parts.append(f"&lt;${entry.alert_price_below:.2f}")
        alert_str = " · ".join(alert_parts) if alert_parts else '<span style="color:#d1d5db">none</span>'

        img_html = f'<img src="{product.image_url}" width="44" height="44" style="object-fit:contain;border-radius:6px;border:1px solid #f0f0f0" alt="">' if product.image_url else '<div style="width:44px;height:44px;background:#f9fafb;border-radius:6px;border:1px solid #f0f0f0"></div>'

        watchlist_rows += f"""
        <tr style="border-bottom:1px solid #f3f4f6">
          <td style="padding:10px 12px">
            <div style="display:flex;align-items:center;gap:10px">
              {img_html}
              <div>
                <div style="font-weight:600;font-size:13px;color:#111">{product.name}</div>
                <div style="font-size:11px;margin-top:2px">
                  <span style="background:{store_color};color:white;padding:1px 7px;border-radius:9999px;font-size:10px;font-weight:600">{store_label}</span>
                  {f'<span style="color:#6b7280;margin-left:4px">{product.unit}</span>' if product.unit else ''}
                </div>
              </div>
            </div>
          </td>
          <td style="padding:10px 12px;text-align:right;vertical-align:middle">
            <div style="font-weight:700;font-size:15px;color:#111">{price_str}{special_badge}</div>
            {was_html}
            {change_html}
          </td>
          <td style="padding:10px 12px;text-align:center;vertical-align:middle;color:#6b7280;font-size:12px">{alert_str}</td>
        </tr>"""

    now_str   = datetime.utcnow().strftime("%A, %d %B %Y")
    count_str = f"{len(entries)} product{'s' if len(entries) != 1 else ''} tracked"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,sans-serif">
  <div style="max-width:600px;margin:24px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">

    <!-- Header -->
    <div style="background:#059669;padding:20px 24px">
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-size:24px">🛒</span>
        <div>
          <h1 style="margin:0;color:white;font-size:18px;font-weight:700">Price Tracker — Watchlist Snapshot</h1>
          <p style="margin:3px 0 0;color:rgba(255,255,255,.8);font-size:12px">{now_str} · {count_str}</p>
        </div>
      </div>
    </div>

    <!-- Table -->
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb">
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600">Product</th>
          <th style="padding:8px 12px;text-align:right;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600">Price</th>
          <th style="padding:8px 12px;text-align:center;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600">Alert</th>
        </tr>
      </thead>
      <tbody>{watchlist_rows}</tbody>
    </table>

    <!-- Footer -->
    <div style="padding:16px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center">
      <p style="margin:0;font-size:11px;color:#9ca3af">
        Price Tracker · North Sydney ·
        <a href="http://localhost:8000" style="color:#059669;text-decoration:none">Open app</a> ·
        <a href="http://localhost:8000/settings" style="color:#059669;text-decoration:none">Manage alerts</a>
      </p>
      <p style="margin:4px 0 0;font-size:10px;color:#d1d5db">This is a preview — real alerts fire only when prices change and meet your thresholds.</p>
    </div>

  </div>
</body>
</html>"""

    try:
        ok = send_digest(f"🛒 Price Tracker — Watchlist ({len(entries)} items)", html, recipients)
        err_detail = ""
    except Exception as exc:
        ok = False
        err_detail = str(exc)
        print(f"[test-email] Exception: {exc}")

    if ok:
        return HTMLResponse(
            f'<div class="rounded-xl px-4 py-3 bg-green-50 border border-green-200 text-green-800 text-sm">'
            f'✅ Test email sent to <strong>{", ".join(recipients)}</strong> — check your inbox!'
            f'</div>'
        )
    else:
        detail = f" ({err_detail})" if err_detail else " — see server console for details."
        return HTMLResponse(
            f'<div class="rounded-xl px-4 py-3 bg-red-50 border border-red-200 text-red-800 text-sm">'
            f'❌ Send failed{detail}'
            f'</div>'
        )


@app.get("/partials/settings/email-preview", response_class=HTMLResponse)
async def email_preview(request: Request, db: Session = Depends(get_db)):
    _uid = request.session.get("user_id")
    entries = db.query(models.WatchlistEntry).join(models.Product).filter(
        models.WatchlistEntry.user_id == _uid
    ).limit(5).all()
    preview_items = []
    for entry in entries:
        latest = (
            db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_id == entry.product.id)
            .order_by(models.PriceRecord.scraped_at.desc())
            .first()
        )
        preview_items.append({"product": entry.product, "latest": latest})
    return templates.TemplateResponse(request, "partials/email_preview.html", {
        "preview_items": preview_items,
    })


# ─────────────────────────────── JSON API ───────────────────────────────────

@app.get("/api/price-history/{product_id}")
async def price_history_api(product_id: int, days: int = 30, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    records = (
        db.query(models.PriceRecord)
        .filter(
            models.PriceRecord.product_id == product_id,
            models.PriceRecord.scraped_at >= since,
            models.PriceRecord.price.isnot(None),
        )
        .order_by(models.PriceRecord.scraped_at.asc())
        .all()
    )
    return JSONResponse({
        "labels": [r.scraped_at.strftime("%d %b") for r in records],
        "prices": [r.price for r in records],
        "specials": [r.on_special for r in records],
    })


@app.get("/api/scraper-status")
async def scraper_status(db: Session = Depends(get_db)):
    """Return last-scrape freshness per store."""
    stores = ["woolworths", "coles", "harris_farm", "iga_crows_nest", "iga_milsons_point", "iga_north_sydney"]
    status = {}
    cutoff = datetime.utcnow() - timedelta(hours=26)
    for store in stores:
        latest = (
            db.query(models.PriceRecord)
            .join(models.Product)
            .filter(models.Product.store == store)
            .order_by(models.PriceRecord.scraped_at.desc())
            .first()
        )
        if not latest:
            status[store] = "no_data"
        elif latest.scraped_at < cutoff:
            status[store] = "stale"
        else:
            status[store] = "ok"
    return JSONResponse(status)


# ─────────────────────────── SHOPPING LIST ROUTES ───────────────────────────

@app.get("/shopping-list", response_class=HTMLResponse)
async def shopping_list_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    lists = db.query(models.ShoppingList).filter(
        models.ShoppingList.user_id == user_id
    ).order_by(models.ShoppingList.updated_at.desc()).all()
    if not lists:
        default = models.ShoppingList(name="My Shopping List", user_id=user_id)
        db.add(default)
        db.commit()
        db.refresh(default)
        lists = [default]
    return RedirectResponse(url=f"/shopping-list/{lists[0].id}", status_code=303)


@app.get("/shopping-list/{list_id}", response_class=HTMLResponse)
async def shopping_list_detail(request: Request, list_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if not sl:
        raise HTTPException(404)
    all_lists = db.query(models.ShoppingList).filter(
        models.ShoppingList.user_id == user_id
    ).order_by(models.ShoppingList.updated_at.desc()).all()

    # Parse matched_results JSON for each item
    from app.unit_parser import parse_unit as _parse_unit
    items_with_results = []
    for item in sl.items:
        results = []
        if item.matched_results:
            try:
                results = json.loads(item.matched_results)
            except Exception:
                results = []
        results_volume = [r for r in results if r.get("unit_cat") == "volume" or (not r.get("unit_cat") and _parse_unit(r.get("unit", ""))[1] == "volume")]
        results_weight = [r for r in results if r.get("unit_cat") == "weight" or (not r.get("unit_cat") and _parse_unit(r.get("unit", ""))[1] == "weight")]
        results_count  = [r for r in results if r not in results_volume and r not in results_weight]
        items_with_results.append({
            "item": item,
            "results": results,
            "results_volume": results_volume,
            "results_weight": results_weight,
            "results_count": results_count,
        })

    sorted_totals = _calc_store_totals(sl)

    return templates.TemplateResponse(request, "shopping_list.html", {
        "lists": all_lists,
        "active_list": sl,
        "items_with_results": items_with_results,
        "store_totals": sorted_totals,
        "page": "shopping_list",
    })


@app.get("/partials/shopping-list/{list_id}/totals", response_class=HTMLResponse)
async def shopping_list_totals(request: Request, list_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if not sl:
        return HTMLResponse("")
    store_totals = _calc_store_totals(sl)
    return templates.TemplateResponse(request, "partials/basket_totals.html", {
        "store_totals": store_totals,
        "list_id": list_id,
        "oob": False,
    })


@app.post("/shopping-list/import/text", response_class=HTMLResponse)
async def import_shopping_list_text(
    request: Request,
    db: Session = Depends(get_db),
    raw_text: str = Form(""),
    list_name: str = Form("My Shopping List"),
    list_id: Optional[int] = Form(None),
):
    import re
    user_id = request.session.get("user_id")
    # Get or create list
    if list_id:
        sl = db.query(models.ShoppingList).filter(
            models.ShoppingList.id == list_id,
            models.ShoppingList.user_id == user_id,
        ).first()
        if not sl:
            sl = models.ShoppingList(name=list_name, user_id=user_id)
            db.add(sl)
    else:
        sl = models.ShoppingList(name=list_name, user_id=user_id)
        db.add(sl)
    db.flush()

    # Parse lines
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    for line in lines:
        # Skip obvious non-items (headers, empty, dashes)
        if line.startswith('#') or line.startswith('-') or len(line) < 2:
            continue
        # Try to extract qty from start: "2x milk" or "2 milk" or "milk x2"
        qty = 1.0
        name = line
        m = re.match(r'^(\d+(?:\.\d+)?)\s*[xX]?\s+(.+)', line)
        if m:
            qty = float(m.group(1))
            name = m.group(2).strip()
        else:
            m2 = re.match(r'^(.+?)\s+[xX](\d+(?:\.\d+)?)$', line)
            if m2:
                name = m2.group(1).strip()
                qty = float(m2.group(2))

        item = models.ShoppingListItem(list_id=sl.id, name=name, qty=qty)
        db.add(item)

    sl.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sl)

    return RedirectResponse(url=f"/shopping-list/{sl.id}", status_code=303)


@app.post("/shopping-list/import/csv", response_class=HTMLResponse)
async def import_shopping_list_csv(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    list_name: str = Form("My Shopping List"),
    list_id: Optional[int] = Form(None),
):
    import csv, io
    user_id = request.session.get("user_id")
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")  # handle BOM

    if list_id:
        sl = db.query(models.ShoppingList).filter(
            models.ShoppingList.id == list_id,
            models.ShoppingList.user_id == user_id,
        ).first()
        if not sl:
            sl = models.ShoppingList(name=list_name, user_id=user_id)
            db.add(sl)
    else:
        sl = models.ShoppingList(name=list_name, user_id=user_id)
        db.add(sl)
    db.flush()

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        # Try common column names
        name = (row.get("name") or row.get("Name") or row.get("item") or row.get("Item") or
                row.get("product") or row.get("Product") or "").strip()
        if not name:
            # Try first column
            vals = list(row.values())
            name = vals[0].strip() if vals else ""
        if not name:
            continue
        qty_raw = (row.get("qty") or row.get("Qty") or row.get("quantity") or
                   row.get("Quantity") or row.get("amount") or "1").strip()
        try:
            qty = float(qty_raw)
        except Exception:
            qty = 1.0
        unit = (row.get("unit") or row.get("Unit") or "").strip() or None
        notes = (row.get("notes") or row.get("Notes") or "").strip() or None

        item = models.ShoppingListItem(list_id=sl.id, name=name, qty=qty, unit=unit, notes=notes)
        db.add(item)

    sl.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sl)

    return RedirectResponse(url=f"/shopping-list/{sl.id}", status_code=303)


@app.post("/partials/shopping-list/add-from-search", response_class=HTMLResponse)
async def shopping_list_add_from_search(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    unit: Optional[str] = Form(None),
    price: Optional[str] = Form(None),
    store: Optional[str] = Form(None),
    external_id: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
):
    user_id = request.session.get("user_id")
    # Get or create the default (most-recently-updated) shopping list for this user
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.user_id == user_id
    ).order_by(models.ShoppingList.updated_at.desc()).first()
    if not sl:
        sl = models.ShoppingList(name="My Shopping List", user_id=user_id)
        db.add(sl)
        db.flush()

    item = models.ShoppingListItem(
        list_id=sl.id,
        name=name.strip(),
        qty=1.0,
        unit=unit or None,
    )
    db.add(item)
    sl.updated_at = datetime.utcnow()
    db.commit()

    # Return a small "added" confirmation badge (replaces the button)
    list_name = sl.name
    return HTMLResponse(f"""
      <span class="inline-flex items-center gap-1.5 text-xs font-semibold
                   bg-violet-50 text-violet-700 border border-violet-200
                   px-3 py-2 rounded-xl whitespace-nowrap"
            title="Added to {list_name}">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
        </svg>
        In List
      </span>
    """)


@app.post("/partials/shopping-list/{list_id}/item", response_class=HTMLResponse)
async def add_shopping_list_item(
    request: Request,
    list_id: int,
    db: Session = Depends(get_db),
    name: str = Form(""),
    qty: float = Form(1.0),
    unit: str = Form(""),
):
    if not name.strip():
        return HTMLResponse("")
    user_id = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if not sl:
        raise HTTPException(404)
    item = models.ShoppingListItem(list_id=list_id, name=name.strip(), qty=qty, unit=unit or None)
    db.add(item)
    sl.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(request, "partials/shopping_list_item.html", {
        "item": item, "results": [], "list_id": list_id
    })


@app.post("/partials/shopping-list/item/{item_id}/search", response_class=HTMLResponse)
async def search_shopping_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(models.ShoppingListItem).filter(models.ShoppingListItem.id == item_id).first()
    if not item:
        raise HTTPException(404)

    # Run search across all stores using the same pattern as the search_results route
    all_results = []

    async def run_scraper(scraper_cls):
        try:
            scraper = scraper_cls()
            hits = await scraper.search(item.name, limit=5)
            await scraper.close()
            return hits
        except Exception:
            return []

    from app.scrapers.woolworths import WoolworthsScraper
    from app.scrapers.coles import ColesScraper
    from app.scrapers.harris_farm import HarrisFarmScraper
    from app.scrapers.iga import IGANorthSydneyScraper, IGAMilsonsPointScraper, IGACrowsNestScraper

    tasks = [
        run_scraper(WoolworthsScraper),
        run_scraper(ColesScraper),
        run_scraper(HarrisFarmScraper),
        run_scraper(IGANorthSydneyScraper),
        run_scraper(IGAMilsonsPointScraper),
        run_scraper(IGACrowsNestScraper),
    ]
    task_results = await asyncio.gather(*tasks)
    for hits in task_results:
        all_results.extend(hits)

    # Apply the same relevance filter used in the main search route
    query_words = item.name.strip().split()
    if len(query_words) >= 2:
        for r in all_results:
            r._relevance = _relevance_score(r.name, item.name)
        all_results = [r for r in all_results if r._relevance >= 0.15]

    sorted_volume, sorted_weight, sorted_count, all_sorted = _build_store_best(all_results)

    item.matched_results = json.dumps(all_sorted)
    db.commit()

    # Recalculate basket totals for OOB refresh
    sl = db.query(models.ShoppingList).filter(models.ShoppingList.id == item.list_id).first()
    store_totals = _calc_store_totals(sl) if sl else []

    item_html = templates.env.get_template("partials/shopping_list_item.html").render(
        item=item, results=all_sorted,
        results_volume=sorted_volume, results_weight=sorted_weight, results_count=sorted_count,
        list_id=item.list_id,
        **templates.env.globals,
    )
    totals_html = templates.env.get_template("partials/basket_totals.html").render(
        store_totals=store_totals, list_id=item.list_id, oob=True,
        **templates.env.globals,
    )
    return HTMLResponse(item_html + totals_html)


@app.post("/partials/shopping-list/search-all/{list_id}", response_class=HTMLResponse)
async def search_all_shopping_items(
    request: Request,
    list_id: int,
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if not sl:
        raise HTTPException(404)

    from app.scrapers.woolworths import WoolworthsScraper
    from app.scrapers.coles import ColesScraper
    from app.scrapers.harris_farm import HarrisFarmScraper
    from app.scrapers.iga import IGANorthSydneyScraper, IGAMilsonsPointScraper, IGACrowsNestScraper

    for item in sl.items:
        try:
            all_results = []

            async def run_scraper(scraper_cls, _item=item):
                try:
                    scraper = scraper_cls()
                    hits = await scraper.search(_item.name, limit=5)
                    await scraper.close()
                    return hits
                except Exception:
                    return []

            tasks = [
                run_scraper(WoolworthsScraper),
                run_scraper(ColesScraper),
                run_scraper(HarrisFarmScraper),
                run_scraper(IGANorthSydneyScraper),
                run_scraper(IGAMilsonsPointScraper),
                run_scraper(IGACrowsNestScraper),
            ]
            task_results = await asyncio.gather(*tasks)
            for hits in task_results:
                all_results.extend(hits)

            _, _, _, all_sorted = _build_store_best(all_results)
            item.matched_results = json.dumps(all_sorted)
        except Exception:
            pass

    db.commit()
    return RedirectResponse(url=f"/shopping-list/{sl.id}", status_code=303)


@app.delete("/partials/shopping-list/item/{item_id}", response_class=HTMLResponse)
async def delete_shopping_list_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.ShoppingListItem).filter(models.ShoppingListItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return HTMLResponse("")


@app.post("/partials/shopping-list/bulk-delete", response_class=HTMLResponse)
async def bulk_delete_shopping_items(
    item_ids: str = Form(""),
    db: Session = Depends(get_db),
):
    ids = [int(i) for i in item_ids.split(",") if i.strip().isdigit()]
    if ids:
        db.query(models.ShoppingListItem).filter(
            models.ShoppingListItem.id.in_(ids)
        ).delete(synchronize_session=False)
        db.commit()
    return HTMLResponse("")


@app.post("/partials/shopping-list/bulk-search", response_class=HTMLResponse)
async def bulk_search_shopping_items(
    request: Request,
    list_id: int = Form(...),
    item_ids: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    ids = [int(i) for i in item_ids.split(",") if i.strip().isdigit()]
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if not sl:
        raise HTTPException(404)

    from app.scrapers.woolworths import WoolworthsScraper
    from app.scrapers.coles import ColesScraper
    from app.scrapers.harris_farm import HarrisFarmScraper
    from app.scrapers.iga import IGANorthSydneyScraper, IGAMilsonsPointScraper, IGACrowsNestScraper

    items_to_search = [item for item in sl.items if item.id in ids]
    for item in items_to_search:
        try:
            all_results = []

            async def run_scraper(scraper_cls, _item=item):
                try:
                    scraper = scraper_cls()
                    hits = await scraper.search(_item.name, limit=5)
                    await scraper.close()
                    return hits
                except Exception:
                    return []

            tasks = [
                run_scraper(WoolworthsScraper),
                run_scraper(ColesScraper),
                run_scraper(HarrisFarmScraper),
                run_scraper(IGANorthSydneyScraper),
                run_scraper(IGAMilsonsPointScraper),
                run_scraper(IGACrowsNestScraper),
            ]
            task_results = await asyncio.gather(*tasks)
            for hits in task_results:
                all_results.extend(hits)

            # Relevance filter — same threshold as main search
            q_words = item.name.strip().split()
            if len(q_words) >= 2:
                for r in all_results:
                    r._relevance = _relevance_score(r.name, item.name)
                all_results = [r for r in all_results if r._relevance >= 0.15]

            _, _, _, all_sorted = _build_store_best(all_results)
            item.matched_results = json.dumps(all_sorted)
        except Exception:
            pass

    db.commit()
    return RedirectResponse(url=f"/shopping-list/{sl.id}", status_code=303)


@app.post("/partials/watchlist/bulk-delete", response_class=HTMLResponse)
async def bulk_delete_watchlist(
    request: Request,
    entry_ids: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    ids = [int(i) for i in entry_ids.split(",") if i.strip().isdigit()]
    if ids:
        db.query(models.WatchlistEntry).filter(
            models.WatchlistEntry.id.in_(ids),
            models.WatchlistEntry.user_id == user_id,
        ).delete(synchronize_session=False)
        db.commit()
    return HTMLResponse("")


@app.post("/partials/shopping-list/item/{item_id}/size", response_class=HTMLResponse)
@app.patch("/partials/shopping-list/item/{item_id}/size", response_class=HTMLResponse)
async def update_item_size(
    request: Request,
    item_id: int,
    qty: float = Form(1.0),
    unit: str = Form(""),
    db: Session = Depends(get_db),
):
    """Update the comparison size (qty + unit) for a shopping list item."""
    item = db.query(models.ShoppingListItem).filter(models.ShoppingListItem.id == item_id).first()
    if not item:
        raise HTTPException(404)

    # Normalise compound units (e.g. "660g" → qty*=660, unit="g").
    # The UI select only offers simple units, but old/API data may have compounds.
    _SIMPLE_UNITS = {"", "ml", "L", "g", "kg", "each", "pack"}
    unit_clean = unit.strip()
    if unit_clean not in _SIMPLE_UNITS:
        from app.unit_parser import parse_unit as _pu
        _base, _cat = _pu(unit_clean)
        if _cat == "volume" and _base > 0:
            qty = qty * _base          # now in mL
            unit_clean = "L" if qty >= 1000 else "ml"
            if unit_clean == "L": qty /= 1000
        elif _cat == "weight" and _base > 0:
            qty = qty * _base          # now in g
            unit_clean = "kg" if qty >= 1000 else "g"
            if unit_clean == "kg": qty /= 1000
        elif _cat == "count" and _base > 0:
            qty = qty * _base
            unit_clean = "each"
        else:
            unit_clean = ""            # unrecognised — clear unit

    item.qty  = max(qty, 0.001)
    item.unit = unit_clean or None
    db.commit()

    results = json.loads(item.matched_results) if item.matched_results else []
    sl = db.query(models.ShoppingList).filter(models.ShoppingList.id == item.list_id).first()
    store_totals = _calc_store_totals(sl) if sl else []

    item_html = templates.env.get_template("partials/shopping_list_item.html").render(
        item=item, results=results,
        results_volume=[r for r in results if r.get("unit_cat") == "volume"],
        results_weight=[r for r in results if r.get("unit_cat") == "weight"],
        results_count =[r for r in results if r.get("unit_cat") not in ("volume", "weight")],
        list_id=item.list_id,
        **templates.env.globals,
    )
    totals_html = templates.env.get_template("partials/basket_totals.html").render(
        store_totals=store_totals, list_id=item.list_id, oob=True,
        **templates.env.globals,
    )
    return HTMLResponse(item_html + totals_html)


@app.patch("/partials/shopping-list/item/{item_id}/check", response_class=HTMLResponse)
async def toggle_item_checked(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(models.ShoppingListItem).filter(models.ShoppingListItem.id == item_id).first()
    if item:
        item.checked = not item.checked
        db.commit()
    from app.unit_parser import parse_unit as _pu
    _results = json.loads(item.matched_results) if item.matched_results else []
    _rv = [r for r in _results if r.get("unit_cat") == "volume" or (not r.get("unit_cat") and _pu(r.get("unit",""))[1] == "volume")]
    _rw = [r for r in _results if r.get("unit_cat") == "weight" or (not r.get("unit_cat") and _pu(r.get("unit",""))[1] == "weight")]
    _rc = [r for r in _results if r not in _rv and r not in _rw]
    return templates.TemplateResponse(request, "partials/shopping_list_item.html", {
        "item": item,
        "results": _results,
        "results_volume": _rv,
        "results_weight": _rw,
        "results_count":  _rc,
        "list_id": item.list_id,
    })


# ── Shopping list management ──────────────────────────────────────────────────

@app.post("/shopping-list/new", response_class=HTMLResponse)
async def create_shopping_list(
    request: Request,
    name: str = Form("New Shopping List"),
    db: Session = Depends(get_db),
):
    """Create a new shopping list and redirect to it."""
    user_id = request.session.get("user_id")
    sl = models.ShoppingList(name=name.strip() or "New Shopping List", user_id=user_id)
    db.add(sl)
    db.commit()
    db.refresh(sl)
    return RedirectResponse(url=f"/shopping-list/{sl.id}", status_code=303)


@app.delete("/shopping-list/{list_id}", response_class=HTMLResponse)
async def delete_shopping_list(request: Request, list_id: int, db: Session = Depends(get_db)):
    """Delete a shopping list (and all its items via cascade)."""
    user_id = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if sl:
        db.delete(sl)
        db.commit()
    # Redirect to another list, or the base route (which creates a new one if none exist)
    remaining = db.query(models.ShoppingList).filter(
        models.ShoppingList.user_id == user_id
    ).order_by(
        models.ShoppingList.updated_at.desc()
    ).first()
    if remaining:
        return RedirectResponse(url=f"/shopping-list/{remaining.id}", status_code=303)
    return RedirectResponse(url="/shopping-list", status_code=303)


@app.post("/shopping-list/{list_id}/rename", response_class=HTMLResponse)
@app.patch("/shopping-list/{list_id}/rename", response_class=HTMLResponse)
async def rename_shopping_list(
    request: Request,
    list_id: int,
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    """Rename the shopping list. Returns updated heading fragment for HTMX."""
    user_id = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == user_id,
    ).first()
    if not sl:
        raise HTTPException(404)
    new_name = name.strip() or sl.name
    if new_name != sl.name:
        sl.name = new_name
        sl.updated_at = datetime.utcnow()
        db.commit()

    # Check if HTMX request — return heading fragment; otherwise full redirect
    if request.headers.get("HX-Request"):
        safe_name = new_name.replace("'", "\\'")
        return HTMLResponse(f"""
<h1 id="list-name-heading" class="text-2xl font-bold text-gray-900 flex items-center gap-2">
  <svg class="w-6 h-6 text-brand shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/>
  </svg>
  {new_name}
</h1>
""")
    return RedirectResponse(url=f"/shopping-list/{list_id}", status_code=303)


# ── Email: shopping list ──────────────────────────────────────────────────────

@app.post("/shopping-list/{list_id}/email", response_class=HTMLResponse)
async def email_shopping_list(
    request: Request,
    list_id: int,
    db: Session = Depends(get_db),
):
    """Send a price-comparison email for a shopping list."""
    import os
    from app.notifiers.email import send_digest
    from app.notifiers.shopping_email import build_shopping_list_html

    ns = db.query(models.NotificationSettings).first()
    smtp_user = (ns.smtp_user if ns else None) or os.getenv("SMTP_USER", "")
    smtp_pass = (ns.smtp_password if ns else None) or os.getenv("SMTP_PASSWORD", "")
    recipients = [r for r in [
        ns.email_address if ns else None,
        getattr(ns, "email_address_2", None) if ns else None,
        getattr(ns, "email_address_3", None) if ns else None,
    ] if r]

    if not smtp_user or not smtp_pass:
        return HTMLResponse(
            '<div id="email-feedback" class="rounded-xl px-4 py-3 bg-amber-50 border border-amber-200 '
            'text-amber-800 text-sm mt-3">⚠️ SMTP credentials not configured. '
            'Go to <a href="/settings" class="underline">Settings</a> and enter your email and app password.</div>'
        )
    if not recipients:
        return HTMLResponse(
            '<div id="email-feedback" class="rounded-xl px-4 py-3 bg-amber-50 border border-amber-200 '
            'text-amber-800 text-sm mt-3">⚠️ No recipient email address configured. '
            'Add one in <a href="/settings" class="underline">Settings</a>.</div>'
        )

    _uid = request.session.get("user_id")
    sl = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == list_id,
        models.ShoppingList.user_id == _uid,
    ).first()
    if not sl:
        raise HTTPException(404)

    os.environ["SMTP_USER"]     = smtp_user
    os.environ["SMTP_PASSWORD"] = smtp_pass

    app_url = str(request.base_url).rstrip("/")
    html    = build_shopping_list_html(sl.name, sl.items, app_url)
    subject = f"Shopping List — {sl.name} ({len(sl.items)} items)"
    ok      = send_digest(subject, html, recipients)

    if ok:
        to_str = ", ".join(recipients)
        return HTMLResponse(
            f'<div id="email-feedback" class="rounded-xl px-4 py-3 bg-emerald-50 border border-emerald-200 '
            f'text-emerald-800 text-sm mt-3">✓ Email sent to {to_str}</div>'
        )
    return HTMLResponse(
        '<div id="email-feedback" class="rounded-xl px-4 py-3 bg-red-50 border border-red-200 '
        'text-red-700 text-sm mt-3">✗ Failed to send email. Check your SMTP settings in '
        '<a href="/settings" class="underline">Settings</a>.</div>'
    )


# ── Email: watchlist ──────────────────────────────────────────────────────────

@app.post("/watchlist/email", response_class=HTMLResponse)
async def email_watchlist(request: Request, db: Session = Depends(get_db)):
    """Send a watchlist price-snapshot email."""
    import os
    from app.notifiers.email import send_digest
    from app.notifiers.shopping_email import build_watchlist_html

    ns = db.query(models.NotificationSettings).first()
    smtp_user = (ns.smtp_user if ns else None) or os.getenv("SMTP_USER", "")
    smtp_pass = (ns.smtp_password if ns else None) or os.getenv("SMTP_PASSWORD", "")
    recipients = [r for r in [
        ns.email_address if ns else None,
        getattr(ns, "email_address_2", None) if ns else None,
        getattr(ns, "email_address_3", None) if ns else None,
    ] if r]

    if not smtp_user or not smtp_pass:
        return HTMLResponse(
            '<div id="wl-email-feedback" class="rounded-xl px-4 py-3 bg-amber-50 border border-amber-200 '
            'text-amber-800 text-sm mt-3">⚠️ SMTP credentials not configured. '
            'Go to <a href="/settings" class="underline">Settings</a> first.</div>'
        )
    if not recipients:
        return HTMLResponse(
            '<div id="wl-email-feedback" class="rounded-xl px-4 py-3 bg-amber-50 border border-amber-200 '
            'text-amber-800 text-sm mt-3">⚠️ No recipient email address configured in '
            '<a href="/settings" class="underline">Settings</a>.</div>'
        )

    _uid = request.session.get("user_id")
    entries = db.query(models.WatchlistEntry).join(models.Product).filter(
        models.WatchlistEntry.user_id == _uid
    ).all()
    entries_data = []
    for entry in entries:
        history = (
            db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_id == entry.product_id)
            .order_by(models.PriceRecord.scraped_at.desc())
            .limit(2)
            .all()
        )
        entries_data.append({
            "product": entry.product,
            "latest":  history[0] if history else None,
            "prev":    history[1] if len(history) > 1 else None,
        })

    os.environ["SMTP_USER"]     = smtp_user
    os.environ["SMTP_PASSWORD"] = smtp_pass

    app_url = str(request.base_url).rstrip("/")
    html    = build_watchlist_html(entries_data, app_url)
    n       = len(entries_data)
    subject = f"Watchlist — Price Snapshot ({n} product{'s' if n != 1 else ''})"
    ok      = send_digest(subject, html, recipients)

    if ok:
        to_str = ", ".join(recipients)
        return HTMLResponse(
            f'<div id="wl-email-feedback" class="rounded-xl px-4 py-3 bg-emerald-50 border border-emerald-200 '
            f'text-emerald-800 text-sm mt-3">✓ Watchlist email sent to {to_str}</div>'
        )
    return HTMLResponse(
        '<div id="wl-email-feedback" class="rounded-xl px-4 py-3 bg-red-50 border border-red-200 '
        'text-red-700 text-sm mt-3">✗ Failed to send email. Check your SMTP settings in '
        '<a href="/settings" class="underline">Settings</a>.</div>'
    )


@app.on_event("startup")
async def startup():
    import logging
    try:
        init_db()
    except Exception as e:
        logging.error("init_db failed: %s", e)
    # Load ScraperAPI key from DB if not set via env var
    try:
        from app.database import SessionLocal
        _startup_db = SessionLocal()
        try:
            ns = _startup_db.query(models.NotificationSettings).first()
            if ns and getattr(ns, "scraperapi_key", None):
                set_scraperapi_key(ns.scraperapi_key)
                logging.info("ScraperAPI key loaded from DB")
        except Exception as e:
            logging.warning("Could not load ScraperAPI key from DB: %s", e)
        finally:
            _startup_db.close()
    except Exception as e:
        logging.error("Startup DB load failed: %s", e)
