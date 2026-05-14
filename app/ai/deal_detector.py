"""
Genuine Deal Detector.

For each item in the user's consumption profile:
  1. Search their stores for that item
  2. Collect products that are on special or have a was_price significantly above current price
  3. Pass the collected specials to Gemini in a single prompt
  4. Gemini curates + ranks the genuine deals, filtering marketing noise

Returns up to 5 deal dicts, each with a one-sentence reason and a verdict.
"""
import asyncio
import json
from google import genai

from app.ai.agent import search_stores
from app.config import get_google_key

# Minimum discount to be considered worth evaluating (5%)
_MIN_DISCOUNT_PCT = 5


async def _collect_specials_for_item(item_name: str, user_stores: list[str]) -> list[dict]:
    """Search stores for one profile item and return only the results on special."""
    results = await search_stores(item_name, user_stores, limit=6)
    specials = []
    for r in results:
        on_special = r.get("on_special", False)
        was = r.get("was_price")
        now = r.get("price")

        # Also count items where was_price implies a meaningful discount
        if was and now and was > 0 and now > 0:
            pct_off = (1 - now / was) * 100
            if pct_off >= _MIN_DISCOUNT_PCT:
                on_special = True

        if on_special:
            discount_pct = 0
            if was and now and was > 0:
                discount_pct = round((1 - now / was) * 100)
            specials.append({**r, "profile_item": item_name, "discount_pct": discount_pct})

    return specials


async def find_deals(profile: list, user_stores: list[str], db=None) -> list[dict]:
    """
    Find and curate genuine deals for all items in the user's consumption profile.

    Returns a list of up to 5 deal dicts:
        {
            "product": str,
            "store_name": str,
            "store": str,
            "price": float,
            "was_price": float | None,
            "discount_pct": int,
            "url": str,
            "reason": str,
            "verdict": "buy now" | "worth it" | "skip",
        }
    """
    api_key = get_google_key()
    if not api_key or not profile:
        return []

    if not user_stores:
        user_stores = ["woolworths", "coles", "aldi"]

    # Collect specials for all profile items in parallel (cap at 10 items)
    items_to_check = profile[:10]
    tasks = [
        _collect_specials_for_item(item.item_name, user_stores)
        for item in items_to_check
    ]
    results_per_item = await asyncio.gather(*tasks, return_exceptions=True)

    all_specials: list[dict] = []
    for specials in results_per_item:
        if isinstance(specials, list):
            all_specials.extend(specials)

    if not all_specials:
        return []

    # Build profile summary for the prompt
    profile_lines = "\n".join(
        f"- {item.item_name}"
        + (f" (prefers: {item.brand_preference})" if item.brand_preference else "")
        + (f" — {item.notes}" if item.notes else "")
        for item in profile
    )

    prompt = f"""Analyse these current grocery specials and identify the top genuine deals for this shopper.

Shopper's regular items:
{profile_lines}

Current specials found (JSON):
{json.dumps(all_specials[:20], indent=2)}

Return the top 4–5 genuine deals as a raw JSON array (no markdown, no explanation — just the array).

Each deal object must have exactly these keys:
  "product"      — product name (string)
  "store_name"   — store display name (string, e.g. "Coles")
  "store"        — store slug (string, e.g. "coles")
  "price"        — current price as a number
  "was_price"    — original price as a number, or null
  "discount_pct" — percentage off as an integer (0 if unknown)
  "url"          — product URL (string)
  "reason"       — one sentence explaining why this is a genuine deal (string)
  "verdict"      — exactly one of: "buy now", "worth it", "skip"

Rules:
- Only include items that match something in the shopper's profile
- Exclude deals where the brand doesn't match the shopper's preference
- Use "buy now" only for genuinely exceptional savings (>20% off, low regular price)
- Use "worth it" for solid but modest deals (5–20% off)
- Use "skip" if the deal seems like marketing noise (e.g. tiny % off a rarely-needed item)
- Return raw JSON array only — no prose, no code fences"""

    client = genai.Client(api_key=api_key)
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # Strip markdown code fences if Gemini added them anyway
        if "```" in text:
            for part in text.split("```"):
                part = part.strip().lstrip("json").strip()
                if part.startswith("["):
                    text = part
                    break

        deals = json.loads(text)
        return deals if isinstance(deals, list) else []

    except (json.JSONDecodeError, Exception):
        return []
