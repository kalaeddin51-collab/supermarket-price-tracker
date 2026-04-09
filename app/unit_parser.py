"""
Unit parsing and normalised price utilities for fair cross-store comparisons.

Common base units:
  Volume  → millilitres (mL)
  Weight  → grams (g)
  Count   → each
"""
import re


# ── Conversion tables ────────────────────────────────────────────────────────

_VOLUME_TO_ML = {
    "ml": 1, "millilitre": 1, "millilitres": 1, "milliliter": 1, "milliliters": 1,
    "l": 1000, "litre": 1000, "litres": 1000, "liter": 1000, "liters": 1000,
}

_WEIGHT_TO_G = {
    "g": 1, "gram": 1, "grams": 1,
    "kg": 1000, "kilogram": 1000, "kilograms": 1000,
    "mg": 0.001,
}

_COUNT_ALIASES = {"ea", "each", "pk", "pack", "pck", "x", "pc", "pcs",
                  "piece", "pieces", "ct", "count", "serve", "serves",
                  "sachet", "sachets", "tab", "tablets", "capsule", "capsules"}


# ── Embedded-price helper ────────────────────────────────────────────────────

def _extract_embedded_price(unit_str: str) -> tuple[float | None, str]:
    """
    Detect store cup-strings that embed the per-unit rate directly, e.g.
      "$1.75 per L"   → (1.75, "L")
      "$0.80 per 100g"→ (0.80, "100g")
      "1.20/100mL"    → (1.20, "100mL")

    Returns (embedded_price, unit_portion) when matched, else (None, unit_str).
    The unit_portion is passed back through parse_unit to get the base quantity.
    """
    s = unit_str.strip()
    # "$X.XX per <unit>" or "X.XX per <unit>"
    m = re.match(r'^\$?([\d]+(?:[.,]\d+)?)\s+per\s+(.+)$', s, re.IGNORECASE)
    if m:
        try:
            return (float(m.group(1).replace(",", ".")), m.group(2).strip())
        except ValueError:
            pass
    # "$X.XX/<unit>" or "X.XX/<unit>"
    m = re.match(r'^\$?([\d]+(?:[.,]\d+)?)\s*/\s*(.+)$', s, re.IGNORECASE)
    if m:
        try:
            return (float(m.group(1).replace(",", ".")), m.group(2).strip())
        except ValueError:
            pass
    return (None, unit_str)


# ── Core parse ───────────────────────────────────────────────────────────────

def parse_unit(unit_str: str) -> tuple[float, str]:
    """
    Parse a unit string and return (quantity_in_base_unit, category).
    category is one of: 'volume', 'weight', 'count', 'unknown'.

    Handles fixed-package sizes, loose-weight/volume sold per unit, and
    embedded-price cup strings from store APIs.

    Examples
    --------
    "2L"            → (2000.0, 'volume')
    "500mL"         → (500.0,  'volume')
    "1kg"           → (1000.0, 'weight')
    "500g"          → (500.0,  'weight')
    "6 pack"        → (6.0,    'count')
    "each"          → (1.0,    'count')
    "375mL can"     → (375.0,  'volume')
    "per kg"        → (1000.0, 'weight')   ← loose weight
    "per 100g"      → (100.0,  'weight')   ← loose weight
    "per L"         → (1000.0, 'volume')   ← loose volume
    "$1.75 per L"   → (1000.0, 'volume')   ← Woolworths cup string
    "kg"            → (1000.0, 'weight')   ← standalone unit symbol
    "L"             → (1000.0, 'volume')   ← standalone unit symbol
    ""              → (1.0,    'unknown')
    """
    if not unit_str:
        return (1.0, "unknown")

    s = unit_str.strip()

    # ── Strip embedded price prefix (e.g. "$1.75 per L" → "L") ──────────────
    _, s = _extract_embedded_price(s)

    # ── Strip "$X.XX each" style (price per unit embedded before "each") ─────
    # e.g. "$0.83 each" → "each"
    s = re.sub(r'^\$?[\d.,]+\s+', '', s)

    # ── Strip leading "per " for loose-weight/volume products ────────────────
    s = re.sub(r'^per\s+', '', s, flags=re.IGNORECASE)

    # ── Volume ────────────────────────────────────────────────────────────────
    m = re.search(r"([\d]+(?:[.,]\d+)?)\s*"
                  r"(millilitre[s]?|milliliter[s]?|litre[s]?|liter[s]?|ml|l\b)",
                  s, re.IGNORECASE)
    if m:
        qty = float(m.group(1).replace(",", "."))
        key = m.group(2).lower().rstrip("s")
        if key in ("ml", "millilitre", "milliliter"):
            return (qty, "volume")
        elif key in ("l", "litre", "liter"):
            return (qty * 1000.0, "volume")

    # ── Weight ────────────────────────────────────────────────────────────────
    m = re.search(r"([\d]+(?:[.,]\d+)?)\s*(kg|kilogram[s]?|g(?:ram[s]?)?)",
                  s, re.IGNORECASE)
    if m:
        qty = float(m.group(1).replace(",", "."))
        key = m.group(2).lower()
        if key.startswith("kg") or key.startswith("kilo"):
            return (qty * 1000.0, "weight")
        else:  # g / gram
            return (qty, "weight")

    # ── Count ─────────────────────────────────────────────────────────────────
    # "6 pack", "12 x", "24 pk", "6 ea", "30 tablets"
    m = re.search(r"(\d+)\s*(?:x\b\s*|"
                  r"(?:pack|pck|pk|ea|each|pcs?|pieces?|ct|count|serves?|sachets?|tabs?|tablets?|capsules?)\b)",
                  s, re.IGNORECASE)
    if m:
        return (float(m.group(1)), "count")

    # standalone alias with no leading number → "each", "ea"
    if s.lower() in _COUNT_ALIASES:
        return (1.0, "count")

    # bare integer / decimal (e.g. "6", "1.5")
    m = re.fullmatch(r"[\d]+(?:[.,]\d+)?", s.strip())
    if m:
        return (float(m.group().replace(",", ".")), "count")

    # ── Standalone unit symbol with no leading number ─────────────────────────
    # Handles "kg", "L", "g", "mL" after stripping "per " prefix
    m = re.fullmatch(r'(litre[s]?|liter[s]?|l)', s, re.IGNORECASE)
    if m:
        return (1000.0, "volume")
    m = re.fullmatch(r'(millilitre[s]?|milliliter[s]?|ml)', s, re.IGNORECASE)
    if m:
        return (1.0, "volume")
    m = re.fullmatch(r'(kg|kilogram[s]?)', s, re.IGNORECASE)
    if m:
        return (1000.0, "weight")
    m = re.fullmatch(r'(g(?:ram[s]?)?)', s, re.IGNORECASE)
    if m:
        return (1.0, "weight")

    return (1.0, "unknown")


# ── Per-unit price ────────────────────────────────────────────────────────────

def per_unit_price(price: float, unit_str: str) -> tuple[float | None, str]:
    """
    Return (normalised_price, display_label).
    normalised_price is price-per-base-unit for sorting (not display-scaled).
    display_label is a human-readable string like "$1.75/L" or "$2.50/100g".

    For embedded-price cup strings (e.g. "$1.75 per L"), the embedded rate
    is used directly rather than dividing the package price by a quantity.

    Returns (None, '') if the unit is unknown or qty is zero.
    """
    # If the unit string contains an embedded per-unit price, use it directly.
    # e.g. "$1.75 per L" → treat as per_unit_price(1.75, "L")
    embedded_price, unit_only = _extract_embedded_price(unit_str)
    if embedded_price is not None:
        return per_unit_price(embedded_price, unit_only)

    qty, category = parse_unit(unit_str)
    if qty <= 0 or category == "unknown":
        return (None, "")

    price_per_base = price / qty  # price per mL or per g or per each

    if category == "volume":
        # Display as /L unless ridiculously small
        per_l = price_per_base * 1000.0
        if per_l >= 1.00:
            return (price_per_base, f"${per_l:.2f}/L")
        per_100ml = price_per_base * 100.0
        return (price_per_base, f"${per_100ml:.2f}/100mL")

    elif category == "weight":
        per_kg = price_per_base * 1000.0
        if per_kg >= 1.00:
            return (price_per_base, f"${per_kg:.2f}/kg")
        per_100g = price_per_base * 100.0
        return (price_per_base, f"${per_100g:.2f}/100g")

    elif category == "count" and qty > 1:
        per_ea = price_per_base
        return (price_per_base, f"${per_ea:.2f}/ea")

    return (None, "")


# ── Basket cost ───────────────────────────────────────────────────────────────

def basket_cost(
    price: float,
    product_unit: str,
    desired_qty: float,
    desired_unit: str,
) -> float:
    """
    How much does it cost to fulfil `desired_qty desired_unit` from a
    product priced at `price` for `product_unit`?

    If units are compatible:
      cost = (price / product_base) × desired_base

    Otherwise falls back to:
      cost = price × desired_qty

    Examples
    --------
    Buy 2 L of milk; product is "2L" @ $3.50  → $3.50
    Buy 2 L of milk; product is "1L" @ $1.90  → $3.80
    Buy 500g cheese; product is "200g" @ $4   → $10.00
    Buy 1 (no unit); product is "2L" @ $3.50  → $3.50
    """
    prod_qty, prod_cat = parse_unit(product_unit)

    # Parse the desired unit SEPARATELY from the quantity to avoid ambiguous
    # strings like "1.0660g" (1.0 + "660g") being mis-parsed as 1.066 g.
    # Instead: parse_unit("660g") → (660.0, "weight"), then multiply by desired_qty.
    # Guard against None/0 qty (legacy DB rows may have NULL).
    safe_qty = float(desired_qty) if desired_qty is not None else 1.0
    if desired_unit:
        unit_base, des_cat = parse_unit(desired_unit)
        des_qty = safe_qty * unit_base   # scale into base units (mL, g, each)
    else:
        des_qty, des_cat = (safe_qty, "unknown")

    # Compatible units → compute proportional cost
    if (prod_cat == des_cat
            and prod_cat in ("volume", "weight", "count")
            and prod_qty > 0
            and des_qty > 0):
        price_per_base = price / prod_qty
        return round(price_per_base * des_qty, 4)

    # Fallback: raw price × qty
    return round(price * safe_qty, 4)


# ── Comparison key for sorting ────────────────────────────────────────────────

def comparison_key(price: float, unit_str: str) -> float:
    """
    Return a price value suitable for sorting results by true value.
    Uses price-per-base-unit when parseable, otherwise raw price.
    This ensures a 2L bottle @ $3.50 ($1.75/L) ranks above a 1L @ $2.50.
    """
    pu, _ = per_unit_price(price, unit_str)
    return pu if pu is not None else price
