"""
Shared scraper execution utilities for the AI agent.

Maps store slugs to scraper classes and exposes search_stores() —
a parallel multi-store search that returns structured dicts the LLM can reason over.
Uses importlib to avoid circular imports with app.main.
"""
import asyncio
import importlib


# slug → "module.ClassName" — mirrors the _scraper_map in main.py
SCRAPER_MAP: dict[str, str] = {
    "woolworths":            "app.scrapers.woolworths.WoolworthsScraper",
    "coles":                 "app.scrapers.coles.ColesScraper",
    "aldi":                  "app.scrapers.aldi.AldiScraper",
    "costco":                "app.scrapers.costco.CostcoScraper",
    "harris_farm":           "app.scrapers.harris_farm.HarrisFarmScraper",
    "harris_farm_cammeray":  "app.scrapers.harris_farm.HarrisFarmCammerayScraper",
    "harris_farm_mosman":    "app.scrapers.harris_farm.HarrisFarmMosmanScraper",
    "harris_farm_lane_cove": "app.scrapers.harris_farm.HarrisFarmLaneCoveScraper",
    "harris_farm_broadway":  "app.scrapers.harris_farm.HarrisFarmBroadwayScraper",
    "iga_north_sydney":      "app.scrapers.iga.IGANorthSydneyScraper",
    "iga_milsons_point":     "app.scrapers.iga.IGAMilsonsPointScraper",
    "iga_crows_nest":        "app.scrapers.iga.IGACrowsNestScraper",
    "iga_newtown":           "app.scrapers.iga.IGANewtownScraper",
    "iga_king_st":           "app.scrapers.iga.IGAKingStreetScraper",
}

_DISPLAY_NAMES: dict[str, str] = {
    "woolworths":            "Woolworths",
    "coles":                 "Coles",
    "aldi":                  "Aldi",
    "costco":                "Costco",
    "harris_farm":           "Harris Farm",
    "harris_farm_cammeray":  "Harris Farm Cammeray",
    "harris_farm_mosman":    "Harris Farm Mosman",
    "harris_farm_lane_cove": "Harris Farm Lane Cove",
    "harris_farm_broadway":  "Harris Farm Broadway",
    "iga_north_sydney":      "IGA North Sydney",
    "iga_milsons_point":     "IGA Milsons Point",
    "iga_crows_nest":        "IGA Crows Nest",
    "iga_newtown":           "IGA Newtown",
    "iga_king_st":           "IGA King Street",
}


def store_display_name(slug: str) -> str:
    return _DISPLAY_NAMES.get(slug, slug.replace("_", " ").title())


async def _search_one_store_ai(store_slug: str, query: str, limit: int = 5) -> list[dict]:
    """Search a single store and return structured dicts. Returns [] on any error."""
    module_path = SCRAPER_MAP.get(store_slug)
    if not module_path:
        return []
    try:
        module_name, class_name = module_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        Cls = getattr(module, class_name)
        scraper = Cls()
        results = await scraper.search(query, limit=limit)
        await scraper.close()
        return [
            {
                "name": r.name,
                "price": r.price,
                "was_price": r.was_price,
                "on_special": r.on_special,
                "store": store_slug,
                "store_name": store_display_name(store_slug),
                "unit": r.unit,
                "url": r.url,
                "image_url": r.image_url,
            }
            for r in results
            if r.price is not None
        ]
    except Exception:
        return []


async def search_stores(query: str, stores: list[str], limit: int = 5) -> list[dict]:
    """Search multiple stores in parallel. Returns a flat list of product dicts."""
    valid_slugs = [s for s in stores if s in SCRAPER_MAP]
    if not valid_slugs:
        return []
    tasks = [_search_one_store_ai(slug, query, limit) for slug in valid_slugs]
    results_per_store = await asyncio.gather(*tasks, return_exceptions=True)
    flat: list[dict] = []
    for r in results_per_store:
        if isinstance(r, list):
            flat.extend(r)
    return flat
