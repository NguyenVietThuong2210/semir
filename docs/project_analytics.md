---
name: SemirDashboard Analytics Engine
description: Analytics engine details, return visit formula, season logic, Excel export structure
type: project
---

## Entry Point
`App/analytics/core.py` → `calculate_return_rate_analytics(date_from, date_to, shop_group)`

Returns dict with all breakdowns:
- Period-level metrics
- By VIP Grade
- By Season
- By Month / Year / Week
- By Shop (with nested breakdowns)
- Customer details list
- Buyer without info (VIP ID = 0)

---

## CRITICAL: Return Visit Formula (LOCKED — user-confirmed)
**File:** `App/analytics/calculations.py`

```python
if registration_date == first_purchase_date:
    return_visits = total_invoices - 1  # First invoice on reg day is not a return
else:
    return_visits = total_invoices      # All invoices count as returns

is_returning = (return_visits > 0)
return_rate = returning_customers / total_customers * 100
```

**Key rule:** Counts INVOICES, not unique days. This is intentional and confirmed by the user.

---

## Season Definitions (NEW — 4 seasons, updated Mar 2026)
**File:** `App/analytics/season_utils.py`

| Season | Months | Notes |
|--------|--------|-------|
| M2-4 | Feb, Mar, Apr | Spring |
| M5-7 | May, Jun, Jul | Summer |
| M8-10 | Aug, Sep, Oct | Fall |
| M11-1 | Nov, Dec, Jan | Winter (cross-year) |

**Old definition (OBSOLETE):** SS = Jan-Jun, AW = Jul-Dec

Season label format: `"M2-4 2025"`, `"M11-1 2025/2026"`

---

## Shop Group Logic
**File:** `App/analytics/aggregators.py`

- Shop ID: "HN01", "HN02", "SG01", "SG02"
- Shop Group: first 2 chars of shop_id → "HN", "SG"
- Custom groups: "Bala Group", "Semir Group", "Others Group"
- Filter via `shop_group` param in `calculate_return_rate_analytics()`

---

## VIP Grade Hierarchy
```
VIP0 (lowest) → VIP1 → VIP2 → VIP3 → DIAMOND (highest)
```
- VIP ID = "0" → non-VIP → excluded from grade analytics, tracked separately as "buyer without info"

---

## Analytics Modules
| File | Size | Purpose |
|------|------|---------|
| core.py | — | Main orchestrator |
| aggregators.py | ~40KB | group by grade/season/month/year/week/shop |
| calculations.py | — | Pure math (return rate formula) |
| season_utils.py | — | Season detection + sort keys |
| customer_utils.py | — | Customer cache + purchase map builder |
| coupon_analytics.py | ~37KB | Coupon-specific analytics (usage, face value) |
| excel_export.py | ~85KB | Excel export (13+ sheets) |

---

## Excel Export Structure
**`export_analytics_to_excel(data, date_from, date_to, shop_group)`**

Sheets:
1. Overview (filter info)
2. By VIP Grade
3. By Season
4. By Month
5. By Week
6. By Shop
7. By Shop Detail
8. Grade Comparison
9. Season Comparison
10. Month Comparison
11. Week Comparison
12. Customer Details
13. Buyer Without Info
14. Reconciliation

**`export_coupons_to_excel(data, date_from, date_to, shop_group)`** — parallel coupon structure

**`export_customer_comparison_to_excel(pos_all, pos_period, cnv_all, cnv_period)`**
- POS vs CNV comparison tables
- CNV columns: Customer ID, Phone, Name, Level, Email, Reg Date, Points, Used Points

**Formatting:** Blue headers (`#366092`), formatted numbers, auto-column width

---

## Coupon Analytics
**`App/analytics/coupon_analytics.py`**
- `calculate_coupon_analytics(date_from, date_to, shop_group)`
- Metrics: issued count, used count, usage_rate, face_value totals
- Same breakdowns as customer analytics (grade, season, shop, month, week)
