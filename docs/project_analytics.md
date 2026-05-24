---
name: SemirDashboard Analytics Engine
description: Analytics engine, return visit formula, season logic, tab functions, shop detail, Excel export
type: project
---

## CRITICAL: Return Visit Formula (LOCKED — do not change without user approval)
**File:** `App/analytics/calculations.py` → `calculate_return_visits(purchases_sorted, reg_date)`

```python
if registration_date == first_purchase_date:
    return_visits = total_invoices - 1  # Reg-day purchase is NOT a return
else:
    return_visits = total_invoices      # All invoices count as returns

is_returning = (return_visits > 0)
return_rate = returning_customers / total_customers * 100
```

**Key rule:** Counts INVOICES, not unique visit days. Intentional, confirmed by user.

---

## Season Definitions
**File:** `App/analytics/season_utils.py`

| Season | Months | Label format |
|--------|--------|-------------|
| M2-4 | Feb, Mar, Apr | `M2-4 2025` |
| M5-7 | May, Jun, Jul | `M5-7 2025` |
| M8-10 | Aug, Sep, Oct | `M8-10 2025` |
| M11-1 | Nov, Dec, Jan | `M11-1 2024-2025` (cross-year: Jan belongs to next year) |

**M11-1 label:** `f"M11-1 {y-1}-{y}"` where `y` is the January year.
Example: Nov-Dec 2024 + Jan 2025 → `M11-1 2024-2025`.

**Old definition (OBSOLETE):** SS = Jan-Jun, AW = Jul-Dec → do NOT use.

## Week Format
`get_week_info(d)` → `(sort_key 'YYYY-WNN', label 'Week N (d/m-d/m)')`
Example: `('2025-W01', 'Week 1 (30/12-5/1)')`

## Grade Hierarchy
**File:** `App/analytics/season_utils.py` → `GRADE_ORDER`
```python
GRADE_ORDER = {'No Grade': 0, 'Member': 1, 'Silver': 2, 'Gold': 3, 'Diamond': 4}
```
**NOT** VIP0/VIP1/VIP2/VIP3/DIAMOND — that's obsolete.

---

## Shop Group Logic
- Filter param: `shop_group`
- `"Bala Group"` → shop_name contains "Bala" or "巴拉"
- `"Semir Group"` → shop_name contains "Semir" or "森马"
- `"Others Group"` → all other shops

---

## Analytics Pipeline (Sales Analytics)
**Entry:** `App/analytics/core.py` → `calculate_return_rate_analytics(date_from, date_to, shop_group)`

1. `_load_sales()` fetches `SalesTransaction` (5 fields only) + pre-loads `Customer` table separately (avoids JOIN on 118K rows)
2. Builds `customer_purchases` map: `{vip_id: [sorted invoices]}`
3. Passes to aggregators: `aggregate_by_grade`, `aggregate_by_season`, `aggregate_by_month`

---

## Tab Functions (KEY file)
**File:** `App/analytics/tab_functions.py`

This file powers ALL lazy-loaded AJAX tabs and the shop detail page.

### `_load_sales(date_from, date_to, shop_group)`
- Cached 5 min by `(date_from, date_to, shop_group)` key
- Returns `(customer_purchases, customer_info_fn, date_stats)` or `(None, None, None)`

### Sales analytics tabs
`get_sales_tab(tab, date_from, date_to, shop_group)` — called by `analytics_tab` view

| tab | content |
|-----|---------|
| `grade` | grade breakdown + overview metrics + buyer_without_info stats |
| `season` | by season |
| `month` | by month |
| `week` | by week |
| `shop` | by shop |
| `grade_allshops` | grade breakdown across all shops |
| `season_allshops` | season across all shops |
| `month_allshops` | month across all shops |
| `week_allshops` | week across all shops |

### Coupon analytics tabs
`get_coupon_tab(tab, date_from, date_to, coupon_id_prefix, shop_group)` — called by `coupon_tab` view

| tab | content |
|-----|---------|
| `shop` | by shop (loaded on initial page) |
| `detail` | coupon detail rows |
| `duplicates` | invoices with multiple coupons |

### Customer comparison tabs
`get_customer_tab(tab, start_date, end_date)` — called by `customer_tab` CNV view

| tab | content |
|-----|---------|
| `bd_season` | breakdown by season |
| `bd_month` | breakdown by month |
| `bd_week` | breakdown by week |
| `bd_shop` | breakdown by shop |
| `bd_season_allshops` | season across all shops |
| `bd_month_allshops` | month across all shops |
| `bd_week_allshops` | week across all shops |
| `ca_points` | loyalty points analytics |
| `ca_pos_cnv` | POS vs CNV matching detail |
| `ca_zalo` | Zalo registration analytics |

---

## Shop Detail Data Functions
**File:** `App/analytics/tab_functions.py`

### `get_shop_detail_sales_data(shop, date_from, date_to)`
One DB call → all-time + period + by_season/month/week.
Returns:
```python
{
    'shop_name': str,
    'all_time': {total_customers, returning_customers, return_rate, returning_invoices,
                 returning_amount, total_invoices_with_vip0, total_amount_with_vip0},
    'period':   {same fields — filtered to date range},
    'by_season': [{session, label, total_customers, returning_customers, return_rate, returning_invoices}],
    'by_month':  [{month, label, ...}],
    'by_week':   [{week_label, ...}],
}
```

### `get_shop_detail_customer_data(store, start_date='', end_date='')`
Returns CNV breakdown for one store (POS vs CNV customer comparison).
- **No dates** → all-time data, returns dict with `all_time` key
- **With dates** → period + breakdown by season/month/week, returns dict with `period` key
- Returns `None` if store has no matching CNV data

**Critical:** `parse_cnv_period_filter(start_date, end_date)` returns `({}, False)` when no dates given (empty dict, NOT None).
Check with `if not period_filter:` — NOT `if period_filter is None:`.

### `get_shop_detail_coupon_data(shop, date_from, date_to)`
Returns coupon usage for one shop.
```python
{
    'shop': str,
    'all_time': {total, used, unused, usage_rate, total_coupon_amount, total_amount},
    'period':   {same},
    'details':  [coupon rows],
}
```

---

## AJAX Partial Loading Pattern (Shop Detail Page)
**URL:** `/shop-detail/` → `shop_detail.html`

Page loads, then fires 3 AJAX calls:
- `/shop-detail/?section=sales&shop=...` → `_sales_partial.html`
- `/shop-detail/?section=customer&shop=...` → `_customer_partial.html`
- `/shop-detail/?section=coupon&shop=...` → `_coupon_partial.html`

Views use `_ajax_perm_check(request, 'page_shop_detail')` (not `@requires_perm`) to avoid redirect-on-401.

---

## Coupon Analytics
**File:** `App/analytics/coupon_analytics.py`

### `calc_coupon_amount(face_value, invoice_amount)`
- `face_value > 1` → cash discount in VND (return face_value as-is)
- `0 < face_value ≤ 1` → percentage off (e.g. 0.9 = customer pays 90% → discount = 0.1 × invoice_amount)

### `calculate_coupon_analytics(date_from, date_to, coupon_id_prefix, shop_group)`
Returns: `{all_time, period, by_shop, details, duplicate_invoices}`
- Detects duplicate invoices (multiple coupons per docket_number)
- Matches with SalesTransaction.invoice_number for amounts
- Enriches with CNV customer data via phone match

### `calculate_coupon_trend_data(date_from, date_to, shop_group, coupon_id_prefix)`
Returns time-series for chart:
- `{time_labels, week_label_map, total_by_time, total_by_time_shop, shops, shop_series, campaigns, campaign_series, campaign_list}`
- Buckets: week (YYYY-Www), month (YYYY-MM), season, year

---

---

## Product Analytics (SaleDetail)
**File:** `App/analytics/product_analytics.py`  
**Model:** `App/models/pos.py` → `SaleDetail` (imported from POS system via upload)

### `get_product_tab(tab, date_from='', date_to='', shop_group='')`

| tab | returns |
|-----|---------|
| `season` | `{overview, by_season}` — rows grouped by `(year, season)` using raw POS season codes ("1","2","3","4","9") |
| `month` | `{overview, by_month}` — `TruncMonth` aggregation, label=`'YYYY-MM'` |
| `week` | `{overview, by_week}` — `TruncWeek` aggregation, label=`'Wnn YYYY'` |
| `brand` | `{overview, by_brand}` |
| `category` | `{overview, by_category}` — `category_l1` / `category_l2` hierarchy |

**`overview` keys:** `total_lines`, `total_qty`, `total_amount`, `total_settlement`, `total_tag_amount`, `disc_pct`, `date_range`

**Row keys (all tabs):** `qty`, `amount`, `settlement`, `tag_amount`, `disc_pct`, `lines` + tab-specific group keys

**`disc_pct`:** `(1 - settlement/tag_amount) * 100` — effective discount percentage. `None` if tag_amount = 0.

**Important:** `SaleDetail.season` stores raw POS codes ("1","2","3","4","9"), NOT the project's M2-4/M5-7 labels. Those labels only apply to `SalesTransaction` (computed by `season_utils.py`).

### Shop Detail: Inventory Tab
**File:** `App/analytics/inventory_functions.py`  
**Model:** `App/models/inventory.py` → `InventorySnapshot`

### `get_shop_inventory_data(shop_name)`
Returns `{}` for unknown shop. Otherwise:
```python
{
    'totals': {
        'sku_lines': int,       # Count('id')
        'on_hand_qty': int,     # Sum('inventory_qty')
        'in_transit_qty': int,  # Sum('in_transit_qty')
        'total_qty': int,       # Sum('total_qty')
        'inv_value': float,     # Sum('tag_amount')
        'total_tag_amt': float, # Sum('total_tag_amount')
    },
    'by_brand': [{'brand', 'qty', 'in_transit', 'total', 'value', 'lines'}],
    'by_season': [{'year', 'season', 'qty', 'total', 'value'}],
    'top_skus':  [{'product_code', 'product_name', 'brand', 'qty', 'total', 'value'}],  # top 20
    'dead':      {'sku_lines', 'dead_qty', 'dead_value'},  # qty=0 rows
}
```

**Django 4.2 aggregate alias rule:** Alias names in `aggregate()` must not collide with field names used as `Sum()` arguments in the same call. Use distinct aliases (`on_hand_qty` not `inventory_qty`, `inv_value` not `tag_amount`).

---

## Analytics Module Summary

| File | Purpose |
|------|---------|
| `calculations.py` | Return visit formula (LOCKED) |
| `season_utils.py` | Season labels, week info, GRADE_ORDER |
| `aggregators.py` | aggregate_by_grade/season/month |
| `core.py` | Main pipeline orchestrator |
| `customer_utils.py` | Customer cache + purchase map |
| `coupon_analytics.py` | Coupon analytics + Excel export |
| `tab_functions.py` | Per-tab data + shop detail functions (KEY) |
| `inventory_functions.py` | Shop inventory KPIs, by_brand, by_season, dead SKUs |
| `product_analytics.py` | SaleDetail product analytics for all 5 product tabs |
