"""
Email HTML builders for:
  - Shopping list price comparison (across all stores)
  - Watchlist snapshot (current prices for all watched items)
"""
import json
from datetime import datetime

STORE_ORDER = [
    "woolworths", "coles", "harris_farm",
    "iga_crows_nest", "iga_milsons_point", "iga_north_sydney",
]
STORE_LABELS = {
    "woolworths":        "Woolworths",
    "coles":             "Coles",
    "harris_farm":       "Harris Farm",
    "iga_crows_nest":    "IGA Crows Nest",
    "iga_milsons_point": "IGA Milsons Point",
    "iga_north_sydney":  "IGA North Sydney",
}

_HEADER_CSS = (
    "font-family:Arial,sans-serif;max-width:700px;margin:0 auto;"
    "padding:20px;color:#333"
)
_TABLE_CSS  = "width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-top:none"
_TH_CSS     = ("padding:8px 12px;text-align:{align};font-size:11px;"
               "color:#6b7280;text-transform:uppercase;white-space:nowrap")
_TD_CSS     = "padding:8px 12px;border-bottom:1px solid #f0f0f0"


def _footer(app_url: str) -> str:
    link = (f' · <a href="{app_url}" style="color:#9ca3af">{app_url}</a>'
            if app_url else "")
    return (
        f'<p style="font-size:11px;color:#9ca3af;margin-top:16px;text-align:center">'
        f'Price Tracker · {datetime.now().strftime("%d %b %Y %H:%M")}{link}</p>'
    )


# ── Shopping List Email ───────────────────────────────────────────────────────

def build_shopping_list_html(list_name: str, items, app_url: str = "") -> str:
    """
    Builds a price-comparison HTML email for a shopping list.
    items — list of ShoppingListItem ORM objects (with .matched_results JSON field).
    Columns: Item | <one per store found in results> | Best Price
    Footer row: TOTAL per store, cheapest highlighted.
    """
    # Collect which stores actually appear across all items
    stores_seen: list[str] = []
    items_parsed: list[tuple] = []   # (item, results_by_store_dict)
    for item in items:
        by_store: dict[str, dict] = {}
        if item.matched_results:
            try:
                for r in json.loads(item.matched_results):
                    s = r.get("store", "")
                    if s:
                        by_store[s] = r
                        if s not in stores_seen:
                            stores_seen.append(s)
            except Exception:
                pass
        items_parsed.append((item, by_store))

    active_stores = [s for s in STORE_ORDER if s in stores_seen]

    # ── Header row ────────────────────────────────────────────────────────────
    store_headers = ""
    for s in active_stores:
        store_headers += (
            f'<th style="{_TH_CSS.format(align="right")}">'
            f'{STORE_LABELS.get(s, s)}</th>'
        )
    store_headers += (
        f'<th style="{_TH_CSS.format(align="right")};color:#059669">Best Price</th>'
    )

    # ── Item rows ────────────────────────────────────────────────────────────
    store_totals: dict[str, float] = {s: 0.0 for s in active_stores}
    store_counts: dict[str, int]   = {s: 0   for s in active_stores}
    rows_html = ""

    for item, by_store in items_parsed:
        # Find cheapest store for this item
        min_price: float | None = None
        min_store: str | None   = None
        for s in active_stores:
            r = by_store.get(s)
            if r and r.get("price") is not None:
                p = float(r["price"])
                if min_price is None or p < min_price:
                    min_price, min_store = p, s

        # Item label
        qty = item.qty or 1.0
        qty_str = ""
        if qty != 1.0:
            qty_str = (f"×{int(qty)}" if qty == int(qty) else f"×{qty}")

        row = (
            f'<tr>'
            f'<td style="{_TD_CSS};font-weight:600">{item.name}'
            + (f' <span style="color:#9ca3af;font-weight:400;font-size:12px">'
               f'{qty_str}</span>' if qty_str else "")
            + "</td>"
        )

        # Price cells
        for s in active_stores:
            r = by_store.get(s)
            if r and r.get("price") is not None:
                p = float(r["price"])
                is_best = (s == min_store)
                bg    = "background:#f0fdf4;" if is_best else ""
                color = "color:#059669;font-weight:700" if is_best else "color:#374151"
                mark  = " ✓" if is_best else ""
                store_totals[s] += p
                store_counts[s] += 1
                row += (
                    f'<td style="{_TD_CSS};text-align:right;{bg}">'
                    f'<span style="{color}">${p:.2f}{mark}</span></td>'
                )
            else:
                row += (
                    f'<td style="{_TD_CSS};text-align:right;color:#d1d5db">—</td>'
                )

        # Best Price cell
        if min_price is not None:
            row += (
                f'<td style="{_TD_CSS};text-align:right;background:#f0fdf4">'
                f'<span style="color:#059669;font-weight:700">${min_price:.2f}</span>'
                f'<br><span style="font-size:11px;color:#6b7280">'
                f'{STORE_LABELS.get(min_store or "", min_store or "")}</span></td>'
            )
        else:
            row += f'<td style="{_TD_CSS};text-align:right;color:#d1d5db">—</td>'

        row += "</tr>"
        rows_html += row

    # ── Totals row ────────────────────────────────────────────────────────────
    filled = [(s, store_totals[s]) for s in active_stores if store_counts.get(s, 0) > 0]
    best_total_store, best_total = (min(filled, key=lambda x: x[1])
                                    if filled else (None, None))

    totals_row = (
        '<tr style="background:#f9fafb">'
        f'<td style="{_TD_CSS};font-weight:700;font-size:13px">TOTAL</td>'
    )
    n_items = len(items_parsed)
    for s in active_stores:
        cnt = store_counts.get(s, 0)
        if cnt > 0:
            t  = store_totals[s]
            ib = s == best_total_store
            bg    = "background:#f0fdf4;" if ib else ""
            color = "color:#059669;font-weight:700;" if ib else ""
            cov   = f" ({cnt}/{n_items})" if cnt < n_items else ""
            totals_row += (
                f'<td style="{_TD_CSS};text-align:right;{bg}{color}">'
                f'${t:.2f}'
                f'<span style="font-size:11px;color:#9ca3af;font-weight:400">{cov}</span>'
                f'</td>'
            )
        else:
            totals_row += f'<td style="{_TD_CSS};text-align:right;color:#d1d5db">—</td>'

    if best_total is not None:
        totals_row += (
            f'<td style="{_TD_CSS};text-align:right;background:#f0fdf4">'
            f'<span style="color:#059669;font-weight:700">${best_total:.2f}</span>'
            f'<br><span style="font-size:11px;color:#6b7280">'
            f'{STORE_LABELS.get(best_total_store or "", best_total_store or "")}</span></td>'
        )
    else:
        totals_row += "<td></td>"
    totals_row += "</tr>"

    # Warning if any items not yet searched
    unsearched = sum(1 for item, _ in items_parsed if not item.matched_results)
    warn_html  = ""
    if unsearched:
        warn_html = (
            f'<p style="font-size:12px;color:#b45309;background:#fffbeb;'
            f'border:1px solid #fde68a;border-radius:6px;padding:8px 12px;margin-top:12px">'
            f'⚠️ {unsearched} item(s) have not been searched yet. '
            f'Use "Search All Stores" on the shopping list page to get prices first.</p>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="{_HEADER_CSS}">
  <div style="background:#059669;color:white;padding:16px 20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0;font-size:18px">🛒 Shopping List — {list_name}</h2>
    <p style="margin:4px 0 0;font-size:12px;opacity:.8">
      {datetime.now().strftime('%A, %d %B %Y')} · {n_items} item{'s' if n_items != 1 else ''}
    </p>
  </div>
  <table style="{_TABLE_CSS}">
    <thead>
      <tr style="background:#f9fafb">
        <th style="{_TH_CSS.format(align='left')}">Item</th>
        {store_headers}
      </tr>
    </thead>
    <tbody>
      {rows_html}
      {totals_row}
    </tbody>
  </table>
  {warn_html}
  {_footer(app_url)}
</body>
</html>"""


# ── Watchlist Email ───────────────────────────────────────────────────────────

def build_watchlist_html(entries_data: list[dict], app_url: str = "") -> str:
    """
    Builds a watchlist snapshot HTML email.
    entries_data — list of dicts: {product, latest (PriceRecord|None), prev (PriceRecord|None)}
    """
    rows = ""
    specials_count = 0

    for item in entries_data:
        product = item["product"]
        latest  = item.get("latest")
        prev    = item.get("prev")

        store_raw = (
            product.store.value
            if hasattr(product.store, "value")
            else str(product.store)
        )
        store_label = STORE_LABELS.get(store_raw, store_raw)

        price_str = f"${latest.price:.2f}" if latest and latest.price else "—"
        was_str   = (f"${latest.was_price:.2f}"
                     if latest and latest.was_price else "—")

        # Price change vs previous scrape
        change_html = ""
        if latest and prev and latest.price and prev.price:
            diff = latest.price - prev.price
            if diff < 0:
                change_html = (
                    f' &nbsp;<span style="color:#059669;font-size:11px">'
                    f'▼ ${abs(diff):.2f}</span>'
                )
            elif diff > 0:
                change_html = (
                    f' &nbsp;<span style="color:#dc2626;font-size:11px">'
                    f'▲ ${diff:.2f}</span>'
                )

        on_special = bool(latest and latest.on_special)
        if on_special:
            specials_count += 1
        special_cell = (
            '<span style="color:#ea580c;font-weight:600;background:#fff7ed;'
            'padding:2px 6px;border-radius:4px;font-size:11px">🏷 ON SPECIAL</span>'
            if on_special
            else '<span style="color:#d1d5db">—</span>'
        )

        unit_html = (
            f'<br><span style="color:#9ca3af;font-size:11px">{product.unit}</span>'
            if product.unit else ""
        )

        rows += f"""
        <tr>
          <td style="{_TD_CSS}">
            <strong>{product.name}</strong>{unit_html}
          </td>
          <td style="{_TD_CSS};white-space:nowrap">{store_label}</td>
          <td style="{_TD_CSS};text-align:right;font-weight:700">
            {price_str}{change_html}
          </td>
          <td style="{_TD_CSS};text-align:right;text-decoration:line-through;color:#9ca3af">
            {was_str}
          </td>
          <td style="{_TD_CSS}">{special_cell}</td>
        </tr>"""

    n = len(entries_data)
    subtitle = f"{n} product{'s' if n != 1 else ''} tracked"
    if specials_count:
        subtitle += f" · {specials_count} on special 🏷"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="{_HEADER_CSS}">
  <div style="background:#4f46e5;color:white;padding:16px 20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0;font-size:18px">👁 Watchlist — Price Snapshot</h2>
    <p style="margin:4px 0 0;font-size:12px;opacity:.8">
      {datetime.now().strftime('%A, %d %B %Y')} · {subtitle}
    </p>
  </div>
  <table style="{_TABLE_CSS}">
    <thead>
      <tr style="background:#f9fafb">
        <th style="{_TH_CSS.format(align='left')}">Product</th>
        <th style="{_TH_CSS.format(align='left')}">Store</th>
        <th style="{_TH_CSS.format(align='right')}">Current Price</th>
        <th style="{_TH_CSS.format(align='right')}">Was</th>
        <th style="{_TH_CSS.format(align='left')}">Special</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  {_footer(app_url)}
</body>
</html>"""
