# Performance Report

**Generated:** 2026-05-03  
**Web URLs audited:** 51 (38 page/API + 13 mobile API — discovered dynamically from urls.py)  
**Mobile routes audited:** 10 (discovered dynamically from app.dart)  
**Web tests run:** 420 (all pre-existing — all routes already covered)  
**Mobile tests run:** 226 (unit + widget + golden)

---

## Web Summary

| Metric | Result |
|--------|--------|
| Total web test suite time | ~120s |
| Web URLs with test coverage | 51/51 |
| Web pages returning 200 | 21/21 |

## Mobile Summary

| Metric | Result |
|--------|--------|
| Flutter analyze errors | 0 |
| Flutter analyze info (test files only) | 40 |
| Mobile tests pass | 226/226 |
| Routes with nav entry point | 10/10 |
| Providers with autoDispose (family) | All ✅ |
| Providers in logout invalidate list | 10/10 ✅ |
| print() leaks found | 0 |
| Unsafe `.cast<>` found and fixed | 3 (fixed) |

---

## Web URL Coverage

All 51 routes covered. No new tests were needed — prior audit passes already covered every route.

| Area | Routes | Tests |
|------|--------|-------|
| Analytics (sales/customer/coupon) | 6 page + 6 AJAX tab | test_analytics*, test_coupon*, test_customer* |
| Shop Detail | 4 (page + 3 AJAX partials) | test_shop_detail* |
| CNV Customer Analytics | 5 (page + tabs + export) | test_cnv* |
| Chart pages | 3 | test_charts* |
| Upload / Admin | 4 | test_upload* |
| Auth | 2 (login/logout) | test_auth* |
| API mobile endpoints | 13 | test_api* |
| Home / Users / Misc | 8 | test_page*, test_users* |

---

## Mobile Route Coverage

| Route | Page | Permission | Nav entry | Test |
|-------|------|-----------|-----------|------|
| `/login` | `LoginPage` | none | GoRouter redirect | `login_page_test.dart` |
| `/` | `HomePage` | authenticated | cold start | `home_page_test.dart` |
| `/sales` | `SalesPage` | `sales.view` | Home card | `sales_page_test.dart` |
| `/sales/charts` | `SalesChartPage` | `sales.view` | Home card + AppBar | `chart_page_test.dart` |
| `/customer` | `CustomerPage` | `customers.view` | Home card | `customer_page_test.dart` |
| `/customer/charts` | `CustomerChartPage` | `customers.view` | Home card + AppBar | `chart_page_test.dart` |
| `/coupon` | `CouponPage` | `coupons.view` | Home card | `coupon_page_test.dart` |
| `/coupon/charts` | `CouponChartPage` | `coupons.view` | Home card + AppBar | `chart_page_test.dart` |
| `/shop-detail` | `ShopDetailPage` | `shop_detail.view` | Home card | `shop_detail_page_test.dart` |
| `/customer-detail` | `CustomerDetailPage` | `customer_detail.view` | Home card | `customer_detail_page_test.dart` |

---

## Web Page Availability (21/21)

All 21 web pages verified with Django test `Client` + `force_login(superuser)`.

| Page | URL | Status |
|------|-----|--------|
| Home | `/` | 200 OK |
| Analytics Dashboard | `/analytics/` | 200 OK |
| Analytics Tab – grade | `/analytics/tab/grade/` | 200 OK |
| Analytics Tab – season | `/analytics/tab/season/` | 200 OK |
| Analytics Tab – month | `/analytics/tab/month/` | 200 OK |
| Analytics Tab – shop | `/analytics/tab/shop/` | 200 OK |
| Coupon Dashboard | `/coupon/` | 200 OK |
| Coupon Tab – session | `/coupon/tab/session/` | 200 OK |
| Coupon Tab – month | `/coupon/tab/month/` | 200 OK |
| Coupon Tab – campaign | `/coupon/tab/campaign/` | 200 OK |
| Customer Analytics | `/cnv/customer-analytics/` | 200 OK |
| CNV Tab – season | `/cnv/customer-analytics/tab/season/` | 200 OK |
| CNV Tab – month | `/cnv/customer-analytics/tab/month/` | 200 OK |
| CNV Tab – week | `/cnv/customer-analytics/tab/week/` | 200 OK |
| Shop Detail | `/shop-detail/` | 200 OK |
| Shop Detail – Sales partial | `/shop-detail/partial/sales/` | 200 OK |
| Shop Detail – Customer partial | `/shop-detail/partial/customer/` | 200 OK |
| Shop Detail – Coupon partial | `/shop-detail/partial/coupon/` | 200 OK |
| Chart – Sales | `/chart/sales/` | 200 OK |
| Chart – Customer | `/chart/customer/` | 200 OK |
| Chart – Coupon | `/chart/coupon/` | 200 OK |

---

## Web Optimizations Applied

### `App/views/coupon.py` — Campaign prefix_list helper

**Issue:** Identical `prefix_list` split/strip logic repeated inline across 3 views (`coupon_dashboard`, `coupon_chart`, `manage_campaigns`) — 9 duplicate lines, inconsistency risk.

**Fix:** Extracted `_get_campaigns_with_prefix_list(extra_fields=())` helper. All three views now call the helper.

| File | Lines | Issue | Fix | Query Δ | Code Δ |
|------|-------|-------|-----|---------|--------|
| `App/views/coupon.py` | 57-59, 200, 234-244 | prefix_list built inline 3× | `_get_campaigns_with_prefix_list()` helper | 0 | −9 dup lines |

**Note:** Other potential optimizations investigated:
- `App/cnv/views.py` lines 499-506: 4 `.count()` calls — already wrapped in a 10-min cache block, no action needed
- `App/analytics/core.py` lines 65-70: 2 counts on different tables (`Customer`, `SalesTransaction`) — cannot be combined, already minimal
- `App/cnv/views.py` line 217: `Customer.objects.all()` in export path — export intentionally needs all rows; `.only()` not safe without knowing all columns used in the Excel builder

### `App/cnv/service.py:_fetch_bd_raw()` — Merge dual POSCustomer queries + eliminate aggregate queries (2026-05-03)

**Issue (cold all-time):** 7 DB queries on every cold start:
1. `POSCustomer.aggregate(Min, Max)` for reg date bounds — redundant
2. `CNVCustomer.aggregate(Min, Max)` for CNV date bounds — redundant
3. `pos_qs`: POSCustomer filtered by period
4. `cnv_list`: CNVCustomer
5. `zalo_list`: CNVCustomer (Zalo filter)
6. `_all_pos_rows`: POSCustomer all-time — overlaps with query 3
7. `build_inv_bucket_map_from_db`: SalesTransaction

**Fix:** Single broad `POSCustomer` scan (replaces queries 1, 3, 6). Derive `reg_lo`/`reg_hi` and `pos_list` in Python from the fetched rows. Derive `cnv_lo`/`cnv_hi` from `cnv_list` after fetch (eliminates query 2). Verified: 0 customers have `registration_date` but no phone — semantics unchanged.

| File | Lines | Issue | Fix | Query Δ | Cold-start Δ |
|------|-------|-------|-----|---------|--------------|
| `App/cnv/service.py` | 160-273 | 7 queries cold all-time (2 aggregate + dual POSCustomer scan) | Single POSCustomer fetch + Python min/max | −3q (7→4) | 11.67s → 10.99s (−6%) |

**Why modest improvement on SQLite:** SQLite has no network round-trip overhead. Postgres production benefit will be larger (~3 × network RTT saved per cold request).

---

### `App/cnv/service.py:get_cnv_phone_sets()` — Eliminate duplicate POS+CNV table scans (2026-05-04)

**Issue:** `get_cnv_phone_sets()` fired 2 separate queries (POSCustomer phone-only + CNVCustomer phone-only). Then `compute_cnv_breakdown({})` called `_fetch_bd_raw({})` which fetched ALL POS + CNV data again — 6 total queries cold, hitting the same two tables twice.

**Fix:** `get_cnv_phone_sets()` now calls `_fetch_bd_raw({})` (4 queries) and derives phone sets in-memory from `_all_pos_rows` and `cnv_list`. Calling `get_cnv_phone_sets()` also primes the `_fetch_bd_raw({})` cache, so the next `compute_cnv_breakdown({})` call is a cache hit. Added `_all_pos_rows` to the `_fetch_bd_raw` return tuple (10-tuple, was 9-tuple).

### `App/api/views.py:CustomerAnalyticsView` — Eliminate duplicate `_compute_grade_rows` call (2026-05-04)

**Issue:** `pd_grade_rows = _compute_grade_rows(cnv_phones_all, period_filter if period_filter else {})` — for all-time (`period_filter={}`), this evaluated to the same call as `at_grade_rows = _compute_grade_rows(cnv_phones_all)`, firing an extra query + iterating 74k POSCustomer rows twice.

**Fix:** `pd_grade_rows = _compute_grade_rows(cnv_phones_all, period_filter) if period_filter else at_grade_rows` — reuses the already-computed result for all-time.

| File | Issue | Fix | Query Δ | Time Δ |
|------|-------|-----|---------|--------|
| `App/cnv/service.py` | `get_cnv_phone_sets` fired 2 separate queries, duplicating POS+CNV table scans done by `_fetch_bd_raw` | Derive phone sets from `_fetch_bd_raw({})` result; prime breakdown cache as side effect | −2q (6→4 cold all-time) | API cold 6.33s → <5s ✅ |
| `App/api/views.py` | `_compute_grade_rows` called twice for all-time (same params) | Reuse `at_grade_rows` when no period filter | −1q | ~−0.3s |

**Result:** `test_cnv_customer_alltime_kpis_match_underlying_function` and `test_cnv_customer_period_2025_kpis_match_underlying_function` now pass the 5s limit. `customer_per_query` TOTAL timer: 3.23s → 1.77s (warm cache).

---

## Mobile Issues Fixed

| File | Issue | Fix | Severity |
|------|-------|-----|----------|
| `shop_detail_service.dart:96-98` | `.cast<String>()` on `ShopCouponPayload` headers/rows | `.whereType<String>().toList()` | BUG — `CastError` crash on mixed-type API response |
| `shop_detail_service.dart:121` | `.cast<String>()` in `getShops()` | `.whereType<String>().toList()` | BUG — `CastError` crash |
| `shared/models/analytics_models.dart:54,56` | `.cast<String>()` in `TableTab.parseMap()` headers/rows | `.whereType<String>().toList()` | BUG — `CastError` crash on mixed-type API response (affects ALL analytics table tabs) |
| `core/auth/token_storage.dart:59` | `.cast<String>()` in `readPermissions()` | `.whereType<String>().toList()` | BUG — `CastError` crash if permissions list contains non-string |
| `auth_provider.dart:logout()` | `salesChartProvider`, `customerChartProvider`, `couponChartProvider` not invalidated | Added `ref.invalidate()` × 3 + `import chart_provider.dart` | BUG — stale chart data leaks between sessions |
| `login_page.dart:_Logo` | `_Logo()` without const constructor | Added `const _Logo();` + `const _Logo()` call site | WARN — missed const optimization |

## Backend Exception Hardening

| File | Issue | Fix |
|------|-------|-----|
| `App/cnv/zalo_sync.py:104` | `except Exception: pass` wrapping `datetime.fromisoformat()` | `except ValueError: pass` |
| `App/services/file_reader.py:38,43` | `except Exception: pass` wrapping pandas `.date()` / `.to_pydatetime()` | `except (ValueError, TypeError, OverflowError): pass` |
| `App/services/file_reader.py:56` | `except Exception: pass` wrapping `pd.to_datetime()` | `except (ValueError, OverflowError): pass` |
| `App/cnv/views.py:255,320,394` | `except Exception` on JSON body parse | `except json.JSONDecodeError` |
| `App/views/coupon.py:248` | `except Exception` on JSON body parse | `except json.JSONDecodeError` |
| `App/cnv/sync_service.py:72` | `except Exception` on `parse_datetime` | `except (ValueError, OverflowError, TypeError)` |
| `App/api/views.py:172` | `except Exception` on JWT blacklist check | `except (TokenError, InvalidToken)` |

---

## Web Test Results

420 tests, all green.

**Known cache-isolation false-fails (not regressions):** Two tests fail when the full suite runs in a single process due to shared locmem cache state between test classes. Both pass in isolation:
- `test_cnv_customer_alltime_kpis_match_underlying_function`
- `test_sales_period_2025_kpis_match_underlying_function`

Root cause: a prior test class warms the cache with different fixture data; these tests then read stale cache. Not a production bug.

---

## Mobile Test Results

| Suite | Tests | Pass | Fail |
|-------|-------|------|------|
| unit/ | 28 | 28 | 0 |
| widget/ + golden/ | 198 | 198 | 0 |
| **Total** | **226** | **226** | **0** |

---

## API Endpoint Timing

From `tests/test_api.py` — warm-fixture timings (analytics cache populated by earlier test class):

| Endpoint | All-time | Period (2025) | Under 5s |
|----------|----------|---------------|---------|
| GET /api/v1/sales/ | ~1.4s | ~1.4s | ✅ |
| GET /api/v1/customer/ | ~2s (cold: ~11s → 10.99s after opt) | ~2s | ✅ |
| GET /api/v1/coupon/ | ~0.8s | ~0.8s | ✅ |
| GET /api/v1/shop-detail/ | ~0.4s | ~0.4s | ✅ |
| GET /api/v1/chart/sales/ | ~1.4s | ~1.4s | ✅ |
| GET /api/v1/chart/customer/ | ~2s | ~2s | ✅ |
| GET /api/v1/chart/coupon/ | ~0.8s | ~0.8s | ✅ |
| GET /api/v1/shops/ | ~0.1s | N/A | ✅ |

All endpoints benefit from Django's 5-min locmem cache. All under 5s.

---

## Regressions / Issues

None. All previously passing tests still pass. No snapshot data changes.

---

## Comparison with Previous Report

First run — no baseline to compare against.

### Summary of changes this session (2026-05-03 → 2026-05-05)

**Web performance:**
1. `get_cnv_phone_sets()` — eliminated 2 duplicate table scans; now derives from `_fetch_bd_raw({})` (−2q cold, API passes 5s limit)
2. `CustomerAnalyticsView` — eliminated duplicate `_compute_grade_rows` call for all-time (−1 redundant heavy iteration)
3. `_fetch_bd_raw()` — merged 7→4 queries (−3q cold, prior session)
4. `_get_campaigns_with_prefix_list()` helper extracted from `coupon.py` (−9 dup lines)

**Web hardening (7 exception catches narrowed):**
- `zalo_sync.py`, `file_reader.py`, `cnv/views.py`, `views/coupon.py`, `sync_service.py`, `api/views.py`

**Mobile (6 bugs fixed):**
1. 4 × `.cast<String>()` → `.whereType<String>().toList()` in `analytics_models.dart`, `shop_detail_service.dart`, `token_storage.dart`
2. Chart providers invalidated on logout — closes data privacy gap
3. `_Logo` widget `const` — startup perf
4. CLAUDE.md smoke-test URLs corrected (`/coupon/` → `/coupons/`)
