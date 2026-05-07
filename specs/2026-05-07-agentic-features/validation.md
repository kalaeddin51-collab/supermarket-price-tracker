# Validation — Agentic Features

---

## 1. Consumption Profile

- [ ] `/profile` requires login — anonymous user is redirected to `/login`
- [ ] Add item (name only, no brand) → appears in list without "brand: …" label
- [ ] Add item with brand → appears with brand label
- [ ] Delete item → removed from list without page reload
- [ ] Profile items persist across logout/login

---

## 2. Natural Language Search

- [ ] "✨ Ask AI" button on search page toggles NL input
- [ ] Type query → spinner shows → results render in results area
- [ ] Summary text appears above results
- [ ] Without API key configured → shows "API key not configured" message (not 500)
- [ ] Anonymous user with no profile → still works, searches default stores
- [ ] Logged-in user with profile → searches use profile context

---

## 3. Deal Detector

- [ ] Deals panel loads lazily on search page (does not block page render)
- [ ] Without API key → panel shows "AI analysis not available" message
- [ ] Without profile → panel shows "Add items to your profile" prompt
- [ ] With profile + API key → deals render with product name, store, discount %, reason
- [ ] Verdict badge shows correct colour (green = buy now, amber = worth it, gray = skip)
- [ ] Panel shows loading spinner while AI is running

---

## 4. Error Handling

- [ ] Scraper failure for one store → other stores still return results (no 500)
- [ ] All scrapers fail → NL search returns "No results found" gracefully
- [ ] Anthropic API rate limit / error → both features show friendly error message
- [ ] ConsumptionItem table auto-created on Railway deploy (no migration needed)

---

## 5. Performance

- [ ] NL search completes in < 20s for a 2-product query
- [ ] Deal detector panel completes in < 30s for 5 profile items across 3 stores
- [ ] Regular search page load is not blocked by AI features
