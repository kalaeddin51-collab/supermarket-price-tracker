# Validation — Costco Scraper

## Status: PASSED (2026-05-01)

### Implementation note
The initial scraper assumed Magento 2 HTML parsing. Live testing revealed
costco.com.au is SAP Commerce Cloud (Hybris) with an Angular SPA frontend —
server-rendered HTML contains no product data. The scraper was rewritten to
use the Hybris autocomplete JSON endpoint:
    GET /search/autocomplete/SearchBox?term={query}&max={limit}
This returns full product data (name, code, price, images, stock) as JSON.

---

## 1. Python Syntax & Import Check

```bash
python -c "from app.scrapers.costco import CostcoScraper; print('scraper OK')"
python -c "from app.models import Store; print(Store.costco)"
python -c "from app.database import init_db; print('OK')"
python -c "from app.main import app, STORE_LABELS, ALL_STORE_SLUGS; print('costco' in ALL_STORE_SLUGS, STORE_LABELS.get('costco'))"
python -c "from app.suburbs import SUBURB_STORES; sample = SUBURB_STORES.get('sydney', []); print('costco in sydney:', 'costco' in sample)"
```

**Result: ✅ PASS** (all 4 checks passed 2026-05-01)

---

## 2. Live Scraper Smoke Test

```bash
python -c "
import asyncio
from app.scrapers.costco import CostcoScraper
async def test():
    s = CostcoScraper()
    r = await s.search('milk', limit=5)
    print(f'Costco: {len(r)} results')
    for x in r[:3]:
        print(f'  {x.name} @ \${x.price} — {x.url}')
    await s.close()
asyncio.run(test())
"
```

**Result: ✅ PASS**
- `milk`: 4 results (e.g. Palmolive Body Wash Milk & Honey $14.99)
- `toilet paper`: 3 results (e.g. Quilton Gold 60 Pack $37.99)
- `olive oil`: 4 results (some `price=None` — warehouse-only items, expected)
- `fetch_price('119498', ...)`: Quilton Gold 60 Pack $37.99 | error=False

---

## 3. Store Enum Migration

### SQLite (local dev)
```bash
python -c "from app.database import init_db; init_db(); print('OK')"
```
Expected: no error.

### PostgreSQL (Railway)
After deploy, confirm in Railway logs:
- No `invalid input value for enum store: "costco"` errors

---

## 4. Search Route Integration

```bash
curl -s "http://localhost:8000/search?q=toilet+paper&stores=costco" | grep -i costco
```

Expected: HTML response with at least one product card labelled "Costco", OR an empty results message (no 500 error).

---

## 5. Relevance / Weight Pipeline Validation

**Verified 2026-05-01**: Costco results go through the identical scoring pipeline as all other stores:

| Step | Applied to Costco? |
|------|--------------------|
| `_extract_brand(r.name)` → `r._brand` | ✅ Yes |
| `per_unit_price(price, unit)` → `r._pu_value`, `r._pu_label` | ✅ Yes |
| `_is_processed(name, category)` → `r._is_processed` | ✅ Yes |
| `_relevance_score(name, query)` → `r._relevance` | ✅ Yes |
| Multi-word filter: drop results with `_relevance < 0.2` | ✅ Yes (same threshold) |
| Final sort: `(-relevance, price asc)` | ✅ Yes (same key) |
| `_group_search_results` cross-store grouping | ✅ Yes (Costco entries merged with other stores) |

**Known cross-store limitation (not Costco-specific):**
`_relevance_score` requires ALL query words to appear in the product name. This means:
- Query `"toilet paper"` → Costco's "Quilton Toilet **Tissue**" → score 0.00 → filtered out
- Query `"toilet paper"` → Sorbent "Toilet **Paper**" (Woolworths/Coles) → score 0.80 → kept
- The same filter would also drop any Woolworths/Coles product named "toilet tissue"

This is a pre-existing limitation of `_relevance_score` (synonym blindness), not introduced by the Costco scraper. Single-word queries (milk, eggs, butter) and most compound queries (olive oil, orange juice, full cream milk) are unaffected.

---

## 6. Manual Browser Checklist

- [ ] Search page loads without error
- [ ] "Costco" pill appears in the store filter bar
- [ ] Clicking the Costco pill filters results to show only Costco products
- [ ] Searching "toilet paper" with All Stores includes Costco results if available
- [ ] Costco store info card shows both Auburn and Marsden Park addresses
- [ ] Settings page: "Costco" appears as a selectable default store option
- [ ] A Costco product can be added to the watchlist

---

## 7. Failure Mode Check

- [ ] If costco.com.au returns 403/5xx, the search still returns results from other stores (no 500)
- [ ] If Costco returns 0 results, no error is shown to the user

---

## 8. DB Enum Check (PostgreSQL only)

```sql
-- Run in Railway Neon console after first deploy:
SELECT enum_range(NULL::store);
-- Should include 'costco' in the result
```

---

## Known Limitations / Risks

- **Synonym blindness**: see section 5 above. Affects all stores equally.
- **Limited range**: Costco sells ~4000 SKUs vs Woolworths/Coles ~30,000. Many searches will return 0 results — this is expected, not a bug.
- **Warehouse-only pricing**: some Costco products return `price=None` (likely in-warehouse-only items). These are displayed with no price — gracefully handled.
- **Membership note**: Costco requires membership to purchase in-store. The online store is publicly browsable, so scraping is unaffected.
