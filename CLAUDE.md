# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev server (from repo root)
cd SemirDashboard && python manage.py runserver

# Migrations
cd SemirDashboard && python manage.py makemigrations
cd SemirDashboard && python manage.py migrate

# CNV loyalty sync
cd SemirDashboard && python manage.py sync_cnv_customers
cd SemirDashboard && python manage.py sync_cnv_orders

# Run all shop_detail tests
cd SemirDashboard && python manage.py test tests.test_shop_detail -v 2

# Run a single test
cd SemirDashboard && python manage.py test tests.test_shop_detail.ShopDetailTest.test_sales_alltime_matches_shop_tab -v 2

# Run all tests
cd SemirDashboard && python manage.py test tests -v 2

# Regenerate stale snapshots (after template or data shape changes)
cd SemirDashboard && UPDATE_SNAPSHOTS=1 python manage.py test tests.test_shop_detail -v 2
```

Test input files live in `SemirDashboard/tests/input/`. Snapshots live in `SemirDashboard/tests/snapshots/`. Run logs are written to `SemirDashboard/tests/output/`.

## Architecture Overview

### Django app layout

All source is under `SemirDashboard/App/`. Models, views, and analytics are split packages (not single files):

- `App/models/` — `pos.py` (Customer, SalesTransaction), `coupon.py` (Coupon, CouponCampaign), `user.py` (Role, UserProfile). All exported from `__init__.py` so `from App.models import Customer` works.
- `App/views/` — one file per page area: `analytics.py`, `coupon.py`, `customer.py`, `upload.py`, `auth.py`, `users.py`, `shop_detail.py`.
- `App/analytics/` — analytics engine (see below).
- `App/cnv/` — CNV Loyalty API integration (models, client, sync service, scheduler, views, Zalo).
- `App/services/` — file import logic (`customer_import.py`, `sales_import.py`, `coupon_import.py`).

URL routing: `SemirDashboard/urls.py` → `/admin/`, `/` → `App/urls.py`, `/cnv/` → `App/cnv/urls.py`.

### Analytics engine (`App/analytics/`)

The main analytics request flow:
1. A view calls `get_sales_tab(tab_name, date_from, date_to, shop_group)` from `tab_functions.py`
2. `tab_functions.py` calls `_load_sales()` which fetches raw transactions, builds `customer_purchases` dict, and caches it 5 min per (date_from, date_to, shop_group)
3. The appropriate aggregator (`aggregate_by_season`, `aggregate_by_shop`, etc.) in `aggregators.py` computes the breakdown
4. `core.py` orchestrates `calculate_return_rate_analytics()` for full-page exports

The **Shop Detail page** (`views/shop_detail.py`) uses direct-query helpers in `tab_functions.py`:
- `get_shop_detail_sales_data(shop, date_from, date_to)` — loads all-time for the shop in 1 DB query, filters to period in Python, returns `{all_time: KPIs, period: KPIs, by_session, by_month, by_week}`
- `get_shop_detail_customer_data(store, start_date, end_date)` — uses `compute_cnv_breakdown` with `store_filter`
- `get_shop_detail_coupon_data(shop, date_from, date_to)` — direct DB filter

Shop Detail partials are loaded via AJAX (`/shop-detail/partial/sales/`, `/customer/`, `/coupon/`) with `X-Requested-With: XMLHttpRequest`. Templates live in `App/templates/shop_detail/_*_partial.html`.

Dropdown lists for Shop Detail are cached 5 min in Django cache under key `"shop_detail_dropdowns"`. The `_get_dropdown_options()` helper uses `.order_by().distinct()` — **never omit `.order_by()`** before `.distinct()` on models that have `Meta.ordering`, or Django will include ordering fields in the SELECT DISTINCT and return every row as unique.

### CNV integration (`App/cnv/`)

CNV Loyalty is an external loyalty platform. Customers are matched POS↔CNV by phone number. `compute_cnv_breakdown()` in `App/cnv/service.py` is the main analytics function. `_fetch_bd_raw(period_filter)` fetches all raw DB data (cached 5 min); `period_filter` must be a dict (`{}` for no filter) — **never pass `None`**, the `.get()` call will crash.

### Permissions

Custom role-based system in `App/permissions.py`. Views use `@requires_perm("permission_string")`. For AJAX partial views that must not redirect on auth failure, use `_ajax_perm_check(request, codename)` which returns a 401/403 `HttpResponse` instead of redirecting (redirect silently followed by `fetch()` would return the wrong page's HTML).

### Template tags

`perm_tags.py` provides `{% check_perm 'codename' as var %}`. `custom_filters.py` provides `|vnd` (VND number format).

## Critical Business Rules

**Return visit formula** (`App/analytics/calculations.py`) — **locked, do not change without user approval:**
```python
if registration_date == first_purchase_date:
    return_visits = total_invoices - 1   # reg-day purchase is NOT a return
else:
    return_visits = total_invoices       # all invoices count as returns
```
Counts invoices, not unique visit days.

**Season definitions** (4 seasons, updated Mar 2026 — old SS/AW definition is obsolete):
| Label | Months |
|-------|--------|
| M2-4  | Feb, Mar, Apr |
| M5-7  | May, Jun, Jul |
| M8-10 | Aug, Sep, Oct |
| M11-1 | Nov, Dec, Jan (cross-year) |

M11-1 label format: `M11-1 2024-2025` (not `2025/2026`). Jan belongs to the *next* year.

**Grade hierarchy:** `No Grade < Member < Silver < Gold < Diamond` — **not** VIP0/VIP1/VIP2/VIP3/DIAMOND (obsolete).

**VIP ID = "0"** → non-VIP customer, excluded from grade analytics. Tracked separately as "buyer without info".

**Coupon campaign prefix** — `CouponCampaign.prefix` is comma-separated. A coupon belongs to a campaign if its `coupon_id` starts with any prefix in the list.

## Test Infrastructure

Tests extend `SnapshotTestCase` from `tests/base.py`. Key features:
- `self.assert_snapshot(name, data)` — compares against JSON in `tests/snapshots/<name>.json`; set `UPDATE_SNAPSHOTS=1` to regenerate
- `self.timer(name)` → `Timer` — records checkpoint timings, writes to run log
- `self.record_page_timing(page, total_s, checkpoints)` — records in summary

All tests that load fixture data (74k customers + 118k sales + 239k coupons) should use `setUpTestData` at the class level to load once per class. Merge test classes that share the same fixture set to avoid duplicate loads.

## Database Notes

Dev: SQLite3 (`SemirDashboard/db.sqlite3`). Prod: PostgreSQL 16.

`Meta.ordering` on `SalesTransaction` and `Customer` models affects `.distinct()` queries — always call `.order_by()` before `.distinct()` to clear model ordering. Indexes exist on `shop_name`, `registration_store`, `using_shop` (migration 0012).

## Detailed Docs

Extended documentation is in `docs/`:
- `ANALYSIS.md` — navigation index + architecture summary
- `project_overview.md` — stack, paths, deploy, commands
- `project_structure.md` — file tree + task→file mapping
- `project_models.md` — all model fields (accurate)
- `project_analytics.md` — analytics engine, season labels, grades, tab_functions.py
- `project_cnv.md` — CNV API, sync service, service.py, scheduler, Zalo
- `project_urls.md` — complete URL map (all 30+ endpoints)
- `project_business_logic.md` — all 20 permissions, business rules, upload flow
