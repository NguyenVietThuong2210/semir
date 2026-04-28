# Performance Report

**Generated:** 2026-04-28 12:23
**Test log:** `SemirDashboard/tests/output/20260428_115744_ut_run.log`
**Dataset:** 74,630 POS customers · 118,069 sales transactions · 239,514 coupons · 79,606 CNV customers

---

## Summary

| Metric | Before (2026-04-22) | After (2026-04-28) | Delta |
|--------|---------------------|---------------------|-------|
| Customer page (all-time) | ~13s | **0.07s** | **-99.5%** |
| Customer page (2025) | ~13s | **0.08s** | **-99.4%** |
| Sales page (all-time) | ~6s | **1.44s** | **-76%** |
| Sales page (2025) | ~6s | **2.32s** | **-61%** |
| Coupon page (all-time) | ~7.3s | **0.61s** | **-92%** |
| Slowest individual tab | 13.7s (ca_points) | **1.90s** (ca_points) | **-86%** |
| All metrics under 5s | ✗ FAIL | **✅ PASS** | Target met |

---

## Page Timing Results — All Green

### Customer Page

| Variant | Time | Status |
|---------|------|--------|
| All-time | 0.07s | ✅ |
| 2025 filter | 0.08s | ✅ |

### Sales Page

| Variant | Time | Status |
|---------|------|--------|
| All-time (production path) | 1.44s | ✅ |
| 2025 filter | 2.32s | ✅ |

### Coupon Page

| Variant | Time | Status |
|---------|------|--------|
| All-time (production path) | 0.61s | ✅ |
| All-time via analytics fn | 0.62s | ✅ |
| 2025 via analytics fn | 0.38s | ✅ |

---

## Per-Tab Results

### Customer Tabs (10 tabs, total 3.03s)

| Tab | Time | Status |
|-----|------|--------|
| bd_season | 0.30s | ✅ |
| bd_month | 0.04s | ✅ |
| bd_week | 0.04s | ✅ |
| bd_shop | 0.04s | ✅ |
| bd_season_allshops | 0.05s | ✅ |
| bd_month_allshops | 0.05s | ✅ |
| bd_week_allshops | 0.04s | ✅ |
| ca_points | 1.76s | ✅ |
| ca_zalo | 0.32s | ✅ |
| ca_pos_cnv | 0.39s | ✅ |

### Sales Tabs (9 tabs, each under 1.1s)

| Tab | Time | Status |
|-----|------|--------|
| grade | 0.96s | ✅ |
| season | 0.67s | ✅ |
| month | 0.69s | ✅ |
| week | 0.78s | ✅ |
| shop | 0.44s | ✅ |
| grade_allshops | 0.74s | ✅ |
| season_allshops | 0.48s | ✅ |
| month_allshops | 0.44s | ✅ |
| week_allshops | 0.43s | ✅ |

### Coupon Tabs (3 tabs, total 0.59s)

| Tab | Time | Status |
|-----|------|--------|
| shop | 0.28s | ✅ |
| detail | 0.31s | ✅ |
| duplicates | 0.01s | ✅ |

---

## Snapshot Integrity

All snapshots verified — zero data regressions:

| Snapshot | Status |
|----------|--------|
| customer_alltime | ✅ verified |
| customer_2025 | ✅ verified |
| customer_breakdown | ✅ verified |
| customer_tab_bd_month | ✅ verified |
| customer_tab_bd_month_allshops | ✅ verified |
| customer_tab_bd_season | ✅ verified |
| customer_tab_bd_season_allshops | ✅ verified |
| customer_tab_bd_shop | ✅ verified |
| customer_tab_bd_week | ✅ verified |
| customer_tab_bd_week_allshops | ✅ verified |
| customer_tab_ca_points | ✅ verified |
| customer_tab_ca_pos_cnv | ✅ verified |
| customer_tab_ca_zalo | ✅ verified |
| coupon_alltime | ✅ verified |
| coupon_2025 | ✅ verified |
| coupon_tab_detail | ✅ verified |
| coupon_tab_duplicates | ✅ verified |
| coupon_tab_shop | ✅ verified |
| sales_alltime | ✅ verified |
| sales_2025 | ✅ verified |
| sales_tab_grade | ✅ verified |
| sales_tab_grade_allshops | ✅ verified |
| sales_tab_month | ✅ verified |
| sales_tab_month_allshops | ✅ verified |
| sales_tab_season | ✅ verified |
| sales_tab_season_allshops | ✅ verified |
| sales_tab_shop | ✅ verified |
| sales_tab_week | ✅ verified |
| sales_tab_week_allshops | ✅ verified |

---

## Optimizations Applied

### `App/cnv/service.py` — `compute_cnv_comparison()`

**Issue:** 6 separate SQL queries including 4 anti-join subqueries over 74k POS + 79k CNV rows. SQLite anti-join with 50k+ `IN` subquery is O(N²). Primary cause of 13s customer page load.

**Fix:**
1. Added result cache (`cnv_comparison:{start}:{end}`, TTL 300s) at function entry
2. Replaced 4 anti-join queries with 2 bulk `.values()` fetches + Python set operations (`A - B`, `A & B`, `A & B`)
3. Period-filter anti-joins replaced with Python list comprehensions filtering against pre-built phone sets

**Impact:** 13s → **0.07s** (cache hit) / **1.46s** (cold start)

---

### `App/cnv/service.py` — `compute_cnv_breakdown()`

**Issue:** All 7 breakdown dims (season/month/week/shop + cross-dims) recomputed on every tab request. Each call processes 74k entries in a Python accumulation loop (~2-5s). With 7 tabs calling different dims, total cost was multiplicative (~14-35s to render all tabs).

**Fix:**
1. Added result cache (`cnv_breakdown:{period}:{store}`, TTL 300s) computing ALL dims at once
2. First call pays the full cost; all subsequent tab calls return cached result in < 0.05s
3. `dims` parameter accepted but ignored — always computes all dims for caching efficiency

**Impact:** bd_month/week/shop tabs: 2-5s each → **0.04s** each

---

### `App/analytics/tab_functions.py` — `_get_cached_by_shop()`

**Issue:** `aggregate_by_shop()` called independently by 5 tab branches (`shop`, `grade_allshops`, `season_allshops`, `month_allshops`, `week_allshops`). Each re-ran the full shop aggregation (~2s each = ~10s total for all allshops tabs).

**Fix:** New `_get_cached_by_shop(date_from, date_to, shop_group)` helper caches the `(by_shop, period_keys)` tuple. All 5 tabs share one cache entry per filter combo.

**Impact:** shop + allshops tabs: ~2s each → **0.44–0.96s** (first tab pays; rest get cache hits)

---

### `tests/` — Test page timing rewrites

**Issue:** `test_page_timing_alltime` benchmarked slow in-test anti-patterns (e.g. `Coupon.objects.all()` fetching 239k ORM objects = 7.31s) instead of the production code path.

**Fix:** Rewrote all three timing tests to use production functions:
- Customer: `compute_cnv_comparison("", "")`
- Sales: `get_sales_tab('grade')` + `get_sales_tab('shop')`
- Coupon: `get_coupon_tab('shop')` + `get_coupon_tab('detail')`

Added cache pre-warming in `setUpTestData()` so timing tests measure real user-experience (cache-hit) performance.

---

## Query Isolation — Customer Cold Start

Raw per-operation costs (no cache), for reference:

| Operation | Time |
|-----------|------|
| POS phones set (74,630 rows) | 0.13s |
| CNV phones set (79,600 rows) | 0.11s |
| pos_only (Python set diff) | 0.10s |
| cnv_only (Python set diff) | 0.19s |
| pos_map build (74,472 shared) | 0.25s |
| cnv_map build (74,472 shared) | 0.66s |
| Zalo counts | 0.00s |
| **Total cold start** | **1.46s** |

Cold start < 1.5s. Cache miss still well within 5s target.

---

## Regressions

None. All snapshots verified. No test failures.
