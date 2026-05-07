# Phase 8 — PWA & Mobile

## Goal
Make the app installable on Android/iOS and substantially more usable on small screens.

## Scope

### In scope
- Web App Manifest (`manifest.json`) with app name, theme colour, icons, display mode
- SVG icons at 192×192 and 512×512 (shopping cart, brand green)
- `<meta name="theme-color">` and apple-touch meta tags in base.html
- Mount `/static` in main.py (currently imported but not mounted)
- Mobile bottom tab bar (fixed, 5 tabs: Search, List, Watchlist, Profile, More)
  - "More" opens a slide-up sheet with Dashboard, Settings, Contact, Sign out
  - Top nav links hidden on mobile (≤sm); tab bar hidden on ≥sm
  - Body padding-bottom on mobile to avoid content hiding under tab bar
- Service worker (basic, cache-first for app shell) — optional / stretch goal

### Out of scope (later)
- VAPID push notifications (requires backend subscription management)
- Barcode scanner (camera API — separate feature)
- Offline full data sync

## Key Decisions
- SVG icons are fine for Android Chrome manifest; iOS needs apple-touch-icon PNG but we use a data-URI workaround
- Bottom nav uses Alpine for the "More" sheet
- No build step — SVG icons served as static files, no icon generation pipeline
- Tailwind breakpoints: `sm` = 640px. Bottom nav shows below 640px.

## Context
- FastAPI + Jinja2 + Alpine.js + HTMX
- Static files at `app/static/` — needs `app.mount("/static", ...)` in main.py
- base.html is the single template that all pages extend
