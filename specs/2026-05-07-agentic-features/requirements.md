# Requirements — Agentic Features: NL Search + Deal Detector + Consumption Profile

_May 2026_

---

## Problem

The app is a rule-based scraper. The user must know exactly what to search for, manually
set alert thresholds, and mentally compare results. Intelligence is entirely in the
developer's code — none of it is model-driven.

---

## Goal

Add an AI reasoning layer on top of the existing scraper infrastructure, making the app
genuinely agentic: a model plans what to search for, executes tool calls (scrapers),
observes results, and synthesises recommendations.

---

## Features in Scope

### 1. Consumption Profile
A per-user list of products they buy regularly, with optional brand preference.

- Fields: `item_name` (e.g. "chicken breast"), `brand_preference` (nullable, e.g. "Mainland"),
  `notes` (nullable, e.g. "free range only")
- HTMX-powered inline add / delete — no page reload
- Requires authentication (anonymous users see a prompt to log in)
- Used as persistent context by both NL Search and Deal Detector

### 2. Natural Language Search
User types intent instead of a product name. Claude interprets it using their profile
as context, decides what to search for, calls the scrapers as tools, and returns a
curated response with a brief text summary.

- Uses Claude with tool use (agentic loop: plan → tool call → observe → synthesise)
- Gracefully falls back if `ANTHROPIC_API_KEY` is not configured
- Results render in the same area as regular search results (HTMX swap)
- Integrated into the search page as an "✨ Ask AI" toggle

### 3. Genuine Deal Detector
Searches for specials on all items in the user's consumption profile, then uses Claude
to filter out fake discounts (raised price then "discounted") and surface only real deals.

- Runs as a lazy-loaded HTMX panel at the top of the search page
- Uses `on_special` flag and `was_price` vs `price` delta as primary signals
- Claude evaluates and ranks deals, adds a one-sentence reason per deal
- Verdict per deal: "buy now" | "worth it" | "skip"

---

## Out of Scope

- Price history analysis (requires richer `PriceRecord` data for profile items)
- Trip optimizer (cross-store cart splitting)
- Receipt scanner (requires vision model + OCR pipeline)
- Saving NL search history

---

## Key Decisions

### Model Choice
Use `claude-3-5-haiku-20241022` for both features — fast and cheap for high-frequency
scraper-augmented tool use. The deal detector in particular may run on every search
page load for logged-in users with a profile.

### Tool Use Pattern
The NL Search agent runs a proper agentic loop (up to 8 rounds) so Claude can make
sequential or parallel search decisions. The deal detector is a single-shot prompt
(no tool use) because the scraper calls happen before the LLM is invoked.

### Scraper Reuse
All scraper classes are reused unchanged. The AI module (`app/ai/agent.py`) wraps them
with `importlib` to avoid circular imports, mirroring the pattern already in `main.py`.

### Anthropic API Key
Configured via `ANTHROPIC_API_KEY` environment variable (Railway Variables).
Both features degrade gracefully if the key is absent — show a setup prompt rather
than an error page.

### Auth Requirement
- Consumption Profile: requires login (items are per-user)
- NL Search: works anonymously (no profile context, uses default stores)
- Deal Detector: requires login + profile items (returns empty panel otherwise)
