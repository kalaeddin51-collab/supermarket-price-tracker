# Plan — Phase 4: Suburb & Store Selection

Numbered task groups in implementation order. Each group is independently reviewable.

---

## Group 1 — Suburb Data

1. Create `app/suburbs.py`:
   - `SUBURB_STORES: dict[str, list[str]]` — maps lowercase suburb name → list of store slugs
   - Start with Lower North Shore (Neutral Bay, Mosman, Cremorne, etc.) as the seed
   - Constants: `_W`, `_C`, `_A`, `_WCA`, `_HF_cammeray`, `_HF_mosman`, `_HF_lane_cove`, `_HF_broadway`, `_IGA_north_sydney`, `_IGA_milsons_point`, `_IGA_crows_nest`, `_IGA_newtown`, `_IGA_king_st`
   - `ALL_SUBURBS: list[str]` — sorted list of all suburb names (for autocomplete)
   - `POSTCODE_NAMES: dict[str, str]` — maps postcode string → canonical suburb name

2. Expand coverage to all Sydney LGAs (iteratively):
   - Eastern Suburbs: Bondi, Randwick, Coogee, Maroubra, Surry Hills, Paddington
   - Inner West: Newtown, Glebe, Balmain, Leichhardt, Marrickville, Petersham
   - North Shore: Chatswood, Pymble, Gordon, Hornsby, Wahroonga, Turramurra
   - Northern Beaches: Manly, Dee Why, Brookvale, Avalon, Mona Vale
   - Western Sydney: Parramatta, Auburn, Merrylands, Granville, Harris Park
   - South-West: Liverpool, Campbelltown, Camden, Narellan, Bankstown, Lakemba
   - Penrith / Blue Mountains: Penrith, St Marys, Mt Druitt, Katoomba
   - Sutherland Shire: Cronulla, Caringbah, Miranda, Engadine, Menai

3. All new suburbs beyond 15km from a Harris Farm / IGA get `_WCA` only.

## Group 2 — Geo Module

4. Create `app/geo.py`:
   - `SUBURB_COORDS: dict[str, tuple[float, float]]` — lat/lon centroids for all suburbs
   - `haversine(lat1, lon1, lat2, lon2) -> float` — distance in km
   - `nearby_suburbs(suburb: str, radius_km: float = 5) -> list[str]` — returns suburb names within radius
   - Used by `/stores-for-suburb` to surface extra nearby stores

## Group 3 — Landing Page Integration

5. Update `GET /` route in `main.py`:
   - Pass `ALL_SUBURBS` (for autocomplete) and `STORE_INFO` dict to template
   - If authenticated: load `UserPreference` and pass `saved_suburb`, `saved_stores` to template

6. Create `GET /stores-for-suburb` route:
   - Accept `suburb: str` query param
   - Look up `SUBURB_STORES[suburb.lower()]` → list of store slugs
   - Expand with `nearby_suburbs()` if result is fewer than 3 stores
   - Return HTML fragment: store card grid (store logo, address, maps link, checkbox)
   - Each HF card has `data-hf-slugs='["harris_farm_broadway"]'` data attribute
   - Each IGA card has `data-iga-slugs='["iga_newtown"]'` data attribute

7. Update `app/templates/landing.html`:
   - Suburb input: `<input list="suburb-list">` with `<datalist id="suburb-list">` populated from `ALL_SUBURBS`
   - Suburb input: HTMX `hx-get="/stores-for-suburb" hx-trigger="change" hx-target="#store-results"`
   - `#store-results` div: replaced by store card grid HTMX response
   - Alpine.js `selectedStores`: initialised from `data-saved-stores` attribute if authenticated
   - "All stores" button: sets `selectedStores` to all slugs in the current suburb's store list
   - Store checkboxes in the FILTER STORES sidebar (Woolworths, Coles, Aldi, Harris Farm, IGA):
     - Woolworths / Coles / Aldi: standard `toggleStore('woolworths')` etc.
     - Harris Farm: reads `[data-hf-slugs]` from `#store-results`, toggles all HF slugs as a group
     - IGA: reads `[data-iga-slugs]` from `#store-results`, toggles all IGA slugs as a group

## Group 4 — Search Page Store Pills

8. Update `POST /search` route:
   - Accept `stores` form field (comma-separated slugs)
   - If authenticated: upsert `UserPreference` with current suburb + stores
   - Pass `user_stores` list to `search.html` template

9. Update `app/templates/search.html`:
   - Render store pills using `{% set ns = namespace(...) %}` for Jinja2 loop scoping
   - For Woolworths / Coles: exact slug match on `user_stores`
   - For Harris Farm: scan `user_stores` for any slug starting with `harris_farm_` → use that slug + color `#F27200`
   - For IGA: group all IGA slugs under one pill labeled "IGA" + suburb suffix
   - Pill label: `{% if slug.startswith('harris_farm') %}Harris Farm{% else %}{{ store_label(slug) }}{% endif %}`

## Group 5 — Store Info Registry

10. Add `STORE_INFO` dict to `main.py`:
    - Keys: all store slugs
    - Values: `{full_name, address, maps_url, website}`
    - `STORE_LABELS` dict for short display names
    - `STORE_COLORS` dict for brand hex colours

11. Add `store_label(slug)` Jinja2 global function that looks up `STORE_LABELS[slug]` with fallback to slug title-cased.

## Group 6 — Verification

12. Test: enter "neutral bay" → store cards appear (Woolworths, Coles, Aldi, HF Cammeray, HF Mosman, IGA North Sydney)
13. Test: enter "bankstown" → Woolworths, Coles, Aldi cards appear (no Harris Farm — too far)
14. Test: click Harris Farm checkbox with Neutral Bay loaded → all HF location slugs added to `selectedStores`
15. Test: search from search page with HF selected → Harris Farm pill appears in header; search results include HF items
16. Test: log out → log in → saved suburb pre-fills, saved stores pre-select in Alpine.js
17. Push to Railway; verify `GET /stores-for-suburb?suburb=mosman` returns correct HTML fragment
