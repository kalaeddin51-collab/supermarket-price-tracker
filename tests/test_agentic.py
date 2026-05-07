"""
Tests for agentic features:
  - ConsumptionItem model creation
  - app/ai/agent.py — SCRAPER_MAP coverage, store_display_name, search_stores error handling
  - app/ai/nl_search.py — degrades gracefully without API key
  - app/ai/deal_detector.py — returns [] without API key or empty profile
  - Profile routes (GET /profile, POST/DELETE /api/profile/items) via FastAPI TestClient
  - NL search route — returns error HTML when key absent
  - Deals panel route — returns no_auth / no_profile states

Run with:  python -m pytest tests/test_agentic.py -v
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ─── ConsumptionItem model ───────────────────────────────────────────────────

class TestConsumptionItemModel:
    def test_model_has_required_fields(self):
        from app.models import ConsumptionItem
        cols = {c.key for c in ConsumptionItem.__table__.columns}
        assert "id" in cols
        assert "user_id" in cols
        assert "item_name" in cols
        assert "brand_preference" in cols
        assert "notes" in cols
        assert "created_at" in cols

    def test_table_name(self):
        from app.models import ConsumptionItem
        assert ConsumptionItem.__tablename__ == "consumption_items"

    def test_brand_preference_nullable(self):
        from app.models import ConsumptionItem
        col = ConsumptionItem.__table__.columns["brand_preference"]
        assert col.nullable is True

    def test_notes_nullable(self):
        from app.models import ConsumptionItem
        col = ConsumptionItem.__table__.columns["notes"]
        assert col.nullable is True


# ─── agent.py ────────────────────────────────────────────────────────────────

class TestAgentModule:
    def test_scraper_map_contains_major_stores(self):
        from app.ai.agent import SCRAPER_MAP
        for slug in ("woolworths", "coles", "aldi", "costco"):
            assert slug in SCRAPER_MAP, f"{slug} missing from SCRAPER_MAP"

    def test_scraper_map_contains_harris_farm_locations(self):
        from app.ai.agent import SCRAPER_MAP
        for slug in ("harris_farm_cammeray", "harris_farm_mosman",
                     "harris_farm_lane_cove", "harris_farm_broadway"):
            assert slug in SCRAPER_MAP

    def test_scraper_map_contains_iga_locations(self):
        from app.ai.agent import SCRAPER_MAP
        for slug in ("iga_north_sydney", "iga_milsons_point",
                     "iga_crows_nest", "iga_newtown", "iga_king_st"):
            assert slug in SCRAPER_MAP

    def test_store_display_name_known(self):
        from app.ai.agent import store_display_name
        assert store_display_name("woolworths") == "Woolworths"
        assert store_display_name("coles") == "Coles"
        assert store_display_name("costco") == "Costco"

    def test_store_display_name_unknown_falls_back(self):
        from app.ai.agent import store_display_name
        result = store_display_name("some_unknown_slug")
        assert "Unknown" in result or len(result) > 0  # graceful fallback

    def test_search_stores_unknown_slug_returns_empty(self):
        from app.ai.agent import search_stores
        result = asyncio.get_event_loop().run_until_complete(
            search_stores("milk", ["not_a_real_store"], limit=3)
        )
        assert result == []

    def test_search_stores_empty_list_returns_empty(self):
        from app.ai.agent import search_stores
        result = asyncio.get_event_loop().run_until_complete(
            search_stores("milk", [], limit=3)
        )
        assert result == []

    def test_search_stores_scraper_exception_returns_empty(self):
        """A scraper that raises should not propagate — returns [] for that store."""
        from app.ai.agent import search_stores
        with patch("app.ai.agent.SCRAPER_MAP", {"woolworths": "app.scrapers.woolworths.WoolworthsScraper"}):
            with patch("importlib.import_module") as mock_import:
                mock_cls = MagicMock()
                mock_instance = MagicMock()
                mock_instance.search = AsyncMock(side_effect=Exception("boom"))
                mock_instance.close = AsyncMock()
                mock_cls.return_value = mock_instance
                mock_module = MagicMock()
                mock_module.WoolworthsScraper = mock_cls
                mock_import.return_value = mock_module

                result = asyncio.get_event_loop().run_until_complete(
                    search_stores("milk", ["woolworths"], limit=3)
                )
                assert result == []


# ─── nl_search.py ────────────────────────────────────────────────────────────

class TestNLSearch:
    def test_returns_error_when_no_api_key(self):
        from app.ai.nl_search import run_nl_search
        with patch("app.ai.nl_search.get_anthropic_key", return_value=""):
            result = asyncio.get_event_loop().run_until_complete(
                run_nl_search("cheap milk", [], ["coles", "woolworths"])
            )
        assert result["error"] is not None
        assert len(result["error"]) > 0
        assert result["results"] == []
        assert result["summary"] == ""

    def test_result_has_required_keys(self):
        from app.ai.nl_search import run_nl_search
        with patch("app.ai.nl_search.get_anthropic_key", return_value=""):
            result = asyncio.get_event_loop().run_until_complete(
                run_nl_search("eggs", [], [])
            )
        assert "summary" in result
        assert "results" in result
        assert "error" in result

    def test_format_profile_empty(self):
        from app.ai.nl_search import _format_profile
        out = _format_profile([])
        assert "no shopping profile" in out.lower()

    def test_format_profile_with_items(self):
        from app.ai.nl_search import _format_profile
        item = MagicMock()
        item.item_name = "chicken breast"
        item.brand_preference = None
        item.notes = "free range"
        out = _format_profile([item])
        assert "chicken breast" in out
        assert "free range" in out
        assert "any brand" in out.lower()

    def test_format_profile_with_brand(self):
        from app.ai.nl_search import _format_profile
        item = MagicMock()
        item.item_name = "greek yoghurt"
        item.brand_preference = "Chobani"
        item.notes = None
        out = _format_profile([item])
        assert "Chobani" in out

    def test_build_system_includes_stores(self):
        from app.ai.nl_search import _build_system
        stores = ["coles", "woolworths", "aldi"]
        sys_prompt = _build_system([], stores)
        for s in stores:
            assert s in sys_prompt

    def test_build_system_without_stores_uses_defaults(self):
        from app.ai.nl_search import _build_system
        sys_prompt = _build_system([], [])
        # Should fall back to some default store list
        assert "woolworths" in sys_prompt or "coles" in sys_prompt


# ─── deal_detector.py ────────────────────────────────────────────────────────

class TestDealDetector:
    def test_returns_empty_without_api_key(self):
        from app.ai.deal_detector import find_deals
        with patch("app.ai.deal_detector.get_anthropic_key", return_value=""):
            result = asyncio.get_event_loop().run_until_complete(
                find_deals([], ["coles"])
            )
        assert result == []

    def test_returns_empty_with_empty_profile(self):
        from app.ai.deal_detector import find_deals
        with patch("app.ai.deal_detector.get_anthropic_key", return_value="fake-key"):
            result = asyncio.get_event_loop().run_until_complete(
                find_deals([], ["coles", "woolworths"])
            )
        assert result == []

    def test_collects_specials_discount_calculation(self):
        from app.ai.deal_detector import _collect_specials_for_item
        fake_result = {
            "name": "Chicken Breast 1kg",
            "price": 8.00,
            "was_price": 10.00,
            "on_special": False,
            "store": "coles",
            "store_name": "Coles",
            "unit": "1kg",
            "url": "http://example.com",
            "image_url": None,
        }
        with patch("app.ai.deal_detector.search_stores", new=AsyncMock(return_value=[fake_result])):
            specials = asyncio.get_event_loop().run_until_complete(
                _collect_specials_for_item("chicken breast", ["coles"])
            )
        # 20% discount — should be included
        assert len(specials) == 1
        assert specials[0]["discount_pct"] == 20
        assert specials[0]["profile_item"] == "chicken breast"

    def test_collects_specials_ignores_small_discount(self):
        from app.ai.deal_detector import _collect_specials_for_item
        fake_result = {
            "name": "Milk 2L",
            "price": 2.95,
            "was_price": 3.00,    # only 1.7% off — below 5% threshold
            "on_special": False,
            "store": "woolworths",
            "store_name": "Woolworths",
            "unit": "2L",
            "url": "http://example.com",
            "image_url": None,
        }
        with patch("app.ai.deal_detector.search_stores", new=AsyncMock(return_value=[fake_result])):
            specials = asyncio.get_event_loop().run_until_complete(
                _collect_specials_for_item("milk", ["woolworths"])
            )
        assert specials == []

    def test_collects_specials_includes_on_special_flag(self):
        from app.ai.deal_detector import _collect_specials_for_item
        fake_result = {
            "name": "Eggs 12pk",
            "price": 4.50,
            "was_price": None,
            "on_special": True,   # flag set even without was_price
            "store": "aldi",
            "store_name": "Aldi",
            "unit": "12pk",
            "url": "http://example.com",
            "image_url": None,
        }
        with patch("app.ai.deal_detector.search_stores", new=AsyncMock(return_value=[fake_result])):
            specials = asyncio.get_event_loop().run_until_complete(
                _collect_specials_for_item("eggs", ["aldi"])
            )
        assert len(specials) == 1


# ─── Profile routes (FastAPI TestClient) ────────────────────────────────────

class TestProfileRoutes:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_profile_page_redirects_when_unauthenticated(self, client):
        r = client.get("/profile", follow_redirects=False)
        assert r.status_code in (303, 401)

    def test_add_profile_item_redirects_when_unauthenticated(self, client):
        r = client.post("/api/profile/items",
                        data={"item_name": "milk"},
                        follow_redirects=False)
        assert r.status_code in (303, 401)

    def test_delete_profile_item_redirects_when_unauthenticated(self, client):
        r = client.delete("/api/profile/items/999", follow_redirects=False)
        assert r.status_code in (303, 401)


# ─── AI endpoint routes ───────────────────────────────────────────────────────

class TestAIRoutes:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_nl_search_returns_200(self, client):
        """NL search endpoint must return 200 (error displayed inline, not 4xx)."""
        r = client.post("/api/nl-search",
                        data={"query": "cheap eggs"},
                        follow_redirects=False)
        assert r.status_code == 200

    def test_nl_search_without_key_returns_error_html(self, client):
        with patch("app.ai.nl_search.get_anthropic_key", return_value=""):
            r = client.post("/api/nl-search",
                            data={"query": "cheap eggs"},
                            follow_redirects=False)
        assert r.status_code == 200
        assert "error" in r.text.lower() or "unavailable" in r.text.lower() or "api key" in r.text.lower()

    def test_deals_panel_unauthenticated_returns_200(self, client):
        r = client.get("/partials/deals", follow_redirects=False)
        assert r.status_code == 200

    def test_deals_panel_unauthenticated_shows_login_prompt(self, client):
        r = client.get("/partials/deals")
        assert r.status_code == 200
        assert "log in" in r.text.lower() or "login" in r.text.lower()


# ─── Seed Sarah smoke test ────────────────────────────────────────────────────

class TestSeedSarah:
    def test_seed_script_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "scripts", "seed_sarah.py")
        assert os.path.isfile(path), "scripts/seed_sarah.py must exist"

    def test_sarah_exists_in_db(self):
        from app.database import SessionLocal, init_db
        from app.models import User, ConsumptionItem
        init_db()
        db = SessionLocal()
        try:
            sarah = db.query(User).filter(User.email == "sarah@example.com").first()
            assert sarah is not None, "Sarah test persona not found in DB — run scripts/seed_sarah.py"
            items = db.query(ConsumptionItem).filter(
                ConsumptionItem.user_id == sarah.id
            ).all()
            assert len(items) >= 10, f"Expected ≥10 profile items for Sarah, got {len(items)}"
        finally:
            db.close()

    def test_sarah_has_neutral_bay_suburb(self):
        from app.database import SessionLocal
        from app.models import User, UserPreference
        db = SessionLocal()
        try:
            sarah = db.query(User).filter(User.email == "sarah@example.com").first()
            if sarah is None:
                pytest.skip("Sarah not seeded")
            pref = db.query(UserPreference).filter(
                UserPreference.user_id == sarah.id
            ).first()
            assert pref is not None
            assert "neutral bay" in (pref.suburb or "").lower()
        finally:
            db.close()

    def test_sarah_has_correct_stores(self):
        from app.database import SessionLocal
        from app.models import User, UserPreference
        db = SessionLocal()
        try:
            sarah = db.query(User).filter(User.email == "sarah@example.com").first()
            if sarah is None:
                pytest.skip("Sarah not seeded")
            pref = db.query(UserPreference).filter(
                UserPreference.user_id == sarah.id
            ).first()
            assert pref is not None
            stores = [s.strip() for s in (pref.stores or "").split(",") if s.strip()]
            assert "woolworths" in stores
            assert "coles" in stores
            assert "aldi" in stores
            assert "harris_farm_cammeray" in stores
        finally:
            db.close()


if __name__ == "__main__":
    import traceback
    passed = failed = skipped = 0
    classes = [
        TestConsumptionItemModel, TestAgentModule, TestNLSearch,
        TestDealDetector, TestProfileRoutes, TestAIRoutes, TestSeedSarah,
    ]
    for cls in classes:
        inst = cls()
        for name in [m for m in dir(inst) if m.startswith("test_")]:
            # skip fixtures
            if name == "client":
                continue
            try:
                # inject client fixture for route tests
                import inspect
                sig = inspect.signature(getattr(inst, name))
                if "client" in sig.parameters:
                    skipped += 1
                    print(f"  SKIP  {cls.__name__}.{name} (needs pytest fixture)")
                    continue
                getattr(inst, name)()
                print(f"  PASS  {cls.__name__}.{name}")
                passed += 1
            except pytest.skip.Exception as e:
                print(f"  SKIP  {cls.__name__}.{name}: {e}")
                skipped += 1
            except Exception as e:
                print(f"  FAIL  {cls.__name__}.{name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
