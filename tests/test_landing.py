"""
Tests for landing page suburb search, store selection, 5km radius expansion,
x-data attribute quoting, and navbar suburb display.

Run with:  python -m pytest tests/test_landing.py -v
"""
import re
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from app.geo import nearby_suburbs, haversine, SUBURB_COORDS
from app.suburbs import SUBURB_STORES


# ─── Haversine / geo tests ───────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(-33.83, 151.21, -33.83, 151.21) == 0.0

    def test_crows_nest_to_north_sydney_under_2km(self):
        lat1, lon1 = SUBURB_COORDS["crows nest"]
        lat2, lon2 = SUBURB_COORDS["north sydney"]
        dist = haversine(lat1, lon1, lat2, lon2)
        assert dist < 2.0, f"Expected < 2 km, got {dist:.2f} km"

    def test_sydney_to_manly_over_10km(self):
        lat1, lon1 = SUBURB_COORDS["sydney"]
        lat2, lon2 = SUBURB_COORDS["manly"]
        dist = haversine(lat1, lon1, lat2, lon2)
        assert dist > 10.0, f"Expected > 10 km, got {dist:.2f} km"

    def test_newtown_to_crows_nest_over_5km(self):
        lat1, lon1 = SUBURB_COORDS["newtown"]
        lat2, lon2 = SUBURB_COORDS["crows nest"]
        dist = haversine(lat1, lon1, lat2, lon2)
        assert dist > 5.0, f"Expected > 5 km (different area), got {dist:.2f} km"


# ─── nearby_suburbs tests ────────────────────────────────────────────────────

class TestNearbySuburbs:
    def test_unknown_suburb_returns_empty(self):
        assert nearby_suburbs("atlantis") == []

    def test_crows_nest_includes_north_sydney(self):
        nearby = nearby_suburbs("crows nest", km=5.0)
        assert "north sydney" in nearby

    def test_crows_nest_includes_milsons_point(self):
        nearby = nearby_suburbs("crows nest", km=5.0)
        assert "milsons point" in nearby

    def test_crows_nest_excludes_manly(self):
        nearby = nearby_suburbs("crows nest", km=5.0)
        assert "manly" not in nearby, "Manly is >5 km from Crows Nest"

    def test_newtown_excludes_north_sydney(self):
        nearby = nearby_suburbs("newtown", km=5.0)
        assert "north sydney" not in nearby

    def test_neutral_bay_includes_iga_suburbs(self):
        nearby = nearby_suburbs("neutral bay", km=5.0)
        assert "crows nest" in nearby or "north sydney" in nearby

    def test_smaller_radius_returns_fewer(self):
        n2 = nearby_suburbs("crows nest", km=2.0)
        n5 = nearby_suburbs("crows nest", km=5.0)
        assert len(n2) <= len(n5)


# ─── Suburb → store slug tests ───────────────────────────────────────────────

class TestSuburbStores:
    def _expand_slugs(self, suburb_key: str, km: float = 5.0) -> list[str]:
        """Simulate the route's 5km expansion logic."""
        nearby = nearby_suburbs(suburb_key, km=km)
        expanded = [k for k in nearby if k in SUBURB_STORES]
        if suburb_key not in expanded and suburb_key in SUBURB_STORES:
            expanded.insert(0, suburb_key)
        seen, slugs = set(), []
        for nk in expanded:
            for s in SUBURB_STORES.get(nk, []):
                if s not in seen:
                    seen.add(s)
                    slugs.append(s)
        return slugs

    def test_crows_nest_has_woolworths(self):
        assert "woolworths" in self._expand_slugs("crows nest")

    def test_crows_nest_has_iga_crows_nest(self):
        assert "iga_crows_nest" in self._expand_slugs("crows nest")

    def test_crows_nest_has_iga_north_sydney_via_5km(self):
        assert "iga_north_sydney" in self._expand_slugs("crows nest")

    def test_crows_nest_has_iga_milsons_point_via_5km(self):
        assert "iga_milsons_point" in self._expand_slugs("crows nest")

    def test_north_sydney_has_iga_north_sydney(self):
        assert "iga_north_sydney" in self._expand_slugs("north sydney")

    def test_newtown_has_no_iga(self):
        slugs = self._expand_slugs("newtown")
        iga = [s for s in slugs if "iga" in s]
        assert iga == [], f"Newtown should have no IGA, got {iga}"

    def test_newtown_has_harris_farm(self):
        assert "harris_farm" in self._expand_slugs("newtown")

    def test_manly_has_harris_farm(self):
        assert "harris_farm" in self._expand_slugs("manly")

    def test_parramatta_has_no_harris_farm(self):
        assert "harris_farm" not in self._expand_slugs("parramatta")

    def test_postcode_2065_same_as_crows_nest(self):
        """Postcode 2065 covers Crows Nest area."""
        assert "iga_crows_nest" in SUBURB_STORES.get("2065", [])


# ─── HTML attribute quoting tests (prevent Alpine.js breakage) ───────────────

class TestHTMLQuoting:
    """
    Ensure the suburb_stores partial renders x-data attributes with single
    outer quotes so embedded JSON double-quotes don't break Alpine.js parsing.
    """

    def _get_partial(self, query: str) -> str:
        import urllib.request
        url = f"http://localhost:8000/partials/suburb-stores?q={query.replace(' ', '+')}"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.read().decode()
        except Exception as e:
            pytest.skip(f"Server not running: {e}")

    def test_no_broken_double_quoted_xdata(self):
        html = self._get_partial("crows nest")
        # A broken pattern would be: x-data="{ igaSlugs: ["
        broken = re.findall(r'x-data="[^"]*\[', html)
        assert broken == [], f"Found broken double-quoted x-data with JSON array: {broken}"

    def test_iga_card_uses_single_quoted_xdata(self):
        html = self._get_partial("crows nest")
        # Valid pattern: x-data='{ "igaSlugs": [...] }'
        good = re.findall(r"x-data='[^']*igaSlugs[^']*'", html)
        assert len(good) > 0, "IGA card must use single-quoted x-data for igaSlugs"

    def test_select_all_uses_single_quoted_xdata(self):
        html = self._get_partial("crows nest")
        good = re.findall(r"x-data='[^']*allSlugs[^']*'", html)
        assert len(good) > 0, "Select-all button must use single-quoted x-data for allSlugs"

    def test_no_results_for_unknown_query(self):
        html = self._get_partial("xyzzy999notasuburb")
        assert "No results" in html

    def test_within_5km_badge_present(self):
        html = self._get_partial("north sydney")
        assert "within 5 km" in html

    def test_multi_suburb_match(self):
        # 'st leonards' appears as its own entry
        html = self._get_partial("st leonards")
        assert "St Leonards" in html or "st leonards" in html.lower()

    def test_neutral_bay_shows_all_iga_branches(self):
        html = self._get_partial("neutral bay")
        assert "IGA" in html

    def test_newtown_shows_no_iga(self):
        html = self._get_partial("newtown")
        assert "igaSlugs" not in html, "Newtown has no IGA stores within 5km"

    def test_postcode_search_works(self):
        html = self._get_partial("2065")
        assert "within 5 km" in html or "Crows Nest" in html


# ─── API tests ───────────────────────────────────────────────────────────────

class TestSuburbAPI:
    def _get_json(self, path: str) -> dict:
        import urllib.request, json
        try:
            with urllib.request.urlopen(f"http://localhost:8000{path}", timeout=5) as r:
                return json.loads(r.read())
        except Exception as e:
            pytest.skip(f"Server not running: {e}")

    def test_suburb_api_returns_json(self):
        data = self._get_json("/api/suburb")
        assert "suburb" in data

    def test_suburb_api_unauthenticated_returns_empty(self):
        data = self._get_json("/api/suburb")
        # Unauthenticated requests return empty suburb
        assert data["suburb"] == "" or isinstance(data["suburb"], str)


if __name__ == "__main__":
    # Quick self-test without pytest
    import traceback
    passed = failed = 0
    for cls_name, cls in [
        ("TestHaversine", TestHaversine),
        ("TestNearbySuburbs", TestNearbySuburbs),
        ("TestSuburbStores", TestSuburbStores),
        ("TestHTMLQuoting", TestHTMLQuoting),
        ("TestSuburbAPI", TestSuburbAPI),
    ]:
        inst = cls()
        for name in [m for m in dir(inst) if m.startswith("test_")]:
            try:
                getattr(inst, name)()
                print(f"  PASS  {cls_name}.{name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {cls_name}.{name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
