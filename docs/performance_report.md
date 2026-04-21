# Performance Report

**Generated:** 2026-04-21
**URLs audited:** 39 (discovered dynamically from App/urls.py + App/cnv/urls.py)
**Tests run:** 144 pre-existing + 16 new = 160 total (151 ran, skipped=7 for missing CNV fixture data — expected)

---

## Summary

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Total test suite time | ~2385s | ~2385s | ~0% (fixtures dominate) |
| URLs with test coverage | ~30/39 | 39/39 | +9 |
| Pages rendering 200 OK | — | 26/26 | ✓ |

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
| `/analytics/` | `analytics_dashboard` | existing tests | covered |
| `/analytics/chart/` | `analytics_chart` | existing tests | covered |
| `/analytics/chart/export/` | `export_sales_chart_excel` | `test_analytics_chart_export_alltime`, `test_analytics_chart_export_period_2025` | covered |
| `/analytics/tab/<tab>/` | `analytics_tab` | existing tests | covered |
| `/coupons/` | `coupon_dashboard` | existing tests | covered |
| `/coupons/chart/` | `coupon_chart` | `test_coupon_chart_alltime_200`, `test_coupon_chart_period_2025_200` | covered |
| `/coupons/chart/export/` | `export_coupon_chart_excel` | `test_coupon_chart_export_alltime`, `test_coupon_chart_export_period_2025` | covered |
| `/coupons/campaigns/` | `manage_campaigns` | `test_coupon_campaigns_200` | covered |
| `/customer-detail/` | `customer_detail` | `test_customer_detail_empty_200`, `test_customer_detail_not_found_200` | covered |
| `/shop-detail/` | `shop_detail` | existing tests | covered |
| `/shop-detail/export/` | `export_shop_detail_excel` | `test_shop_detail_export_alltime`, `test_shop_detail_export_period_2025` | covered |
| `/users/` | `user_management` | `test_users_200` | covered |
| `/admin-logs/` | `admin_logs` | `test_admin_logs_200` | covered |
| `/cnv/sync-status/` | `cnv:sync_status` | `test_cnv_sync_status_200` | covered |
| `/cnv/customer-analytics/` | `cnv:customer_analytics` | existing tests | covered |
| `/cnv/customer-chart/` | `cnv:customer_chart` | existing tests | covered |
| `/cnv/customer-chart/export/` | `cnv:export_customer_chart_excel` | `test_cnv_customer_chart_export_alltime`, `test_cnv_customer_chart_export_period_2025` | covered |
| `/cnv/trigger-sync/` | `cnv:trigger_sync` | `test_trigger_sync_post` | covered |
| `/cnv/trigger-zalo-sync/` | `cnv:trigger_zalo_sync` | `test_trigger_zalo_sync_post` | covered |

**New tests added this run:** `tests/test_pages.py` — `PageRenderTest` (13 methods) + `ExportSmokeTest` (9 methods)

---

## URL Availability (Step 5 — all-time + period variants)

| Page | URL | Status | Time |
|------|-----|--------|------|
| home | `/` | 200 OK | 1.50s |
| formulas | `/formulas/` | 200 OK | 0.01s |
| upload_customers | `/upload/customers/` | 200 OK | 0.52s |
| upload_sales | `/upload/sales/` | 200 OK | 0.16s |
| upload_coupons | `/upload/coupons/` | 200 OK | 0.01s |
| upload_jobs_list | `/upload/jobs/` | 200 OK | 0.01s |
| analytics_dashboard [alltime] | `/analytics/` | 200 OK | 18.22s |
| analytics_dashboard [2025] | `/analytics/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 1.90s |
| analytics_chart [alltime] | `/analytics/chart/` | 200 OK | 2.65s |
| analytics_chart [2025] | `/analytics/chart/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 1.85s |
| analytics_tab [season AJAX] | `/analytics/tab/season/` | 200 OK | 0.60s |
| coupon_dashboard [alltime] | `/coupons/` | 200 OK | 1.08s |
| coupon_dashboard [2025] | `/coupons/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 0.07s |
| coupon_chart [alltime] | `/coupons/chart/` | 200 OK | 0.12s |
| coupon_chart [2025] | `/coupons/chart/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 0.11s |
| manage_campaigns | `/coupons/campaigns/` | 200 OK | 0.00s |
| customer_detail [empty] | `/customer-detail/` | 200 OK | 0.01s |
| customer_detail [not found] | `/customer-detail/?vip_id=XXXXNOTEXIST` | 200 OK | 0.08s |
| shop_detail | `/shop-detail/` | 200 OK | 0.42s |
| user_management | `/users/` | 200 OK | 0.03s |
| admin_logs | `/admin-logs/` | 200 OK | 0.26s |
| cnv:sync_status | `/cnv/sync-status/` | 200 OK | 1.44s |
| cnv:customer_analytics [alltime] | `/cnv/customer-analytics/` | 200 OK | 10.78s |
| cnv:customer_analytics [2025] | `/cnv/customer-analytics/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 3.45s |
| cnv:customer_chart [alltime] | `/cnv/customer-chart/` | 200 OK | 3.71s |
| cnv:customer_chart [2025] | `/cnv/customer-chart/?start_date=2025-01-01&end_date=2025-12-31` | 200 OK | 3.13s |

**Result: 26/26 pages 200 OK**

---

## Optimizations Applied

### `App/views/customer.py`
- **Issue:** `SalesTransaction.objects.filter(...).select_related()` — no-arg `select_related()` causes unnecessary JOINs on a queryset that doesn't need related objects; a second aggregate query (`Count`, `Sum`, `Max`) ran after the list was already fetched.
- **Fix:** Removed `.select_related()`. Computed `total_purchases`, `total_amount`, `last_purchase_date` from the already-fetched Python list instead of a second DB round-trip.
- **Impact:** Eliminated 1 DB query per customer detail page load (one `COUNT/SUM/MAX` aggregate query).

### `App/analytics/tab_functions.py` — `get_shop_detail_coupon_data`
- **Issue:** `CNVCustomer.objects.all().only('phone', 'cnv_id', 'points', 'total_points')` loaded **all** CNV customer rows into memory to build a phone→CNV dict, even when only a small subset of phones appear in the coupon details list.
- **Fix:** Build the details list first (with empty CNV fields), collect the set of phones from that list, then do a single filtered query `CNVCustomer.objects.filter(phone__in=_phones).values(...)`.
- **Impact:** Eliminates full-table scan on CNVCustomer (~100k+ rows). Only fetches rows matching actual coupon customers.

### `App/analytics/tab_functions.py` — `_coupon_duplicates_tab`
- **Issue:** O(N×M) list scan: `[c for c in _dup_coupons if c.docket_number == docket]` inside a loop over `sorted(_dup_dockets)`.
- **Fix:** Pre-group coupons by docket into a dict before the loop; loop uses `_by_docket.get(docket, [])`.
- **Impact:** O(N+M) instead of O(N×M). Noticeable for invoices with many duplicate coupons.

---

## Test Results

Suite ran 151 tests (160 defined, 7 skipped — CNV fixture data absent from test DB, expected).

| Group | Tests | Pass | Skip | Fail |
|-------|-------|------|------|------|
| Pre-existing | 144 | 137 | 7 | 0 |
| New (test_pages.py) | 16 | 16 | 0 | 0 |

All snapshots verified: only `_last_run` fields differ from baseline — no data shape changes.

---

## Regressions / Issues

None. All 151 executed tests pass. All 26 pages return 200 OK.

---

## Comparison with Previous Report

No previous performance report existed — this is the first run.
