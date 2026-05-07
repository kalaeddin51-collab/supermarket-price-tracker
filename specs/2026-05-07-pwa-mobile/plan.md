# Phase 8 — PWA & Mobile — Implementation Plan

1. Create `app/static/icon.svg` — 512×512 shopping cart SVG, brand green (#059669)
2. Create `app/static/manifest.json` — name, icons, theme_color, display standalone
3. Mount `/static` in `app/main.py` via `app.mount("/static", StaticFiles(...))`
4. Add to `base.html` `<head>`:
   - `<link rel="manifest" href="/static/manifest.json">`
   - `<meta name="theme-color" content="#059669">`
   - `<meta name="apple-mobile-web-app-capable" content="yes">`
   - `<meta name="apple-mobile-web-app-status-bar-style" content="default">`
   - `<link rel="apple-touch-icon" href="/static/icon.svg">`
5. Add mobile bottom tab bar to `base.html` (below `<main>`):
   - Fixed bottom, `block sm:hidden`, 5 items: Search, List, Watchlist, Profile, More
   - More button opens Alpine-controlled slide-up sheet with remaining links
   - Active state driven by `page` template variable
6. Add `pb-20 sm:pb-0` to `<main>` so content isn't obscured on mobile
7. Update roadmap.md to mark Phase 8 in-progress
