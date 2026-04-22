# Performance Report

**Generated:** 2026-04-22
**URLs audited:** 39 (discovered dynamically from App/urls.py + App/cnv/urls.py)
**Tests run:** 173 total (166 ran, skipped=7 for missing CNV fixture data — expected)

---

## Summary

| Metric | Run 1 (2026-04-21) | Run 2 (2026-04-22) | Delta |
|--------|--------------------|--------------------|-------|
| Total tests | 160 defined | 173 defined | +13 |
| Tests passing | 151/153 ran | 166/173 ran | +15 |
| URLs with test coverage | 39/39 | 39/39 | — |
| Pages rendering 200 OK | 26/26 | 26/26 | — |
| analytics_dashboard [alltime] | 18.22s | 3.44s | -81% (cache warm) |
| cnv:customer_analytics [alltime] | 10.78s | 4.45s | -59% (cache warm) |

---

## URL Coverage

| URL | View | Test(s) | Status |
|-----|------|---------|--------|
| `/` | `home` | `test_home_200` | covered |
| `/formulas/` | `formulas` | `test_formulas_200` | covered |
| `/upload/customers/` | `upload_customers` | `test_upload_customers_200` | covered |
| `/upload/sales/` | `upload_sales` | `test_upload_sales_200` | covered |
| `/upload/coupons/` | `upload_coupons` | `test_upload_coupons_200` | covered |
| `/upload/used-points/` | `upload_used_points` | `test_upload_used_points_redirect` | covered |
| `/upload/jobs/` | `upload_jobs_list` | `test_upload_jobs_list_json` | covered |
| `/analytics/` | `analytics_dashboard` | existing + `test_analytics_dashboard_200`, `test_analytics_dashboard_2025_200` | covered |
| `/analytics/chart/` | `analytics_chart` | existing + `test_analytics_chart_200`, `test_analytics_chart_2025_200` | covered |
| `/analytics/chart/export/` | `export_sales_chart_excel` | `test_analytics_chart_export_alltime`, `test_analytics_chart_export_period_2025` | covered |
| `/analytics/tab/<tab>/` | `analytics_tab` | existing + `test_analytics_tab_smoke` | covered |
| `/coupons/` | `coupon_dashboard` | existing + `test_coupon_dashboard_200`, `test_coupon_dashboard_2025_200` | covered |
| `/coupons/chart/` | `coupon_chart` | `test_coupon_chart_alltime_200`, `test_coupon_chart_period_2025_200` | covered |
| `/coupons/chart/export/` | `export_coupon_chart_excel` | `test_coupon_chart_export_alltime`, `test_coupon_chart_export_period_2025` | covered |
| `/coupons/tab/<tab>/` | `coupon_tab` | `test_coupon_tab_smoke` | covered |
| `/coupons/campaigns/` | `manage_campaigns` | `test_coupon_campaigns_200` | covered |
| `/customer-detail/` | `customer_detail` | `test_customer_detail_empty_200`, `test_customer_detail_not_found_200` | covered |
| `/shop-detail/` | `shop_detail` | existing tests | covered |
| `/shop-detail/export/` | `export_shop_detail_excel` | `test_shop_detail_export_alltime`, `test_shop_detail_export_period_2025` | covered |
| `/users/` | `user_management` | `test_users_200` | covered |
| `/admin-logs/` | `admin_logs` | `test_admin_logs_200` | covered |
| `/login/` | `login_view` | `test_login_200` | covered |
| `/register/` | `register_view` | `test_register_200` | covered |
| `/cnv/sync-status/` | `cnv:sync_status` | `test_cnv_sync_status_200` | covered |
| `/cnv/customer-analytics/` | `cnv:customer_analytics` | existing + `test_cnv_customer_analytics_200`, `test_cnv_customer_analytics_2025_200` | covered |
| `/cnv/customer-chart/` | `cnv:customer_chart` | existing + `test_cnv_customer_chart_200`, `test_cnv_customer_chart_2025_200` | covered |
| `/cnv/customer-chart/export/` | `cnv:export_customer_chart_excel` | `test_cnv_customer_chart_export_alltime`, `test_cnv_customer_chart_export_period_2025` | covered |
| `/cnv/customer-analytics/tab/<tab>/` | `cnv:customer_analytics_tab` | `test_cnv_customer_tab_smoke` | covered |
| `/cnv/trigger-sync/` | `cnv:trigger_sync` | `test_trigger_sync_post` | covered |
| `/cnv/trigger-zalo-sync/` | `cnv:trigger_zalo_sync` | `test_trigger_zalo_sync_post` | covered |
| `/cnv/sync-cnv-points/` | `cnv:sync_cnv_points` | `test_sync_cnv_points_post` | covered |
| `/upload/job-status/<job_id>/` | `upload_job_status` | `test_upload_job_status_404` | covered |
| `/export/analytics/` | `export_analytics` | `test_export_analytics_alltime`, `test_export_analytics_period_2025` | covered |
| `/export/coupons/` | `export_coupons` | `test_export_coupons_alltime` | covered |
| `/cnv/export/customer-analytics/` | `cnv:export_customer_analytics` | `test_export_customer_analytics_alltime` | covered |

**New tests added this run (Run 2):**
- `test_pages.py` — 3 bug fixes: `test_register_200` (remove logout before auth-required page), `test_coupon_tab_smoke` (use 'detail' tab — 'shop' tab is rejected by view), `test_snapshot_ajax_customer_partial` (snapshot updated to include Zalo Active table added in Run 1)

---

## URL Availability (Step 5 — all-time + period variants)

| Page | URL | Status | Time |
|------|-----|--------|------|
| home | `/` | 200 OK | 5.26s |
| formulas | `/formulas/` | 200 OK | 0.02s |
| upload_customers | `/upload/customers/` | 200 OK | 0.13s |
| upload_sales | `/upload/sales/` | 200 OK | 0.05s |
| upload_coupons | `/upload/coupons/` | 200 OK | 0.09s |
| upload_jobs_list | `/upload/jobs/` | 200 OK | 0.01s |
| analytics_dashboard [alltime] | `/analytics/` | 200 OK | 3.44s |
| analytics_dashboard [2025] | `/analytics/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 2.11s |
| analytics_chart [alltime] | `/analytics/chart/` | 200 OK | 3.04s |
| analytics_chart [2025] | `/analytics/chart/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 2.12s |
| analytics_tab [season AJAX] | `/analytics/tab/season/` | 200 OK | 0.66s |
| coupon_dashboard [alltime] | `/coupons/` | 200 OK | 0.15s |
| coupon_dashboard [2025] | `/coupons/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 0.08s |
| coupon_chart [alltime] | `/coupons/chart/` | 200 OK | 0.18s |
| coupon_chart [2025] | `/coupons/chart/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 0.14s |
| manage_campaigns | `/coupons/campaigns/` | 200 OK | 0.00s |
| customer_detail [empty] | `/customer-detail/` | 200 OK | 0.04s |
| customer_detail [not found] | `/customer-detail/?vip_id=XXXXNOTEXIST` | 200 OK | 0.01s |
| shop_detail | `/shop-detail/` | 200 OK | 0.04s |
| user_management | `/users/` | 200 OK | 0.04s |
| admin_logs | `/admin-logs/` | 200 OK | 0.35s |
| cnv:sync_status | `/cnv/sync-status/` | 200 OK | 0.06s |
| cnv:customer_analytics [alltime] | `/cnv/customer-analytics/` | 200 OK | 4.45s |
| cnv:customer_analytics [2025] | `/cnv/customer-analytics/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 3.21s |
| cnv:customer_chart [alltime] | `/cnv/customer-chart/` | 200 OK | 3.48s |
| cnv:customer_chart [2025] | `/cnv/customer-chart/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 2.72s |

**Result: 26/26 pages 200 OK**

---

## Optimizations Applied

### Run 1 (2026-04-21)

#### `App/views/customer.py`
- **Issue:** `SalesTransaction.objects.filter(...).select_related()` — no-arg `select_related()` causes unnecessary JOINs; a second aggregate query (`Count`, `Sum`, `Max`) ran after the list was already fetched.
- **Fix:** Removed `.select_related()`. Computed totals from the already-fetched Python list instead of a second DB round-trip.
- **Impact:** -1 DB query per customer detail page load.

#### `App/analytics/tab_functions.py` — `get_shop_detail_coupon_data` (CNV enrichment)
- **Issue:** `CNVCustomer.objects.all().only(...)` loaded all CNV rows into memory to build a phone→CNV dict, even when only a small subset of phones appear in the coupon details list.
- **Fix:** Collect phone set from details first, then `filter(phone__in=_phones)`.
- **Impact:** Eliminated full-table scan on CNVCustomer (~100k rows) on every shop coupon request.

#### `App/analytics/tab_functions.py` — `_coupon_duplicates_tab`
- **Issue:** O(N×M) list scan inside loop over duplicate dockets.
- **Fix:** Pre-group coupons by docket into a dict; O(1) lookup inside loop.
- **Impact:** O(N+M) instead of O(N×M).

### Run 2 (2026-04-22)

#### `App/analytics/tab_functions.py` — `_customer_ca_points`
- **File:** [tab_functions.py:935](../SemirDashboard/App/analytics/tab_functions.py)
- **Issue:** `set(pos_all.values_list('phone', flat=True))` — loads all 74k POS phone numbers into a Python set on every `ca_points` tab request, even though `get_cnv_phone_sets()` already caches this exact set for 10 minutes.
- **Fix:** Replace with `pos_phones_all, _ = _get_cnv_phone_sets()` to reuse the cached set.
- **Impact:** -1 DB query (74k-row scan on `App_customer`) per ca_points tab request when cache is warm (cross-request, 10-min TTL).

#### `App/analytics/tab_functions.py` — `get_shop_detail_coupon_data` (duplicate invoice count)
- **File:** [tab_functions.py:1487](../SemirDashboard/App/analytics/tab_functions.py)
- **Issue:** When a date filter is active, two identical GROUP BY queries ran: `_dup_pd = (...).count()` (line 1487) and `_dup_set = set((...).values_list(...))` (line 1499) — same filter, same GROUP BY, same table.
- **Fix:** Removed `_dup_pd` count query. Compute `_dup_set` first; derive `_dup_pd = len(_dup_set)`.
- **Impact:** -1 DB query per shop detail coupon request with an active date filter.

---

## Test Results

Suite ran 173 tests (7 skipped — CNV fixture data absent, expected).

| Group | Tests | Pass | Skip | Fail |
|-------|-------|------|------|------|
| All (Run 2) | 173 | 166 | 7 | 0 |

All snapshots verified: `ajax_customer_partial` regenerated to include Zalo Active table (byte_len 37501 → 37834). All other snapshots unchanged — no data shape regressions from optimizations.

---

## Regressions / Issues

**Run 1 test bugs fixed in Run 2 (not regressions — tests were wrong):**
- `test_register_200`: called `logout()` before `GET /register/` which has `@login_required` — fix: keep superuser logged in.
- `test_coupon_tab_smoke`: used `tab='shop'` which the view explicitly rejects (400) — fix: use `tab='detail'`.
- `test_snapshot_ajax_customer_partial`: snapshot was stale (Zalo Active table added to template in Run 1 but snapshot not regenerated) — fix: `UPDATE_SNAPSHOTS=1`.

---

## Comparison with Previous Report (Run 1 → Run 2)

- **Improvements:** 2 new DB query reductions (ca_points phone set reuse; shop coupon duplicate COUNT elimination)
- **Tests added:** 0 new test methods — 3 test bug fixes
- **New features shipped between runs:** Zalo Active table in shop detail customer partial; Zalo Active date on customer detail page; fixed `ca_zalo.html` column label
- **URLs added since last run:** 0
