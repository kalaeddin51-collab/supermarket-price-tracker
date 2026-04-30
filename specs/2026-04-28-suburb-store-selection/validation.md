# Validation — Phase 4: Suburb & Store Selection

Phase 4 is complete and ready to merge when all criteria below pass.

---

## 1. Suburb Coverage

```python
from app.suburbs import SUBURB_STORES, ALL_SUBURBS, POSTCODE_NAMES

assert "neutral bay" in SUBURB_STORES
assert "bankstown" in SUBURB_STORES
assert "penrith" in SUBURB_STORES
assert "katoomba" in SUBURB_STORES
assert "manly" in SUBURB_STORES
assert len(ALL_SUBURBS) >= 400
assert "2200" in POSTCODE_NAMES  # Bankstown
assert POSTCODE_NAMES["2065"] == "st leonards"  # or nearest canonical suburb
```

---

## 2. Store Mapping Correctness

```python
from app.suburbs import SUBURB_STORES

# Near North Shore — should have Harris Farm
neutral_bay = SUBURB_STORES["neutral bay"]
assert "woolworths" in neutral_bay
assert "coles" in neutral_bay
assert any(s.startswith("harris_farm_") for s in neutral_bay)
assert any(s.startswith("iga_") for s in neutral_bay)

# Western suburbs — should NOT have Harris Farm (too far)
bankstown = SUBURB_STORES["bankstown"]
assert "woolworths" in bankstown
assert "coles" in bankstown
assert not any(s.startswith("harris_farm_") for s in bankstown)
```

---

## 3. Geo Module

```python
from app.geo import nearby_suburbs, haversine

# Haversine sanity check
dist = haversine(-33.83, 151.22, -33.86, 151.21)  # ~3-4 km
assert 2 < dist < 6

# Nearby suburbs
nearby = nearby_suburbs("neutral bay", radius_km=5)
assert "mosman" in nearby or "cremorne" in nearby
```

---

## 4. Landing Page (Browser)

- [ ] Type "neutral bay" in suburb input → store card grid appears with correct stores
- [ ] Type "2200" (Bankstown postcode) → autocomplete resolves to "bankstown", correct stores shown
- [ ] Click Harris Farm checkbox → **all** nearby HF location slugs added to `selectedStores` (not just `harris_farm`)
- [ ] Click Aldi checkbox → `aldi` added / removed from `selectedStores`
- [ ] Click "All stores" → all suburb store slugs added
- [ ] Suburb change → store grid updates (previous stores cleared, new stores shown)
- [ ] Log in → saved suburb auto-fills, saved stores pre-checked

---

## 5. Search Page Store Pills (Browser)

- [ ] Search with Woolworths + Harris Farm Broadway selected → green Woolworths pill + orange "Harris Farm Broadway" pill visible
- [ ] Search with IGA selected → red IGA pill visible
- [ ] Pill label for Harris Farm: shows "Harris Farm" or store-name with suburb suffix (not "harris_farm_broadway")
- [ ] Search with only Coles selected → only red Coles pill visible

---

## 6. Preference Persistence

- [ ] Logged in, select "neutral bay" + Woolworths + Coles → search → log out → log in → suburb is still "neutral bay", Woolworths + Coles still selected
- [ ] Anonymous: preferences saved to localStorage → refresh page → stores still selected (Alpine.js `loadPreferences()`)

---

## 7. Known Bugs to Verify Fixed

These bugs were identified and fixed during Phase 4 — confirm each is resolved:

- [ ] **Harris Farm checkbox on landing page**: clicking "Harris Farm" in the FILTER STORES sidebar correctly toggles all nearby HF location slugs (not a generic `harris_farm` slug that doesn't exist in the suburb's store list)
- [ ] **Harris Farm pill on search page**: when `user_stores` contains `harris_farm_broadway` (or any HF slug), the orange Harris Farm pill appears on the search page (not missing due to exact string match `"harris_farm" in user_stores`)
- [ ] **Watchlist add for non-logged-in users**: clicking ☆ Watch shows an inline "Please log in" message rather than a silent failure
- [ ] **Jinja2 namespace scoping**: `{% set ns = namespace(...) %}` used correctly so Harris Farm slug accumulates across the for-loop
