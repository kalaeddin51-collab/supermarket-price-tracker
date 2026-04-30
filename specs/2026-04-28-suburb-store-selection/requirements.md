# Requirements — Phase 4: Suburb & Store Selection

## Scope

Phase 4 makes store selection location-aware. A user enters their Sydney suburb on the landing page, and the app shows only the stores that serve that suburb. Saved suburb and store preferences are persisted per user account so the next session starts pre-filtered.

## Decisions

### Suburb → Store Mapping (`suburbs.py`)
- Hand-curated Python dict mapping suburb name (lowercase) → list of store slugs.
- Covers 600+ Sydney suburbs across all LGAs (as of April 2026).
- Postcode-to-name reverse lookup also provided (`POSTCODE_NAMES` dict) so users can type a postcode.
- Each suburb entry specifies which store slugs serve it. Harris Farm and IGA entries are location-specific (e.g., `harris_farm_broadway`, `iga_newtown`).
- Woolworths, Coles, and Aldi use uniform national pricing — included for all Sydney suburbs.
- Constants for readability:
  - `_W` = `["woolworths"]`
  - `_C` = `["coles"]`
  - `_A` = `["aldi"]`
  - `_WCA` = `["woolworths", "coles", "aldi"]` (the default set for all suburbs)
  - `_HF_*` = Harris Farm location slug list (used only for nearby suburbs)
  - `_IGA_*` = IGA location slug list (used only for nearby suburbs)

### Geo Expansion (`geo.py`)
- `nearby_suburbs(suburb, radius_km=5)` — returns a list of suburbs within `radius_km` of the given suburb's centroid.
- Implemented using a haversine distance table keyed on suburb name.
- Used to expand the store list: if a user lives in a suburb adjacent to a Harris Farm, that store is included even if the user's exact suburb isn't directly served.
- Centroid coordinates stored as `SUBURB_COORDS` dict in `geo.py`.

### Landing Page UX
- Suburb input field with autocomplete from `ALL_SUBURBS` list.
- On suburb selection: HTMX `GET /stores-for-suburb?suburb={name}` → returns the nearby store cards HTML fragment.
- Store cards: each shows the store logo, full address, and Google Maps link.
- Selecting a store (checkbox) updates Alpine.js `selectedStores` array.
- "All stores" shortcut: selects all slugs returned for the suburb.

### Store Preferences Persistence
- `UserPreference` model: `suburb` (string) + `stores` (comma-separated slugs).
- On login: load saved suburb and stores → pre-fill `selectedStores` Alpine.js state via `data-saved-stores` attribute in the template.
- On `POST /search`: if user is authenticated, save current suburb + stores to `UserPreference` (upsert).
- Anonymous users: preferences stored in `localStorage` only (Alpine.js `savePreferences()` / `loadPreferences()`).

### Harris Farm Checkbox Logic
Harris Farm presents a UX challenge because there is no single `harris_farm` slug — stores are location-specific (`harris_farm_broadway`, `harris_farm_cammeray`, etc.). The landing page "Harris Farm" checkbox must:
- Read the actual HF location slugs from the nearby stores panel (via `[data-hf-slugs]` data attribute)
- Toggle all found HF slugs as a group
- Show as checked if **any** HF location slug is in `selectedStores`

IGA has the same issue and is handled identically.

### Search Page Store Pills
On the search page, active stores are shown as colored pills (e.g., green Woolworths pill, orange Harris Farm pill). The pills are rendered server-side from `user_stores` (the list of slugs from the request). Harris Farm requires:
- Scanning `user_stores` for any slug starting with `harris_farm_`
- Using Jinja2 namespace scoping (`{% set ns = namespace(...) %}`) for loop-variable mutation

### Store Info Registry
`STORE_INFO` dict in `main.py` provides for each store slug:
- `full_name` (e.g., "Harris Farm Markets — Broadway")
- `address` (street address for display)
- `maps_url` (Google Maps link)
- `website`

Used on the landing page store card grid.

## Context
- This phase is the most visible to users — every search starts from this store selection.
- The `suburbs.py` coverage must be maintained as the app expands beyond the North Shore.
- The Harris Farm / IGA multi-slug pattern is a recurring source of bugs — any new generic store checkbox must follow the same HF pattern (read slugs from DOM, toggle by prefix).

See `specs/mission.md` Section "User Personas" for why suburb-based selection matters.

## Out of Scope
- Postcode-based GPS auto-detection (browser Geolocation API) — future improvement
- User-configurable radius expansion for nearby suburb lookup
- Displaying store opening hours
- Stock levels per store (not available from any current API)
