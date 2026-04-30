# Validation — Phase 2: Store Scrapers

Phase 2 is complete and ready to merge when all criteria below pass.

---

## 1. Scraper Unit Tests (`tests/`)

Run with:
```bash
pytest tests/ -v
```

Required:

### Unit Parser
- `parse_unit_price("$3.50 / 100g", 3.50)` → `(0.035, "$3.50/100g")`
- `parse_unit_price("$14.00 / L", 14.00)` → `(0.014, "$14.00/L")`
- `parse_unit_price("nonsense", 1.00)` → `(None, None)`

### Product Grouping
- Two products with identical base name + same brand → merged into one group
- Two products with different brands → two separate groups
- Cheapest per-unit price is first in `group["entries"]`
- `savings_label` is non-empty when a group has 2+ priced entries with different per-unit prices

---

## 2. Live Scraper Smoke Tests

Run manually (not in CI — hits live endpoints):

```bash
python -c "
import asyncio
from app.scrapers.coles import ColesScraper
async def test():
    s = ColesScraper()
    r = await s.search('milk', limit=5)
    print(f'Coles: {len(r)} results, first: {r[0].name} @ \${r[0].price}')
    await s.close()
asyncio.run(test())
"
```

### Required results:
- **Coles**: ≥3 results for "milk", prices present, per-unit values parsed
- **Harris Farm (Broadway)**: ≥1 result for "milk" or "pasta", price present
- **IGA (North Sydney or Newtown)**: ≥1 result for "milk", price present
- **Aldi**: ≥1 result for any active catalogue item (may return 0 for off-catalogue queries — acceptable)
- **Woolworths** (if `SCRAPERAPI_KEY` set locally): ≥3 results for "milk"

---

## 3. Search Route Integration

- `POST /search` with `query=milk&stores=woolworths,coles` → HTTP 200
- Response HTML contains at least one product group card
- Group card shows store pill (green for Woolworths, red for Coles)
- Per-unit price displayed when cup string is available
- ☆ Watch button present on each product card

---

## 4. Manual Browser Checklist

- [ ] Search "milk" with Coles selected → results appear within 5 seconds
- [ ] Search "olive oil" with Harris Farm Broadway selected → at least one Harris Farm result appears
- [ ] Search "pasta" with multiple stores → results are grouped (same product appears in one card, not two separate cards)
- [ ] Savings label appears when one store is cheaper per unit (e.g., "save $1.20/100g")
- [ ] `/debug/woolworths?q=milk` returns JSON (not 500)
- [ ] If no `SCRAPERAPI_KEY` set: Woolworths returns 0 results gracefully (no error shown to user, other stores still load)

---

## 5. Error Handling

- Simulate Woolworths timeout: set `timeout=0.001` in scraper and confirm search still returns Coles/HF results
- Confirm: failing scraper does NOT cause the entire search to return a 500 error
