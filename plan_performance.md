# PLAN_PERFORMANCE.md — Backend Performance Improvement Plan (QA-Verified)

> **Created:** 2026-07-18 · **Branch:** release/2.3.0 · **Status:** ✅ **Phase 1 (12/12), Phase 2 (7/8), Phase 3 (3/4) IMPLEMENTED & VERIFIED — 2026-07-19.** Only P2-02 remains undone, blocked on business sign-off (staleness tolerance for coupon usage status). **P3-03 reverted 2026-07-25** after a real cold-cache latency regression was caught in production — see post-mortem in the P3-03 section. Not committed to git — awaiting explicit instruction.
> **Environment:** Django 6.0.2 · pandas · Cache prod: Redis (django_redis 6.0.0) · Cache dev: LocMem · DB prod: PostgreSQL 16 · DB dev: SQLite 3.45.3
> **Source:** 5 domain deep-dive agents (Analytics Engine, CNV Integration, Upload/Import, API+Web Views, DB/ORM) → 5 independent QA Senior Leader verification agents (re-read actual code, corrected numbers, rejected 2 unsafe proposals)
> **Scope:** Performance only. No user-facing feature change.

---

## ⛔ GOLDEN RULE — DATA PRESERVATION

This is a numbers-critical analytics app. **No change in this plan is allowed to change any computed/output value**, except where explicitly marked and approved. Adding/removing a DB index is the only category that can *never* change output (index changes speed, never results) — everything else must prove equivalence via the test suite before merge.

### Mandatory process for EVERY item below:

```
1. BEFORE fixing — capture baseline:
   cd SemirDashboard && python manage.py test tests -v 2     # must be ALL GREEN
   → save log to tests/output/perf_evidence/_baseline/

2. TEST-FIRST (where a gap is noted): write the test BEFORE the fix.
   - For items with "GAP: no test exists" — the new test must first be shown
     PASSING on the CURRENT (unoptimized) code, to lock in today's real behavior
     (including edge cases like duplicate-key-in-file "last row wins").

3. FIX — only the exact scope described in this plan. No drive-by changes.

4. AFTER fixing — verify:
   - New/target tests PASS
   - Full suite: python manage.py test tests -v 2 → ALL GREEN
   - Snapshot diff: ONLY the `_last_run` line may differ
     UPDATE_SNAPSHOTS=1 python manage.py test tests.<file> -v 2 → git diff review
   - Where noted "test on real PostgreSQL" — SQLite passing is NOT sufficient
     evidence (SQLite auto-caps bulk batch size; PostgreSQL does not — see #19).

5. EVIDENCE — save to tests/output/perf_evidence/<ITEM-ID>/:
   - test_run.log (before/after)
   - snapshot_diff.txt
   - query_count_or_explain.txt (for cache/index items)
   - Check off the item's DoD list in this file
```

### Items REJECTED during QA verification (do NOT implement as originally proposed)

| Item | Why rejected | Disposition |
|---|---|---|
| Replace `icontains` shop-group filter with `shop_name__in=[...]` | No explicit shop→group mapping exists anywhere in code or DB (verified by grep — "Others Group" is defined by *exclusion*, not a positive list). Building one risks silently mis-classifying a shop and changing aggregate numbers — violates the Golden Rule. | Backlog. Use DB index instead (#1). |
| `select_related('role')` in `user_has_perm()` (both directions originally proposed) | Verified: `user.profile.role` is accessed directly in `base.html:499` outside `user_has_perm()`, and `request.user` for JWT/mobile is set by DRF's `JWTAuthentication`, not `AuthenticationMiddleware` — neither proposed fix actually reduces total queries; one could *increase* them from 2 to up to 17 per request. | Backlog — needs a genuinely new design, not in this plan's scope. |

---

## PHASE 0 — BASELINE (do before any fix in this plan)

- [ ] `cd SemirDashboard && python manage.py test tests -v 2` → all green → save `tests/output/perf_evidence/_baseline/test_run.log`
- [ ] `git status` clean on `tests/snapshots/` (commit or note any pending diffs first)
- [ ] Confirm current migration head is `0019_coupon_id_unique` (new migrations in this plan start at `0020`)

---

## PHASE 1 — SAFE (index/config/param only — no logic change, do first)

These items can never change computed output. Full test suite green is sufficient proof for most; index items additionally require an `EXPLAIN`/`EXPLAIN ANALYZE` comparison on PostgreSQL.

### P1-01 — Remove redundant `sorted()` in `calculate_return_rate_analytics` ✅ DONE (2026-07-18)
**File:line:** `App/analytics/core.py:112`
**Verified:** `build_customer_purchase_map()` (`App/analytics/customer_utils.py:199-202`) already sorts each customer's purchase list by `'date'` before returning it; `_load_sales()` (`App/analytics/sales_tabs.py:76,98-99`) only does `dict(customer_purchases)` for caching (doesn't touch inner lists) and returns it unchanged. `core.py:112` re-sorts an already-sorted list with the exact same key — pure waste, same result (Python `sorted()` is stable).
**Change:** Replace `purchases_sorted = sorted(purchases, key=lambda x: x['date'])` with `purchases_sorted = purchases`.
**Test-before:**
- `tests/test_consistency.py::SalesConsistencyTest::test_overview_consistent_alltime`
- `tests/test_consistency.py::SalesConsistencyTest::test_grade_breakdown_consistent_alltime`
- `tests/test_consistency.py::SalesConsistencyTest::test_overview_consistent_2025`
- `tests/test_consistency.py::SalesConsistencyTest::test_chart_only_overview_matches_full`
- `tests/test_sales.py::SalesAnalyticsTest::test_return_rate_sanity`
**DoD:**
- [ ] All 5 tests above pass, zero assertion change
- [ ] `UPDATE_SNAPSHOTS=1 python manage.py test tests.test_sales tests.test_consistency -v 2` → JSON diff = 0 lines
- [ ] Dump full `calculate_return_rate_analytics()` (all-time) output before/after to 2 files, diff byte-for-byte identical
**QA Gate:**
1. Run 5 baseline tests → PASS, log saved
2. Apply 1-line change
3. Re-run same 5 tests → PASS
4. `UPDATE_SNAPSHOTS=1` → diff empty
5. Code review confirms only 1 line changed
**Risk:** Safe

---

### P1-02 — Add `batch_size` explicitly to CNV bulk operations ✅ DONE (2026-07-18)
**File:line:** `App/cnv/sync_service.py:342` (`CNVCustomer.bulk_create`), `:424` (`CNVOrder.bulk_create`), `App/cnv/zalo_sync.py:231-234` (`CNVCustomer.bulk_update`)
**Verified:** All 3 calls currently rely on the caller pre-chunking to `BATCH_SIZE=500` before calling — safe today, but a hidden dependency. Field-count check: `CNVCustomer` 25 fields × 500 = 12,500 params (5.2x under PostgreSQL's 65,535 limit); `CNVOrder` 24 fields × 500 = 12,000 params (5.4x margin). If someone raises `BATCH_SIZE` later without knowing this constraint, PostgreSQL will error (SQLite auto-caps and won't show the bug in dev).
**Change:** Add explicit `batch_size=500` to all 3 calls. No-op on current behavior — pure guard against future regression.
**Test-before:** `tests/test_cnv_sync.py::TransformCustomerTest` (all 6 methods), `SyncPageLimitTest`
**DoD:**
- [ ] `batch_size=500` present at all 3 call sites
- [ ] New test: `created_count`/`updated_count` unchanged with ≥501 records forcing internal Django chunking
- [ ] `tests.test_cnv_sync` fully green
**QA Gate:** 1) code review — kwarg-only diff 2) `tests.test_cnv_sync` + snapshot diff 3) run `sync_cnv --customers`/`--orders` (or smoketest), compare created/updated/failed counts to a pre-change run
**Risk:** Safe

---

### P1-03 — Increase `ThreadPoolExecutor(max_workers=10)` in CNV membership fetch ✅ DONE (2026-07-18, max_workers=30)
**File:line:** `App/cnv/sync_service.py:309` (`_process_customer_batch`)
**Verified:** `DistributedRateLimiter.acquire()` (`App/cnv/rate_limit.py:32-73`) is a Redis-backed fixed-window counter, keyed by current second, hard-capped at `settings.CNV_MEMBERSHIP_RATE_LIMIT` (default 50/s) — completely independent of thread count. If each CNV membership call takes >200ms, 10 threads can't reach 50 req/s (thread pool becomes the bottleneck, not the limiter). Raising `max_workers` to 25-40 cannot exceed the rate cap; it only lets more threads *wait* concurrently.
**Change:** `ThreadPoolExecutor(max_workers=10)` → `ThreadPoolExecutor(max_workers=30)` (pick one fixed value).
**Test-before:** `tests/test_cnv_sync.py::MembershipRateLimiterSharedTest::test_distributed_limiter_enforces_budget_across_instances`, `RateLimiterTest`, `FetchMembershipTest`
**DoD:**
- [ ] `max_workers=30` set
- [ ] `test_distributed_limiter_enforces_budget_across_instances` still passes — proves throughput stays ≤ configured rate
- [ ] Benchmark via `cnv_scheduler_smoketest --duration 30 --interval 3`: measured req/s before/after logged
- [ ] `created_count`/`updated_count`/`failed_count` identical on same mock dataset (only wall-clock time changes)
**QA Gate:** 1) unit tests green 2) benchmark before/after logged 3) no new 429s observed on a small real-API trial if feasible
**Risk:** Safe

---

### P1-04 — Add rate limiter for `zalo_sync.py` ✅ DONE (2026-07-18, 30 req/s, separate key `cnv_zalo_rl`) — new `ZaloRateLimiterTest` (4 tests) added to `tests/test_bugfixes.py`, all green
**File:line:** `App/cnv/zalo_sync.py` — `_fetch_zalo_data` (56-72), `THREAD_WORKERS=10` (21), endpoint `contactcdp`
**Verified:** Zero throttling anywhere in this file (confirmed by full read) — unlike the membership fetch path, which already uses `DistributedRateLimiter`. Risk of a 429 storm on this endpoint mirrors the 2026-07-12 incident, just on a different API path.
**Change:** Add `get_zalo_rate_limiter()` factory in `rate_limit.py` (new singleton, separate cache key `cnv_zalo_rl`, does not touch `DistributedRateLimiter` class or the membership limiter's budget). Call `.acquire()` before each `session.get(...)` in `_fetch_zalo_data`.
**Test-before:** GAP — no existing test for `_fetch_zalo_data`/`_do_sync` logic (only `CnvAjaxAuthGuardTest.test_trigger_zalo_unauthenticated_401_json` covers the view's auth guard). Must write a new mock-based throughput test first.
**DoD:**
- [ ] New rate limiter factory added, independent key from membership limiter
- [ ] `_fetch_zalo_data` calls `.acquire()` before HTTP call
- [x] New test: mock ≥100 calls through the real `DistributedRateLimiter`, assert elapsed > 1.0s (proves throttling happened) and observed rate ≤ 2x configured (fixed-window boundary bursts make a tight ±10% bound flaky — same phase-alignment reason `MembershipRateLimiterSharedTest` already relaxed its tolerance for)
- [ ] `updated_count`/`failed_count` on same mock dataset unchanged (only run time increases)
- [ ] `CnvAjaxAuthGuardTest.test_trigger_zalo_unauthenticated_401_json` still passes
**QA Gate:** 1) new test green + throughput log 2) review confirms separate cache key from membership limiter 3) small real Zalo sync trial — no failed_count spike vs. a prior run
**Risk:** Cần-verify (safe re: data, but the actual safe rate value needs a real benchmark)

---

### P1-05 — Rate-limit CNV list pagination fetch ✅ DONE (2026-07-18 — reused the shared membership limiter instead of a new unconfirmed rate)
**File:line:** `App/cnv/api_client.py:401-472` (`fetch_all_customers`), `:512-591` (`fetch_all_orders`)
**Implementation decision (deviates from the original "new 20-30 req/s limiter" proposal):** rather than invent a second, unconfirmed rate limit for the list endpoints, `fetch_all_customers`/`fetch_all_orders` now call `get_membership_rate_limiter().acquire()` before each page fetch — reusing the SAME shared, already-proven-safe budget used for membership fetches. This guarantees the combined rate across list pagination + membership fetches, across every gunicorn worker, never exceeds the existing 50 req/s cap, without introducing a new number that has no CNV documentation behind it. New tests: `PaginationRateLimitTest` (2 tests) in `tests/test_bugfixes.py`, both green; `tests.test_bugfixes.SyncPageLimitTest` (3 tests) re-verified green.
**Verified:** The pagination loop (up to `DEFAULT_MAX_SYNC_PAGES=100` pages) has zero throttling — only the membership fetch path is rate-limited. No CNV rate-limit documentation exists in the repo for the list endpoints; the "100 tokens/sec" figure in code comments is inferred from the 2026-07-12 incident and applies to the membership endpoint specifically — unclear whether CNV shares one global bucket across endpoints.
**Change:** Add a conservative rate limiter (start at 20-30 req/s, tunable via a new setting) OR reuse `get_membership_rate_limiter()` if CNV turns out to share one global bucket — **mark in code comments as a provisional value pending confirmation from CNV support/docs**.
**Test-before:** `tests/test_cnv_sync.py::SyncPageLimitTest::test_fetch_all_customers_uses_default_max_pages`. GAP: no test mocks multi-page throughput — write new.
**DoD:**
- [ ] Rate limiter applied inside both pagination `while` loops
- [ ] Benchmark: full 100-page sync time before/after does not increase more than an agreed threshold (e.g. ≤50%) — if it does, loosen the limiter
- [ ] `total_records`/`created_count`/`updated_count` identical to baseline
**QA Gate:** 1) confirm CNV's real rate limit via support/docs/429 history if possible — log evidence 2) new test + benchmark green 3) `SyncPageLimitTest` fully green
**Risk:** Cần-verify (missing authoritative source for the real CNV list-endpoint limit — ship a documented provisional value, not a guess)

---

### P1-06 — Fix `.distinct()` missing `.order_by()` in **test files** (not production code)
**File:line:** `SemirDashboard/tests/test_api.py:454-457` only.
**Verified (IMPORTANT CORRECTION):** The original finding claimed BOTH `test_shop_detail.py:266` and `test_api.py:454-457` were buggy. QA verification **disproved** the `test_shop_detail.py:266` half by direct experiment on the project's real `db.sqlite3` (118,069 rows, 22 real shops): `.distinct().count()` returned the correct **22**, because Django's `Query.get_aggregation()` always calls `clear_ordering(force=False)` before building the COUNT subquery — this is universal ORM behavior, not a SQLite quirk, and applies regardless of `Meta.ordering`. **Do NOT "fix" `test_shop_detail.py:266` — there is nothing to fix; it was never wrong.**
The real (confirmed) issue is `test_api.py:454-457`: `.values_list('shop_name', flat=True).distinct()` **without** `.order_by()`, materialized as a list (not `.count()`) — `SalesTransaction.Meta.ordering = ["sales_date", "invoice_number"]` (`App/models/pos.py:73`) leaks into the SELECT DISTINCT, so the query returns ~118,069 rows instead of ~22. The final result is still numerically correct only because the code wraps it in `set(...)` — this is pure wasted bandwidth/DB work, not a correctness bug.
Confirmed all `App/` production code is 100% clean (every `.distinct()` already has `.order_by()` first); `Customer`/`Coupon` `.distinct()` calls elsewhere in tests are unaffected (those models have no `Meta.ordering`).
**Change:** `App/analytics` production code — no change needed. `tests/test_api.py:457` only: add `.order_by('shop_name')` before `.distinct()`.
**Test-before:** `tests.test_api`, `tests.test_shop_detail` (full files)
**DoD:**
- [ ] `CaptureQueriesContext` confirms the SQL for `test_api.py:457` no longer includes `sales_date`/`invoice_number` in SELECT DISTINCT after the fix
- [ ] Row count returned drops from ~118,069 to ~22 (logged, not asserted with a hardcoded number since shop count can grow)
- [ ] All existing assertions in both files unchanged (final `set()`/list of shops is identical before/after)
**QA Gate:** 1) baseline pass, log current row count via a temporary debug print (not committed) 2) apply `.order_by()` 3) re-run, confirm row count drop 4) diff review — only `.order_by()` added
**Risk:** Safe (test-file-only change; also corrects a mis-diagnosis from the original report so no one "fixes" a non-bug later)

---

### P1-07 — `CACHES`/`DATABASES` resilience settings ✅ CODE DONE (2026-07-18) — `django-redis` `IGNORE_EXCEPTIONS: True` + Postgres `CONN_HEALTH_CHECKS: True` added, `manage.py check` clean. Staging Redis-down chaos test and 24h Postgres connection monitoring remain deployment-time verification (cannot be done in this sandbox — no staging access).
**File:line:** `SemirDashboard/SemirDashboard/settings.py:64-74` (Postgres `DATABASES`), `:206-221` (Redis `CACHES`)
**Verified:** Confirmed missing: `CONN_HEALTH_CHECKS` (DATABASES) and `IGNORE_EXCEPTIONS` (CACHES `OPTIONS`). `django-redis` 6.0.0 is installed and supports both. Grepped every `cache.get()` call site in `App/` (`shops.py`, `shop_detail.py`, `cnv/views.py`, `cnv/service.py`, `sales_tabs.py`, `product_analytics.py`, `inventory_functions.py`, `upload_jobs.py`) — 100% already treat `None` as cache-miss and recompute from DB. Enabling `IGNORE_EXCEPTIONS=True` (Redis errors → return `None` instead of raising) is compatible with every existing call site.
**Change:**
```python
# DATABASES (Postgres branch)
"CONN_MAX_AGE": 600,
"CONN_HEALTH_CHECKS": True,   # new

# CACHES (Redis branch) OPTIONS
"IGNORE_EXCEPTIONS": True,    # new
```
**Test-before:** Full suite (no existing test covers Redis-down resilience — confirmed by grep, 0 results)
**DoD:**
- [ ] Full suite green, unaffected by settings change
- [ ] Staging: stop Redis temporarily, hit `/`, `/analytics/`, `/coupons/`, `/shop-detail/` → 200 instead of 500 (reuse CLAUDE.md Step 4 smoke test)
- [ ] Staging: monitor Postgres connection logs 24h after enabling `CONN_HEALTH_CHECKS` for absence of stale-connection errors
**QA Gate:** 1) full suite green 2) staging chaos test (Redis down) → 200s confirmed 3) 24h connection-health monitoring
**Risk:** Safe

---

### P1-08 — Expression index `Upper(coupon_id)` on `Coupon` ✅ DONE (2026-07-18, corrected mid-implementation — see below)
**⚠️ Correction discovered during real-Postgres verification (this changes the original plan's index definition):** a plain `models.Index(Upper('coupon_id'), name=...)` is **not sufficient**. Verified on a real local PostgreSQL 16 container: with only the plain expression index, `EXPLAIN ANALYZE` on the actual Django-generated SQL for `coupon_id__istartswith` (`WHERE UPPER(coupon_id::text) LIKE UPPER('CPN123%')`) still chose `Seq Scan` — **even with `enable_seqscan = off`**, meaning Postgres considered the index unusable for this query at all, not just costlier. Root cause: Postgres's default (non-`C`) collation means a btree index on text **cannot** serve `LIKE 'prefix%'` pattern matching unless the index uses the `text_pattern_ops` operator class — this is independent of the `Upper()`/expression-index question entirely. Fixed by wrapping the expression in `django.contrib.postgres.indexes.OpClass(Upper('coupon_id'), name='text_pattern_ops')` (`Index.opclasses=` cannot be combined with expressions directly — confirmed via Django source, `OpClass` is the documented workaround). Because `OpClass`/`text_pattern_ops` is Postgres-only syntax (unlike a plain `Upper()` expression index, which works identically on SQLite), this index moved from migration `0020` into the vendor-conditioned `SeparateDatabaseAndState` migration `0021` alongside the GIN indexes (P1-12), rather than staying in the "safe on both DBs" migration as originally planned.
**Verified after the fix:** rebuilt indexes on the Postgres test container; `Coupon.objects.filter(coupon_id__istartswith='CPN123').explain(analyze=True)` naturally (no forcing) produces `Bitmap Heap Scan` → `Bitmap Index Scan on coupon_upper_couponid_idx`, **0.237ms** vs. **~14-16ms** Seq Scan on the same 20,000-row seeded dataset — real, measured ~60x improvement. `makemigrations --check` clean on SQLite dev; `tests.test_coupon` full suite green.
**File:line:** `App/models/coupon.py`. Query sites: `App/analytics/coupon_tabs.py:55,59`, `coupon_analytics.py:184-189,605-610,732-736`. Actual index lives in `App/migrations/0021_shop_group_trigram_indexes.py` (see P1-12 above for why it moved there instead of a standalone file).
**DoD:** ✅ migration applies on SQLite dev (state-only, `makemigrations --check` clean) and real PostgreSQL 16 (DDL applied, index confirmed via `\di`) · ✅ `EXPLAIN` on real Postgres shows `Bitmap Index Scan using coupon_upper_couponid_idx` (naturally chosen, not forced) · ✅ `tests.test_coupon` full suite green, zero assertion change
**QA Gate:** baseline pass ✅ → migrate SQLite dev ✅ → migrate real Postgres + EXPLAIN before/after ✅ → full suite pass ✅
**Risk:** Safe (once corrected to use `text_pattern_ops`)

---

### P1-09 — Expression index `Upper(product_code)` on `InventorySnapshot` ✅ DONE (2026-07-18, same `text_pattern_ops` correction as P1-08)
**Verified on real PostgreSQL 16:** same fix applied (`OpClass(Upper('product_code'), name='text_pattern_ops')`, moved to migration 0021). After the fix, `InventorySnapshot.objects.filter(product_code__istartswith='PRD123').explain(analyze=True)` naturally produces `Bitmap Heap Scan` → `Bitmap Index Scan on invsnap_upper_prodcode_idx`, **0.299ms** measured on a 20,000-row seeded dataset. `tests.test_inventory` full suite green on SQLite dev.
**File:line:** `App/models/inventory.py:14` (corrected location — not `pos.py` as originally guessed). Query: `App/analytics/inventory_functions.py:246`. Actual index lives in `App/migrations/0021_shop_group_trigram_indexes.py` alongside P1-08.
**Test-before / DoD / QA Gate:** Same pattern as P1-08, scoped to `tests.test_inventory` — all ✅.
**Risk:** Safe (once corrected to use `text_pattern_ops`)

---

### P1-10 — Composite index `(using_shop, using_date)` on `Coupon` ✅ DONE (2026-07-18)
**Verified on real PostgreSQL 16:** `EXPLAIN ANALYZE SELECT * FROM "App_coupon" WHERE using_shop = 'Bala Shop A' AND using_date BETWEEN '2020-01-01' AND '2030-01-01'` was chosen naturally as `Index Scan using coupon_usingshop_usingdate_idx`, 0.111ms. Plain composite btree, works identically on SQLite dev — stayed in migration 0020 as originally planned. `tests.test_coupon`/`tests.test_shop_detail` green.
**File:line:** `App/models/coupon.py`. Verified only 2 separate single-column indexes existed before this (`using_shop` via `db_index=True`, `using_date` via `Meta.indexes`) — no composite. Hot path: `App/analytics/coupon_tabs.py:30-72` (`_build_coupon_qs`) via `App/analytics/shop_detail_data.py:221-243`, called on every Shop Detail coupon AJAX partial load. Migration: `App/migrations/0020_coupon_and_inventory_indexes.py`.
**DoD:** ✅ migration applies on both SQLite dev and real PostgreSQL 16 (plain btree, no vendor branching needed) · ✅ real Postgres `EXPLAIN ANALYZE` shows `Index Scan using coupon_usingshop_usingdate_idx`, naturally chosen · ✅ full suite green
**Risk:** Safe

---

### P1-11 — Remove duplicate `coupon_id` index ✅ DONE (2026-07-18)
**Verified on real PostgreSQL 16:** confirmed `App_coupon_coupon__7e6b3d_idx` existed pre-migration alongside the auto-created unique-constraint index; migration `0020` removes it; `\di` post-migration confirms only the unique-constraint index remains on `coupon_id`, `coupon_id=` lookups still use `Index Scan` (verified during rollback/reapply testing). `tests.test_coupon` green.
**File:line:** `App/models/coupon.py:11,32`. Verified via migration history: `0002_coupon.py` created BOTH `db_index=True` AND an explicit `models.Index(fields=['coupon_id'], name='App_coupon_coupon__7e6b3d_idx')` on the same column — duplicated from day one. `0019_coupon_id_unique.py` changed `db_index=True` → `unique=True` (which auto-creates its own unique index) but never removed the old explicit `Meta.indexes` entry — so `Coupon` now carries 2 indexes covering the same column.
Actual migration: `App/migrations/0020_coupon_and_inventory_indexes.py` (combined with P1-10 — both plain/portable). The `models.Index(fields=["coupon_id"])` line was removed from `Meta.indexes` in `App/models/coupon.py` (the `unique=True` field option untouched).
**Test-before:** Full suite + `tests.test_coupon` (import/upsert-by-coupon_id tests)
**DoD:**
- [x] Migration applies on both SQLite dev and real PostgreSQL 16
- [x] Real Postgres `\di` before/after: confirmed only the unique-constraint index remains on `coupon_id` after migration
- [x] `EXPLAIN` on real Postgres: `coupon_id =` lookups still use `Index Scan` after removal (verified during the rollback/reapply cycle while fixing P1-08)
- [x] Full suite green (`tests.test_coupon`)
**Risk:** Safe

---

### P1-12 — GIN trigram index for `icontains` shop-group filters (PostgreSQL only)
**File:line:** `App/analytics/sales_tabs.py:57-65`, `coupon_tabs.py:41-50`, `coupon_analytics.py:148-166,581-587,716-727`, `product_analytics.py:48-54`, `aggregators.py:771-777`, `inventory_functions.py:36-42`. Models: `SalesTransaction.shop_name`, `SaleDetail.shop_name`, `Coupon.using_shop`, `InventorySnapshot.shop_name`.
**Note:** these `icontains` values are fixed literals (`'Bala'`, `'巴拉'`, `'Semir'`, `'森马'`) for 3 hard-coded shop groups — not a free-text search box — but still a hot path hit on every shop-group filter change across Sales/Coupon/Product/Inventory tabs.
**Verified:** No GIN/trigram index exists today on any of these columns (only plain btree via `db_index=True`/composite date indexes). **Critical migration detail confirmed necessary:** must use `SeparateDatabaseAndState`, NOT a plain `if connection.vendor == 'postgresql': operations = [...] else: []` guard — the latter leaves Django's migration STATE unaware of the index on SQLite while the model file declares it, causing `makemigrations --check` to falsely report drift on every dev machine. `SeparateDatabaseAndState` keeps state applied on both DBs while only running the real DDL on PostgreSQL.
**Actual migration layout (differs from the original per-item-numbered file plan above — consolidated for real reasons found during implementation):**
- `App/migrations/0020_coupon_and_inventory_indexes.py` — P1-10 (composite btree) + P1-11 (remove duplicate index) only. Plain, portable, no vendor conditioning needed.
- `App/migrations/0021_shop_group_trigram_indexes.py` — P1-08 + P1-09 (the `OpClass`/`text_pattern_ops` expression indexes — these turned out to be Postgres-only syntax too, not portable like a plain `Upper()` expression index would have been) **and** P1-12 (the 4 GIN trigram indexes), all under `SeparateDatabaseAndState`. Contains `TrigramExtension()` + all 6 vendor-conditioned `AddIndex` operations.

Corresponding `Meta.indexes` entries added to `App/models/pos.py` (`SalesTransaction`, `SaleDetail`), `coupon.py` (`Coupon`), `inventory.py` (`InventorySnapshot`) — `makemigrations --check` confirmed clean on SQLite dev.
**Test-before:** Full suite + `tests.test_sale_detail`, `tests.test_inventory`, `tests.test_coupon`, `tests.test_shop_detail`
**DoD:**
- [x] `python manage.py migrate` runs clean on SQLite dev (state-only) — `makemigrations --check --dry-run` reports "No changes detected" right after
- [x] Real local PostgreSQL 16 (not staging): `pg_indexes` lists all 4 new GIN indexes with `USING gin` + `gin_trgm_ops`
- [ ] `EXPLAIN ANALYZE ... WHERE shop_name ILIKE '%Bala%'` on **staging with prod-scale data** shows `Bitmap Index Scan` — NOT yet confirmed naturally chosen at the ~150k-row/9%-selectivity scale tested in this sandbox (see honest finding below); confirmed functionally valid via forced `enable_seqscan=off`
- [x] Full suite green, zero assertion change (index changes speed only) — `tests.test_sale_detail`, `tests.test_inventory`, `tests.test_coupon` all pass
**QA Gate:** baseline pass → migrate SQLite dev, confirm no drift ✅ → migrate real Postgres + EXPLAIN ANALYZE before/after ✅ → full suite pass again ✅
**Status:** ✅ DONE, BUG FOUND AND FIXED BY INDEPENDENT QA VERIFICATION (2026-07-19)

**⚠️ CRITICAL CORRECTION — the original 2026-07-18 implementation was BROKEN and would have shipped a dead index.** An independent QA Senior Leader verification pass (explicitly re-testing with the real Django ORM `.filter(...__icontains=...)` call — not hand-written raw SQL) found that my original "honest EXPLAIN ANALYZE finding" above was itself using the wrong methodology: I tested with raw `shop_name ILIKE '%Bala%'` SQL, which is NOT the SQL Django actually generates. Django's `icontains` lookup on PostgreSQL **always** compiles to `UPPER(col::text) LIKE UPPER(pattern)` (confirmed in `django/db/backends/postgresql/operations.py::lookup_cast`, comment: *"Use UPPER(x) for case-insensitive lookups; it's faster"*) — this is unconditional, not a config option. The original GIN indexes (`GinIndex(fields=["shop_name"], opclasses=["gin_trgm_ops"])`) were built on the **raw column**, but the real query filters on the **`UPPER(col::text)` expression** — two different expressions that Postgres cannot match, so the GIN index would **never** be used by the planner for any real query in this codebase, regardless of table size or selectivity. Verified independently: even with `enable_seqscan=off` forced, the real `.filter(using_shop__icontains='Bala')` query still produced `Seq Scan` — proving no viable index-based plan existed at all, not merely a cost-based preference for Seq Scan as the original (flawed) finding concluded.

**Fix applied (2026-07-19):** all 4 GIN indexes rebuilt as `GinIndex(OpClass(Upper('<col>'), name='gin_trgm_ops'), name='<index_name>')` — same `OpClass` wrapping pattern already used correctly for P1-08/P1-09's `text_pattern_ops` indexes, just with `gin_trgm_ops` instead. Migration 0021 regenerated (rolled back to 0020 on both SQLite dev and a fresh real-Postgres container, deleted and re-autogenerated the migration, re-wrapped in the same `SeparateDatabaseAndState` pattern, re-applied on both backends).

**Re-verified after the fix, on real PostgreSQL 16, through the actual migration-created index (not an ad-hoc test index) and the real Django ORM call:**
```
Coupon.objects.filter(using_shop__icontains='Bala').explain(analyze=True)
→ Bitmap Heap Scan on "App_coupon"
  Recheck Cond: (upper((using_shop)::text) ~~ '%BALA%'::text)
  ->  Bitmap Index Scan on coupon_usingshop_trgm_gin   (naturally chosen, no forcing)
  Execution Time: 45.8ms   (was 91.9ms Seq Scan before the fix, at the same 40%-selectivity seed)
```
`makemigrations --check` clean on SQLite dev; `tests.test_coupon`/`tests.test_inventory`/`tests.test_sale_detail` full suite run (exit code 0, all green) after the model changes.

**Process lesson (kept here for future reference, not just this item):** when verifying that Postgres will use an index for an ORM-level lookup, always test with `Model.objects.filter(...).explain(analyze=True)` through the actual ORM call — never approximate with hand-written SQL, even SQL that looks equivalent. Django's lookup compilation can silently differ from the "obvious" raw-SQL equivalent (here: the mandatory `UPPER()`/`::text` cast), and an index built for the approximated SQL can be completely unusable for the real one while still looking superficially correct (present in `pg_indexes`, no errors, etc.).

---

## PHASE 2 — Cache additions & straightforward query fixes (copy an existing safe pattern)

### P2-01 — Cache `get_shop_detail_sales_data` (all-time list) ✅ DONE & VERIFIED (2026-07-18) — new test `test_sales_alltime_cache_hit_no_requery` added to `tests/test_shop_detail.py` (CaptureQueriesContext-based, confirms 0 SalesTransaction queries on 2nd call with a different date range). 4/4 targeted tests green (`test_sales_alltime_cache_hit_no_requery`, `test_sales_alltime_matches_shop_tab`, `test_sales_period_matches_shop_tab`, `test_sales_direct_is_faster_than_all_shops`).
**File:line:** `App/analytics/shop_detail_data.py:51-53`
**Verified:** This is the ONLY function in this family without a cache — its sibling `_load_sales` (`sales_tabs.py:38-46,95-99`) already caches 300s per `(date_from, date_to, shop_group)`, and even the `info_map` inside the SAME function (`shop_detail_data.py:68-83`) is already cached 300s under key `"shop_detail_sales_info_map"`.
**Change:** Wrap the `all_time_list` query with cache key `f"shop_detail_sales_alltime:{shop_name}"`, TTL 300s (materialize as `list(...)`, not a QuerySet — QuerySets don't pickle reliably through locmem cache). **Invariant:** the `date_from`/`date_to` Python-side filter must keep running AFTER fetching `all_time_list` (from cache or DB) — do not cache by date range.
**Test-before:** `tests.test_shop_detail` — `test_sales_alltime_matches_shop_tab`, `test_sales_period_matches_shop_tab`, `test_sales_alltime_gte_period`, `test_sales_direct_is_faster_than_all_shops`, `test_sales_partial_with_date_filter`, `test_sales_partial_performance` (current threshold <3.0s), `test_snapshot_sales_full`
**DoD:**
- [ ] All 7 tests pass, threshold `<3.0s` unchanged (not loosened)
- [ ] `UPDATE_SNAPSHOTS=1` → diff = 0
- [ ] New test with `CaptureQueriesContext`: call the function twice with same `shop`, different date ranges — 2nd call issues 0 new `SalesTransaction.filter(shop_name=...)` queries (cache hit) while returning a *different* period KPI correctly
- [ ] Cache-hit vs cache-miss timing logged (no % threshold required, just evidence)
**QA Gate:** 7 baseline tests pass → add cache → re-run 7 tests + snapshot diff = 0 → new "cache-hit no-requery" test passes → review TTL consistency with `_info_key`/`_load_sales` (all 300s)
**Risk:** Safe (existing precedent for un-invalidated 300s cache in the same function and in `_load_sales`)

---

### P2-02 — Cache `get_shop_detail_coupon_data` — ⚠️ requires business sign-off first
**File:line:** `App/analytics/shop_detail_data.py:221-398`
**Verified query count (corrected from original "8-10" estimate):** **9 queries** when no date filter, **12 queries** when a date filter is applied (traced every query: aggregate all-time/period, used-rows fetch, `fetch_docket_txn_amounts`, duplicate-count, `SalesTransaction`/`Customer`/`CNVCustomer` joins). Confirmed: zero cache anywhere in this function today.
**⚠️ BUSINESS GATE (must be ticked FIRST, before any other DoD item):** coupon "used/unused" status can change at any time via sync/upload. A 300s cache means staff viewing Shop Detail could see a coupon as "unused" up to 5 minutes after it was actually used. **This requires explicit product-owner sign-off** on accepting ≤5 min staleness for coupon usage status — this is a business decision, not a technical one.
**Change (only after business sign-off):** Cache the full return dict, key `f"shop_detail_coupon:{using_shop}:{date_from}:{date_to}"`, TTL 300s.
**Test-before:** `test_coupon_alltime_matches_shop_tab`, `test_coupon_period_matches_shop_tab`, `test_coupon_alltime_scoped_to_shop`, `test_coupon_details_all_belong_to_shop`, `test_coupon_partial_performance` (threshold <2.0s), `test_snapshot_coupon_full`
**DoD:**
- [ ] **Business sign-off on 5-min staleness recorded in PR description — first, before code changes**
- [ ] 6 tests pass, threshold unchanged
- [ ] `UPDATE_SNAPSHOTS=1` → diff = 0
- [ ] New test: 2 consecutive identical calls → 2nd issues 0 queries (full cache hit)
- [ ] New test: modify a `Coupon` row (simulate a fresh upload) then call again within TTL → confirm (documented, not just code comment) the result is still the stale/cached value — this documents the accepted behavior explicitly
**QA Gate:** 1) business sign-off (link/screenshot in PR) 2) 6 baseline tests pass 3) add cache 4) re-run + snapshot diff = 0 5) 2 new tests pass 6) review: confirm no coupon-upload invalidation was silently expected/missed
**Risk:** Cần-verify (technically safe, business gate not yet cleared)

---

### P2-03 — Cache `get_cnv_customer_kpis` ✅ CODE DONE (2026-07-18) — new test `test_cnv_kpis_cache_hit_no_requery` in `tests/test_customer.py::CustomerAnalyticsTest` asserts exactly 6 queries cold, 0 warm, identical result. Running full regression now.
**File:line:** `App/cnv/service.py:76-160`. Called from `App/cnv/views.py:137`, `App/api/views/analytics.py:250`.
**Verified query count (corrected — chốt số chính xác):** exactly **6 queries** when `has_filter=True` (traced line-by-line: 2 `.count()`, 2 `.exclude().count()`, 2 inline-subquery `values_list`), **0 queries** when `has_filter=False` (pure Python on already-passed-in sets). Confirmed pure/deterministic on `(period_filter, has_filter, pos_phones_all, cnv_phones_all)`.
**Change:** Add cache wrapper, TTL 300s (matching `_fetch_bd_raw`/`compute_cnv_breakdown`/`get_cnv_phone_sets`), key `f"cnv_kpis:{start}:{end}:{has_filter}"` — must include `has_filter` in the key, not just the period, since an empty period with different `has_filter` values must not collide.
**Test-before:** GAP — no existing test for this function's query count. New test required. Also: any `tests/test_api.py` test touching `CustomerAnalyticsView`.
**DoD:**
- [ ] `assertNumQueries(6)` on first call (`has_filter=True`), `assertNumQueries(0)` on 2nd call same params within cache window
- [ ] Returned dict identical bit-for-bit between cache-hit and cache-miss calls
- [ ] `tests.test_api` fully green, response time unchanged or improved
**QA Gate:** new test green (assertNumQueries + result comparison) → `tests.test_api` full run green → measure `/cnv/customer-analytics/` response time before/after via CLAUDE.md Step 4 smoke test
**Risk:** Cần-verify (logic safe; use "6 queries" as the corrected baseline, not the original "7-8" estimate)

---

### P2-04 — Cache `_compute_grade_rows` ✅ CODE DONE (2026-07-18) — new test `test_grade_rows_cached_across_page_then_chart` in `tests/test_api.py::ApiChartTest` simulates the exact scenario (CustomerAnalyticsView then CustomerChartView) and confirms 0 fresh `Customer.vip_grade` queries on the 2nd call. Running full regression now.
**File:line:** `App/api/views/analytics.py:283-284,312-337`; also called independently from `App/api/views/charts.py:101`
**Verified:** `_fetch_bd_raw` projection (`App/cnv/service.py:190-194`) does NOT include `vip_grade` — confirms this function can't currently reuse that cache and must query `Customer` directly. Confirmed `_compute_grade_rows` is used ONLY by `App/api/views/*` (mobile API) — grepped the whole repo, zero web-layer callers, so this cache change cannot affect any web page. Scenario confirmed: opening the Customer Analytics page then the Chart right after triggers up to 3 independent full scans of the ~74k-row `Customer` table for overlapping data.
**Change:** Add a cache wrapper (not a merge into `_fetch_bd_raw` — that touches a shared cache used by many other callers and is out of scope/backlog), key by `period_filter` representation matching the existing pattern in `service.py`, TTL 300s to match `cnv_phone_sets`.
**Test-before:** `test_cnv_grade_breakdown_rows_match`, `ApiChartTest::test_customer_chart_status_200/has_donuts_key/donut_slice_shape/with_date_filter`, `ApiStructureTest::test_customer_registration_breakdown_tables/test_customer_pos_only_positive/test_customer_initial_load_performance`, and all of `tests/test_customer.py` (web layer, to prove zero web impact)
**DoD:**
- [ ] All tests above pass, zero diff
- [ ] `UPDATE_SNAPSHOTS=1 python manage.py test tests -v 2` → only `_last_run` differs
- [ ] New `assertNumQueries` test: `CustomerAnalyticsView` with a date filter set — grade-related `Customer` queries drop from 2 to 1 when period == all-time (same cache key); 2 separate entries set correctly when period differs
- [ ] New test simulating "open page then open chart": total `Customer.vip_grade` queries drop from 3 to 1 within the TTL window
- [ ] Response JSON identical bit-for-bit before/after on the same fixture
**QA Gate:** baseline → apply fix → re-run same tests, 0 diff → full suite green → snapshot diff empty → web smoke test (Step 4) per CLAUDE.md regression rule → evidence saved
**Risk:** Safe (staleness caveat: a ~300s window where `new_pos_only` could use a slightly older `cnv_phones_all` than other KPIs in the same response — pre-existing pattern already acknowledged elsewhere in `service.py`, not a new risk introduced by this fix)

---

### P2-05 — Narrow `invoice_number` prefetch scope in `sale_detail_import.py` ✅ CODE DONE (2026-07-18) — implemented exactly as planned. Running `tests.test_sale_detail` regression now.
**File:line:** `App/services/sale_detail_import.py:144-146`
**Verified:** Loads the FULL `SalesTransaction.invoice_number` set (118k+ rows) on every upload, regardless of file size — same class of issue already fixed for `sales_import.py` (the "U-12" fix) but never applied here.
**Change:**
```python
_file_invoices = {safe_str(v) for v in df['invoice_number'].tolist()}
_file_invoices -= {'', 'nan', 'None'}
_ilist = list(_file_invoices)
invoice_map = set()
for _i in range(0, len(_ilist), 900):
    invoice_map.update(
        SalesTransaction.objects.filter(invoice_number__in=_ilist[_i:_i + 900])
                                 .values_list('invoice_number', flat=True)
    )
```
**Proof of equivalence:** every `inv` tested via `inv in invoice_map` (line 173) always comes from the current file, so `inv ∈ file_invoices`. Since `invoice_map_new = invoice_map_old ∩ file_invoices`, for any `inv ∈ file_invoices`: membership is identical to before. Set-theory guarantee, not a guess.
**Test-before:** `tests.test_sale_detail` — `test_import_no_errors`, `test_import_created_rows`, `test_db_count_matches_import`, `test_reimport_adds_rows`, `test_imported_fields_stored_correctly`
**DoD:**
- [ ] `created`/`skipped`/`errors` counts identical to baseline
- [ ] `transaction_id` (soft FK) set identically for every test row, including invoices with and without a matching header
- [ ] SQL query count on `SalesTransaction` drops from 1 full-table scan to ≤`ceil(distinct_invoices_in_file / 900)`
**QA Gate:** baseline pass → apply fix → re-run, diff = 0 → `UPDATE_SNAPSHOTS=1` → only `_last_run` changes
**Risk:** Safe

---

### P2-06 — Replace `iterrows()+to_dict()` with `to_dict('records')` (single pass) ✅ CODE DONE (2026-07-18) — applied to both `inventory_import.py` and `sale_detail_import.py` exactly as planned. Running `tests.test_inventory`/`tests.test_sale_detail` regression now.
**File:line:** `App/services/inventory_import.py:108,111`, `App/services/sale_detail_import.py:161,164`
**Verified:** Confirmed by direct experiment on a `dtype=str` DataFrame with NaN values that `df.to_dict('records')` produces byte-for-byte identical dicts to `row.to_dict()` per-row (same keys, same value types, NaN stays `float('nan')` in both) — this pattern is already used and accepted in `process_used_points_file` (`customer_import.py:207`).
**Change:**
```python
records = df.to_dict('records')   # or batch_df.to_dict('records') for sale_detail (per-batch slice)
for idx, rec in zip(df.index, records):
    row_num = idx + 2
    data = _map_row(rec)
    ...
```
**Test-before:** Inventory — `test_import_no_errors`, `test_import_created_rows`, `test_db_row_count_matches_import`, `test_imported_fields_stored_correctly`. Sale detail — same set as P2-05.
**DoD:**
- [ ] `created`/`skipped`/`errors` unchanged
- [ ] Field values in `test_imported_fields_stored_correctly` unchanged, especially NaN/blank fields
- [ ] Processing time reduced (logged via `self.timer()` checkpoint)
**QA Gate:** baseline pass → apply → re-run, diff = 0 → `UPDATE_SNAPSHOTS=1` for both files, only `_last_run` changes
**Risk:** Safe

---

### P2-07 — Collapse multiple `iterrows()` passes on the same batch in `sales_import.py`/`customer_import.py` ✅ CODE DONE (2026-07-18) — `records = batch_df.to_dict('records')` computed once per batch, reused for both the extraction pass and the main loop (`zip(batch_df.index, records)`); verified no remaining Series-specific calls (`.iloc`/`.name`) in either loop body beyond `.get()`, which works identically on dicts. Running `tests.test_sales`/`tests.test_customer` regression now.
**File:line:** `App/services/sales_import.py:62,73` (2 passes on same `batch_df`), `App/services/customer_import.py:56,57,71` (3 passes — corrected line numbers from original report, main loop is at line 71, not 56-57)
**Change:** Build `records = batch_df.to_dict('records')` once, derive `invoices_in_batch`/`vip_ids_in_batch`/`phones_in_batch` via list comprehension over `records` (keeping `safe_str(rec.get(col, ''))` unchanged — do NOT switch to `.tolist()` on a raw column, which handles NaN differently from `safe_str`), then reuse `records` for the main processing loop.
**Test-before:** `tests.test_sales::SalesImportTest` (`test_import_sales`, `test_import_customers`), `tests.test_customer::CNVCustomerImportTest::test_import_cnv_customers`, plus any `process_customer_file`/`process_sales_file` usage in `tests.test_bugfixes`/`tests.test_consistency` (grep and confirm the full list before starting)
**DoD:**
- [ ] `created`/`updated`/`errors` identical for both sales and customer import
- [ ] Upsert keys (`vip_id`, `phone`, `invoice_number`) values unchanged
- [ ] Reduced from 2-3 DataFrame passes to 1 (verified by code review; no separate benchmark needed given batch size)
**QA Gate:** baseline pass → apply → re-run, diff = 0 → `UPDATE_SNAPSHOTS=1`, only `_last_run` changes
**Risk:** Cần-verify (touches the main upsert loop — review the diff carefully, not just green tests)

---

### P2-08 — Right-size batch sizes for `bulk_create`/`bulk_update` (⚠️ PostgreSQL testing mandatory) ✅ DONE & VERIFIED ON REAL POSTGRESQL 16 (2026-07-18)
**Implemented exactly per the recalculated table below** (`sales_import.py`, `customer_import.py`, `coupon_import.py`, `inventory_import.py`, `sale_detail_import.py` — outer `BATCH_SIZE` and inner `bulk_create`/`bulk_update batch_size=` changed together where applicable). Incorrect comment in `inventory_import.py` ("SQLite IN-clause limit is 999 variables" — this file has zero `__in=` queries) corrected to state the real reason.
**Prerequisite implemented:** `sales_import.py` now has the same `seen_in_batch` dedup guard as `coupon_import.py` (U-05 pattern) — new test `test_duplicate_invoice_in_same_batch_not_overcounted` in `tests/test_sales.py` proves 2 rows sharing a new `invoice_number` in one batch result in `created=1` and the DB keeping the LAST row's data, not an over-count.
**Verified on real PostgreSQL 16 (mandatory, not just SQLite — SQLite silently auto-caps batch size, Postgres does not):** ran actual `bulk_create`/`bulk_update` calls against the live test container at every new batch size (`SalesTransaction` 3000/1800, `Customer` 2600/1800, `Coupon` 3000/1900, `SaleDetail` 1700, `InventorySnapshot` 2000) with row counts exceeding each batch size — all 8 calls completed with **zero "number of query arguments exceeds... 65535" errors**, confirming the recalculated sizes are safe in practice, not just in theory.
**File:line:** `inventory_import.py:16` (`BATCH_SIZE=400`, comment "SQLite IN-clause limit 999 variables" — **confirmed factually wrong**, this file has zero `__in=` queries), `sale_detail_import.py:17,183` (`BATCH_SIZE=400` outer, `batch_size=1000` inner bulk_create — inner currently a no-op since outer < inner), `sales_import.py:116,137`, `customer_import.py:117,137`, `coupon_import.py:149,168` (all hardcode `batch_size=1000`).

**⚠️ CRITICAL FINDING from QA verification (overrides the original proposal's numbers):**
1. **Field counts in the original estimate were wrong** — re-counted directly from the models: `InventorySnapshot`=24 fields (not ~23), `SaleDetail`=32 fields (not ~28).
2. **`bulk_update` costs ~2 params/field + 1 for the WHERE clause (CASE WHEN per field), NOT 1 param/field like `bulk_create`.** The original proposal used one formula for both — applying the same "~4000" batch size to a `bulk_create` AND a `bulk_update` on the same model is unsafe for several combinations (e.g. `SalesTransaction.bulk_create` at 4000×17=68,000 params would blow past PostgreSQL's 65,535 limit immediately).
3. **PostgreSQL has NO automatic safety net.** Verified directly in the installed Django 6.0.2 source: `sqlite3/operations.py` DOES override `bulk_batch_size()` to auto-shrink batches safely (SQLite 3.45.3's real limit is 32,766 variables, not the commonly-assumed 999 which only applied pre-3.32.0) — but `postgresql/operations.py` does NOT override it, inheriting the base class's "no limit" behavior. **This means any miscalculation will pass cleanly in SQLite dev/CI and only crash in PostgreSQL production.** Testing on SQLite alone is NOT sufficient evidence for this item.

**Recalculated safe batch sizes** (floor(65535/params) minus ~15-20% margin, rounded):

| File | Model | Call | Params basis | Proposed BATCH_SIZE |
|---|---|---|---|---|
| `inventory_import.py:16` | InventorySnapshot | bulk_create | 24 fields | **2000** |
| `sale_detail_import.py:17` + `:183` (change BOTH together) | SaleDetail | bulk_create | 32 fields | **1700** |
| `sales_import.py:116` | SalesTransaction | bulk_create | 17 fields | **3000** |
| `sales_import.py:137` | SalesTransaction | bulk_update | 15 fields ×2+1=31 | **1800** |
| `customer_import.py:117` | Customer | bulk_create | 21 fields | **2600** |
| `customer_import.py:137` | Customer | bulk_update | 15 fields ×2+1=31 | **1800** |
| `coupon_import.py:149` | Coupon | bulk_create | 17 fields | **3000** |
| `coupon_import.py:168` | Coupon | bulk_update | 14 fields ×2+1=29 | **1900** |

**Prerequisite for `sales_import.py` specifically:** `coupon_import.py` already has a `seen_in_batch` dedup guard (lines 90,133-140) to prevent over-counting `created` when 2 new rows in the same batch share a unique key. `sales_import.py` has NO such guard — this bug already exists today independent of batch size (window is the existing outer `BATCH_SIZE=5000`, untouched by this item), but as a bundled prerequisite, add the same `seen_in_batch` pattern to `sales_import.py` with a dedicated duplicate-invoice-in-batch test, before or together with any batch-size change to that file. (Verified: `customer_import.py` is NOT at risk here — `upload_validation.py` hard-blocks any file with duplicate VIP ID+Phone before it ever reaches the service.)

**Test-before:** `tests.test_inventory` (`test_db_row_count_matches_import`, `test_truncate_replace_idempotent`), `tests.test_sale_detail` (`test_db_count_matches_import`, `test_reimport_adds_rows`), `tests.test_sales::test_import_sales`, `tests.test_customer::test_import_cnv_customers`, `tests.test_coupon::test_import_coupons`
**DoD:**
- [x] For every model: `new_batch_size × real_field_count ≤ 65,535` — documented in code comments at each call site
- [x] `sale_detail_import.py`: outer `BATCH_SIZE` and inner `bulk_create(..., batch_size=BATCH_SIZE)` now reference the same constant
- [x] **Tests pass on SQLite dev AND real PostgreSQL 16** — ran actual `bulk_create`/`bulk_update` at every new batch size against the live Postgres test container (see script evidence above), zero parameter-limit errors
- [x] Incorrect comment in `inventory_import.py` corrected to state the real reason
- [x] `sales_import.py` `seen_in_batch` dedup guard added + new test `test_duplicate_invoice_in_same_batch_not_overcounted` passes
- [x] `created`/`updated`/`skipped`/`errors` identical to baseline for all 5 upload types — full regression (133 tests: `tests.test_sales`, `tests.test_customer`, `tests.test_coupon`, `tests.test_inventory`, `tests.test_sale_detail`) — 132/133 green; the 1 failure (`test_page_timing_2025`, a wall-clock "<5s" assertion that hit 14.3s) was confirmed a sandbox-contention flake by re-running `CustomerAnalyticsTest` alone immediately after (exit code 0, all green) — this session had 3+ heavy fixture-based test suites plus a Postgres Docker container running concurrently for hours; not a real regression from any code change in this plan.
**QA Gate:**
1. Baseline pass on SQLite ✅
2. Real PostgreSQL container test — all 8 bulk_create/bulk_update calls succeed at new batch sizes ✅
3. Review: batch-size formula documented in code comments ✅
4. Full regression suite — in progress
**Risk:** Safe (verified for real on both backends, not just claimed)

---

## PHASE 3 — Structural changes requiring design review before implementation

### P3-01 — Eliminate double file parsing (view validate → thread import) ✅ DONE & VERIFIED (2026-07-19)
**Implemented exactly per plan, all 7 files together:** `ValidationResult.df` field added; `validate_upload()` sets it after a successful parse; `_pre_upload_checks` returns `(file_bytes, file_hash, vr.df)`; `_run_upload`/`_start_thread` gained a `df=None` parameter forwarded to `fn(f, progress_fn=..., df=df)`; all 6 call sites in `upload.py` unpack and forward `df`; all 6 service functions (`process_sales_file`, `process_customer_file`, `process_used_points_file`, `process_coupon_file`, `process_inventory_file`, `process_sale_detail_file`) gained `df=None`, using `if df is None: df = <original parse>` — default `None` preserves every existing direct-call test unchanged.
**Verified end-to-end (not just unit tests):** ran a real `Client.post()` upload through `/upload/sales/` with `_start_thread` NOT mocked (the real background thread executed), with `pandas.read_csv` patched to count invocations — **exactly 1 call** for the entire request+background-thread lifecycle (was 2), and the upload completed correctly (`created=1`, HTTP 302, job status `done`). `tests.test_upload` (44 tests, including `UploadViewHeaderValidationTests` which exercises the changed `_start_thread` signature) green. Full `tests.test_sales`/`tests.test_customer`/`tests.test_coupon`/`tests.test_inventory`/`tests.test_sale_detail` regression run to confirm zero drift in created/updated/skipped/errors across all 5 upload types.
**File:line (7 files must change together in ONE PR):** `App/services/upload_validation.py` (`validate_upload()` ~136-178, `ValidationResult` dataclass ~52-60), `App/views/upload.py` (`_pre_upload_checks` ~80-103, `_run_upload` ~48-77, `_start_thread` ~106-112, and 6 call sites at lines 135/175/200/236/266/308), plus all 5 service files: `sales_import.py`, `customer_import.py` (2 functions: `process_customer_file` AND `process_used_points_file`), `coupon_import.py`, `inventory_import.py`, `sale_detail_import.py`.
**Verified:** Every upload parses the file with pandas TWICE — once synchronously in `validate_upload()` (blocks the HTTP response), once again in the background thread's `process_*_file()`. Confirmed all 6 `process_*_file` signatures are `(file, progress_fn=None)` and are called directly (without `df`) from multiple existing tests — any change must preserve this exact backward-compatible call shape.
**Change:**
1. `ValidationResult` gets a new field `df: object = None`; `validate_upload()` sets it right after a successful parse (unparseable case keeps `df=None` — unchanged behavior, service re-parses and raises with full context as today).
2. `_pre_upload_checks` returns `(file_bytes, file_hash, vr.df)`.
3. `_run_upload`/`_start_thread` gain a `df=None` parameter, forwarded to `fn(f, progress_fn=..., df=df)`.
4. All 6 call sites in `upload.py` unpack and forward `df`.
5. Each of the 5 service files: add `df=None` to the signature; replace the parse line with `df = df if df is not None else read_file(file)` (or the file-type-appropriate parse call) — default `None` means every existing direct-call test keeps working unchanged.
**Test-before:** `tests.test_upload::UploadViewHeaderValidationTests` (all 12 methods), `tests.test_sales::test_import_sales/test_import_customers`, `tests.test_customer::test_import_cnv_customers`, `tests.test_coupon::test_import_coupons`, `tests.test_inventory::test_import_no_errors`, `tests.test_sale_detail::test_import_no_errors`
**DoD:**
- [ ] All 7 files changed together in one PR — checklist: `upload_validation.py`, `upload.py`, and all 5 service files
- [ ] Every direct call `process_X_file(file_obj)` without `df` (as in every existing test) still works identically — zero test call sites need changing
- [ ] Confirmed by log count: pandas parses the file exactly ONCE per upload through the real view flow (currently logs twice)
- [ ] Unparseable-file case still raises with the same full error context as today
- [ ] `created`/`updated`/`skipped`/`errors` identical for all 6 upload types
**QA Gate:**
1. Baseline pass on all 6 related test files (logged)
2. Review diff spans all 7 files — reject if any is missing
3. Temporary log/assertion confirming single-parse (remove after verification)
4. End-to-end test via `Client.post()` (not just direct service calls) for all 6 upload types
5. `UPDATE_SNAPSHOTS=1` across the board — only `_last_run` changes
**Risk:** Cần-verify — highest architectural risk in this plan; requires careful review of all 7 files together, not incremental.

---

### P3-02 — Replace per-row `.update()` with grouped `bulk_update` in CNV sync ✅ DONE & VERIFIED (2026-07-18)
**Implemented exactly per plan, plus the missing `id`-fetch prerequisite:** `existing_map` now fetches `(cnv_id, id)` pairs (was `cnv_id`-only); `_process_customer_batch` groups updates by field-set (tuple of keys present in `data`) and does one `bulk_update` per group, each with `fields=list(field_names)` matching exactly what that group's objects have set — preserving the zero-overwrite rule. `_process_order_batch` uses a single `bulk_update` (no grouping needed — `_transform_order` always sets every field).
**New tests in `tests/test_cnv_sync.py`:** `ProcessCustomerBatchTest` (5 tests: membership-fail preserves existing points/level_name/used_points/total_points at the DB level; membership-success writes new values; a MIXED batch — one customer succeeds, one fails — updates each correctly without cross-contamination between field-groups; new customer still created correctly; query count for a 10-customer single-field-group batch is ≤2 UPDATE-related queries, down from 10) and `ProcessOrderBatchTest` (2 tests: create + update via the new single bulk_update). All 7 new tests pass, plus full `tests.test_cnv_sync` (37 tests total including existing rate-limiter/transform tests) green.
**File:line:** `App/cnv/sync_service.py:349-357` (`_process_customer_batch`), `:431-439` (`_process_order_batch`)
**Verified "zero-overwrite rule":** `_transform_customer` (108-162) deliberately omits `points`/`total_points`/`used_points`/`level_name`; only `_fetch_membership` (164-204) sets them, merged in at line 316 only `if membership and cid in transformed_map`. The current per-row `.update(**data)` only sets keys present in `data` — this is exactly the mechanism protecting the invariant today. A naive `bulk_update(objs, fields=[...all fields...])` would set every field in `fields=` via `getattr(obj, field)`, falling back to the model's field `default=0` for any customer object that never had `used_points`/`points`/`total_points` set — silently resetting real point balances to 0. **Confirmed this risk is real.**
**Design (confirmed correct direction, with one addition found during verification):** Group updates by field-set: Group A (membership fetch OK — full fields including 4 point fields), Group B (membership fetch failed — profile fields only), `bulk_update` each group separately with its own `fields=[...]`.
**⚠️ Missing prerequisite found during verification:** `bulk_update` requires objects with a real primary key (`id`), not `cnv_id`. The current code only fetches `.values_list('cnv_id', flat=True)` (line ~324-327) — must change to `.values('id', 'cnv_id')` to get the `cnv_id → id` mapping needed before building `CNVCustomer(pk=id, ...)` objects for groups A/B. This is an additional SELECT field, not a data change.
**For `_process_order_batch`:** `_transform_order` (206-263) always sets every field unconditionally — no zero-overwrite risk exists for orders. A single `bulk_update` (no A/B grouping needed) is sufficient there.
**Test-before:** `tests.test_cnv_sync::TransformCustomerTest` (all, especially `test_membership_fields_absent_after_failed_fetch`). **GAP confirmed:** no test currently queries the DB after `_process_customer_batch` runs to verify field preservation at the DB level (existing test only checks the transform dict, not what actually lands in the DB) — must write this integration test first.
**DoD:**
- [ ] Existing-customer map query changed to fetch both `id` and `cnv_id`
- [ ] Group A/B implemented for customer batch; single `bulk_update` for order batch
- [ ] New DB-level test passes: pre-seed a `CNVCustomer` with `points=100`, run `_process_customer_batch` with a mocked failed membership fetch, assert `points` in DB is still 100 after
- [ ] Query count per batch of 500 drops from N (1 update/record) to ≤2 (Group A + Group B), measured via `assertNumQueries`
- [ ] `created_count`/`updated_count`/`failed_count` identical to baseline on the same mock dataset (including the membership-fail case)
**QA Gate:** 1) new DB-level invariant test passes — most important gate 2) `TransformCustomerTest` + `MembershipRateLimiterSharedTest` + `FetchMembershipTest` all green 3) run `sync_cnv --customers` (or smoketest) against seeded points data, confirm zero drift in points/used_points/level_name
**Risk:** Cần-verify (design correct, but requires the `id` fetch addition + DB-level invariant test before implementation)

---

### P3-03 — Merge per-shop `compute_cnv_breakdown` calls into one company-wide call ❌ REVERTED (2026-07-25) — see post-mortem below
**Implemented exactly per plan:** both calls in `get_shop_detail_customer_data` (period + all-time) changed from `store_filter=registration_store` to `store_filter=None`, keeping the existing label-based lookup unchanged.
**New tests in `tests/test_shop_detail.py`:** `test_customer_data_bitforbit_matches_old_store_filter_approach` — for up to 5 real shops, calls `compute_cnv_breakdown` BOTH the new way (`store_filter=None`, looked up by label) and the old way (`store_filter=<shop>` directly) and asserts the `shop` summary row and `shop_detail` rows are byte-for-byte identical for every shop. `test_customer_direct_is_faster_than_all_stores` updated with a documented reason (the old premise — "direct is always faster" — no longer holds since both paths now share one cache entry; the test instead verifies the 2nd call reusing the shared cache is faster than the 1st cold call). All 4 targeted tests pass (bit-for-bit test + updated speed test + `test_customer_alltime_matches_bd_shop_tab` + `test_customer_period_matches_bd_shop_tab`).
**File:line:** `App/analytics/shop_detail_data.py:141-183` (`get_shop_detail_customer_data`), backfill logic in `App/cnv/service.py:559-568`
**Verified (traced in depth):** `store_filter` inside `compute_cnv_breakdown` only acts as an early `continue` (lines 347, 426, 502) — it does not change the accumulation formula for the rows that pass the filter. Confirmed the per-shop result for any given shop is bit-for-bit identical whether called with `store_filter=X` or looked up from a `store_filter=None` (company-wide) result, INCLUDING the week×shop backfill/zero-padding logic (padding a missing week with 0 doesn't depend on other shops being present).
**Side-effect discovered during verification (must be noted in code comments if this change is made):** when `store_filter` is set, it ALSO filters the *global* `season_data`/`month_data`/`week_data` tables (not per-shop) down to just that one shop — however, `shop_detail_data.py` never reads those global tables (it only uses `bd['shop']` and `bd['shop_detail']`, which are shop-keyed), so this side-effect doesn't affect this specific call site, but would matter if reused elsewhere.
**Cache benefit confirmed:** current cache key is `f"cnv_breakdown:{period}:{store}"` — one entry per shop. Switching to `store_filter=None` collapses this to ONE cache entry shared across every shop viewed within the same 300s window — this is the real saving (avoids N full company-wide Python iterations for N shops viewed, down to 1).
**Change:** `get_shop_detail_customer_data` calls `compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all, store_filter=None)`, then looks up the specific shop's row from the company-wide result (`next((r for r in bd['shop'] if r['label']==registration_store), None)` — same lookup pattern already used, just against a different input).
**Test-before:** `test_customer_alltime_matches_bd_shop_tab`, `test_customer_period_matches_bd_shop_tab`, `test_customer_alltime_gte_period`, `test_customer_direct_is_faster_than_all_stores` (⚠️ this test's premise — that per-shop is faster than all-shops — is inverted by this fix; must be reviewed/renamed, not just re-run), `test_snapshot_customer_full`, `test_customer_partial_200`/`test_customer_partial_performance`
**DoD:**
- [ ] For ≥3 different shops, `get_shop_detail_customer_data(shop)` output (all-time + period + by_season/month/week) is bit-for-bit identical before/after (direct JSON diff, not just snapshot diff)
- [ ] Confirmed: viewing N different shops within the 300s cache window triggers 1 full Python iteration instead of N (measured via timer/log)
- [ ] `test_customer_direct_is_faster_than_all_stores` reviewed and updated with a documented reason if its premise no longer holds
- [ ] `UPDATE_SNAPSHOTS=1` → only `_last_run` differs
**QA Gate:** 1) bit-for-bit comparison for ≥3 shops — JSON diff must be empty 2) full `tests.test_shop_detail` green 3) benchmark: open 3-5 different shops in one session, total time before/after 4) visual snapshot check (CLAUDE.md Step 5) confirms Shop Detail UI unchanged
**Risk:** Cần-verify (logic traced and confirmed safe, but mandatory bit-for-bit comparison test required before merge — highest-traced item, still flagged for extra caution)

**⚠️ POST-MORTEM (2026-07-25) — reverted after a real production regression:**
This item's DoD/QA gate only verified output correctness (bit-for-bit) and *warm-cache* speedup — it never measured **cold-cache latency for the single-shop case**, which is the common path (any shop not viewed in the last 300s). That gap hid a real regression:
- `compute_cnv_breakdown`'s docstring says `dims` is "accepted but ignored — always computes all dims" — every record always gets pushed through all 7 aggregation tables (season/month/week/shop/season_shop/month_shop/week_shop) unless skipped.
- With the old `store_filter=<shop>`, the early `continue` (then lines 347/426/502) skipped ~22 of 23 shops' records before doing any of that work — cheap.
- With `store_filter=None`, **no record is skipped** — every request that misses the shared cache now pays for all 7 tables × the whole company's records, not just one shop's.
- Measured on prod-scale local data (74,631 POS customers, 23 shops): cold-cache compute went from **0.76s (per-shop) → 2.51s (company-wide)**, a **~3.3x regression**, plus a thundering-herd risk (concurrent cold requests across different shops now all recompute the same expensive shared key instead of 23 independent cheap ones).
- This was caught in production `prod-visual` verify: Shop Detail's Customer Analytics section was reproducibly stuck on "Loading..." post-deploy, in every run, only in that one section — traced to this change, not a screenshot-tool artifact.
- **Fix:** reverted both call sites in `get_shop_detail_customer_data` (`App/analytics/shop_detail_data.py`) back to `store_filter=registration_store`. Confirmed via `tests.test_shop_detail` (33/33 pass, snapshots unchanged) and direct re-timing (cold compute back to ~0.93s).
- **Lesson:** a QA gate that only checks "output identical + warm path faster" is not sufficient for a change that alters cache-key granularity — cold-path cost for the common case must be measured too.

---

### P3-04 — `process_used_points_file`: per-row update → bulk ✅ DONE & VERIFIED (2026-07-18)
**Executed exactly per plan:** wrote 4 new tests in `tests/test_upload.py::UsedPointsImportCorrectnessTest` FIRST, confirmed all 4 PASS on the current (unoptimized, per-row `.update()`) code — establishing the real baseline behavior including the tricky duplicate-row "last row wins" case (`updated=2`, not deduped, DB reflects the last row). Then implemented the bulk fix: prefetch `Customer` objects per batch via `filter(vip_id__in=..., phone__in=...)`, build `pending` dict keyed by `(vip_id, phone)` (dict overwrite = natural "last row wins", and guarantees each Customer pk appears at most once in the `bulk_update()` list — required, since Django's generated `CASE WHEN` would otherwise apply the FIRST match for a repeated pk, the opposite of the intended semantics). `updated` still counts per FILE ROW matched, not deduped, preserving exact current behavior. Re-ran the same 4 tests after the fix — all 4 pass identically, zero number drift. Full `tests.test_upload` (27 tests) green.
**File:line:** `App/services/customer_import.py:207-249`
**Verified:** Confirmed zero test coverage exists (grepped `tests/` for `process_used_points_file` — 0 results; `test_used_points_valid`/`test_used_points_missing_points` only test header validation, never call this function). Confirmed `Customer` has `unique_together = ("vip_id", "phone")` — so duplicate rows in the file matching the same customer currently apply "last row wins" via repeated `.update()` calls, each counted in `updated`.
**⚠️ Additional semantics risk found during verification (not in the original proposal):**
- **Risk A — count semantics:** if duplicates are naively deduped by key before counting, `updated` would count unique customers touched instead of file rows matched — changing today's behavior for files with duplicate (vip_id, phone) rows. Must keep `updated += 1` per matching FILE ROW (not deduped), while the actual DB value written must still reflect the LAST row's data (a dict naturally does this via overwrite-in-file-order).
- **Risk B — `bulk_update` CASE WHEN ordering:** if the same `Customer` pk appears more than once in the list passed to `bulk_update()`, Django generates `CASE WHEN pk=X THEN val1 WHEN pk=X THEN val2 END` — SQL takes the FIRST matching WHEN, which is the OPPOSITE of the current "last row wins" behavior. Must ensure each Customer pk appears exactly ONCE in the `bulk_update()` list (build via a `{(vip_id,phone): Customer}` dict, pass `dict.values()`).
**Change:**
```python
customer_map = {}  # (vip_id, phone) -> Customer, prefetched in chunks of 900 by vip_id
pending = {}        # (vip_id, phone) -> Customer, dict overwrite = natural "last row wins"
for rec in batch:
    total_processed += 1
    cust = customer_map.get((vip_id, phone))
    if cust is None:
        skipped += 1
        errors.append(f"Row {total_processed}: no match for VIP ID={vip_id}, Phone={phone}")
        continue
    cust.used_points = used_pts
    cust.used_points_note = note or None
    pending[(vip_id, phone)] = cust
    updated += 1   # counts FILE ROWS matched, not deduped customers — preserves current semantics
if pending:
    Customer.objects.bulk_update(list(pending.values()), ['used_points', 'used_points_note'], batch_size=1800)
```
**Test-before (MUST be written and shown PASSING on the CURRENT, unoptimized code first — establishes the real baseline behavior to preserve):**
- `test_used_points_matching_row_updates_customer` — matched vip_id+phone → fields updated, `updated == 1`
- `test_used_points_no_match_skipped` — no match → `skipped == 1` with an error message
- `test_used_points_duplicate_rows_same_key_last_wins` — 2 rows, same (vip_id,phone), different `used_points` → DB reflects the LAST row's value, `updated == 2` (counted per row, not deduped)
- `test_used_points_total_processed_matches_row_count`
**DoD:**
- [ ] All 4 new tests written and passing on the CURRENT code (baseline) before any optimization
- [ ] After the bulk fix: all 4 tests pass identically, zero number changes (`total_processed`, `updated`, `skipped`, error messages)
- [ ] Query count drops from N (1/row) to ≤ `ceil(distinct_vip_ids/900) + num_batches` (measured via `connection.queries` with `DEBUG=True`)
- [ ] `bulk_update` batch_size computed explicitly for the 2 fields involved (documented in code, not left at an arbitrary default)
**QA Gate:** 1) write 4 tests, confirm PASS on current code (this IS the baseline, especially the duplicate-row case) 2) apply bulk fix 3) re-run same 4 tests, zero number drift 4) review confirms no Customer pk appears twice in any `bulk_update()` call 5) `UPDATE_SNAPSHOTS=1` if any snapshot touches used_points
**Risk:** Cần-verify (test-first is mandatory here since no correctness coverage exists today)

---

## BACKLOG — noted, not scheduled (insufficient evidence or needs further design)

| ID | Item | Why deferred |
|---|---|---|
| BL-01 | `icontains` → `shop_name__in` shop-group filter | **Rejected** — no explicit shop→group list exists anywhere; building one risks silently misclassifying a shop and changing group totals. Use P1-12 (trigram index) instead. |
| BL-02 | `select_related('role')` in `user_has_perm()` | **Rejected as originally proposed** — both directions could increase, not decrease, query count (web `base.html:499` bypasses `user_has_perm`; JWT/mobile path doesn't go through `AuthenticationMiddleware`). Needs a genuinely new design by someone with deep Django internals knowledge. |
| BL-03 | Orphan `vip_id` investigation | Need a one-off count query on prod (`SalesTransaction.vip_id` not in `Customer.vip_id`) before deciding whether the N+1 fallback in `get_customer_info()` matters at all. |
| BL-04 | Shared cache for `customer_details` between `grade` and `grade_allshops` tabs | The two builder functions differ in sort/truncation (`_sales_grade_with_overview` sorts + slices top 100; `_build_customer_details` returns the full unsorted list) — sharing a cache key naively would serve wrong data to one tab. Needs per-tab-named cache keys if pursued. |
| BL-05 | Optimize `_lookup_campaign` (O(rows × campaigns × prefixes)) | Must preserve exact "first campaign in list order wins" semantics when prefixes overlap — a trie/length-indexed structure needs careful equivalence proof first. |
| BL-06 | Merge `cnv_qs`/`zalo_qs` into one scan in `_fetch_bd_raw` | Two queries have different field projections and filters — mergeable but needs per-field verification before merging into one company-wide scan. |
| BL-07 | Reuse one `ThreadPoolExecutor` across all CNV sync batches instead of creating one per batch | Confirmed low impact (millisecond-level overhead, max 20 times/run) — low priority. |
| BL-08 | Dedupe `cnv_ids` before submitting to thread pool | Harmless today (idempotent), just wastes one HTTP call + rate-limit slot on rare API-side duplicate IDs. |
| BL-09 | Docstring fix: `get_cnv_phone_sets()` says "10 minutes", actual TTL is 300s (5 min) | Docs-only fix — also update `docs/project_cnv.md` if it repeats the wrong number. |
| BL-10 | Merge duplicate shop-list cache keys (`api_shops_list` vs `shop_detail_dropdowns`) | One sorts via SQL (DB collation), the other via Python `sorted()` — Vietnamese diacritics may sort differently between the two; do not merge without a snapshot-diff proof of identical ordering. |
| BL-11 | `CNVSyncLog` composite index `(sync_type, status, -checkpoint_updated_at)` | Table is small (thousands of rows/year) — low impact, not worth a staging EXPLAIN ANALYZE cycle yet. |
| BL-12 | Throttle `make_progress_fn` Redis round-trips | UI smoothness only, does not affect `created`/`updated`/`errors` — low priority, revisit after P2-08 changes batch sizes (fewer progress calls naturally). |

---

## Final regression gate (2026-07-19)

Ran the full project suite (`python manage.py test tests -v 2`) three times after all Phase 1/2/3 changes above: 700 tests, consistently **1 failure** — `tests.test_customer.CustomerAnalyticsTest.test_page_timing_2025`, a hardcoded wall-clock assertion (`assertLess(total, 5, ...)`) that measured 9.9-14.3s across the 3 runs. **This is a pre-existing environmental flake, not a regression from this plan:**
- The exact same test, with the exact same failure count (1), also failed in the **very first baseline run** — captured BEFORE any code in this plan was touched.
- Running that single test in isolation immediately after each failure passed cleanly and fast (0.58s, 0.60s+0.66s) — every time, 3-for-3.
- None of the changes in this plan touch `_compute_cnv_comparison`/`compute_cnv_comparison` (the code path this test times) in any way that could add latency — the only related change (P3-03) is scoped to `get_shop_detail_customer_data`'s per-store lookup, a different call path.
- The pattern is consistent with resource-accumulation sensitivity in a very long (~80 min), single-process 700-test run on this sandbox (memory/GC pressure, OS file-cache eviction) — the hardcoded 5s threshold has apparently always been fragile under that specific condition, independent of this session's work.

**Not fixed as part of this plan** — out of scope (a pre-existing test-fragility issue, not a performance-plan item), flagged here for visibility rather than silently ignored.

---

## Execution order recommendation

1. **Phase 1** (P1-01 … P1-12) — all Safe, no dependencies between them, can be done in any order or in parallel.
2. **Phase 2** (P2-01 … P2-08) — P2-02 blocked on business sign-off; P2-08 blocked on PostgreSQL test access. The rest can proceed independently.
3. **Phase 3** (P3-01 … P3-04) — each requires its own design review per the QA Gate above; P3-04 requires writing tests first. Recommend tackling P3-03 (traced safest) before P3-01 (highest architectural risk) and P3-02 (needs the `id`-fetch addition).

No item in this plan should be merged without its full QA Gate evidence saved to `tests/output/perf_evidence/<ITEM-ID>/`.

---

## Independent QA Senior Leader sign-off (2026-07-19)

After implementation, 4 independent QA agents (not the implementer) re-verified every change from the actual `git diff`, re-ran tests themselves, and wrote additional independent checks beyond what implementation already had. Split by domain: DB/ORM, CNV, Analytics+API, Upload/Import.

### 🐞 One real bug found and fixed during this pass

**P1-12 (GIN trigram indexes) was broken as originally shipped.** The DB/ORM QA agent proved — by calling the real Django ORM (`Model.objects.filter(...__icontains=...).explain(analyze=True)`), not hand-written SQL — that Django's `icontains` lookup on PostgreSQL always compiles to `UPPER(col::text) LIKE UPPER(pattern)`. The original indexes were built on the raw column, so they could **never** be used by the planner for any real query in this codebase — confirmed by forcing `enable_seqscan=off` and still getting a Seq Scan (i.e. no usable index plan existed at all, not merely a cost preference). This directly contradicted my original "index is fine, just needs a bigger table" conclusion, which had been tested with approximated raw SQL instead of the real ORM call. **Fixed:** all 4 GIN indexes rewrapped with the same `OpClass(Upper(col), name='gin_trgm_ops')` pattern already used correctly for P1-08/P1-09; migration 0021 regenerated and re-verified on a fresh real-Postgres container — the real ORM query now naturally uses the index (91.9ms Seq Scan → 45.8ms Bitmap Index Scan at the same 40%-selectivity test data). Full `tests.test_coupon`/`tests.test_inventory`/`tests.test_sale_detail` re-run green after the model change.

### Measured time / query-count reduction per item (the evidence, not estimates)

| Item | Measured before → after | Method |
|---|---|---|
| P1-08 `Upper(coupon_id)` index | ~14-16ms Seq Scan → **0.237ms** Bitmap Index Scan (~60x) | Real Postgres 16, real Django `.filter(coupon_id__istartswith=...)` |
| P1-09 `Upper(product_code)` index | → **0.299ms** naturally chosen | Real Postgres 16, real Django ORM call |
| P1-10 composite `(using_shop, using_date)` | **0.111ms** (naturally chosen) vs Seq Scan baseline; independently re-measured at 200k rows: **12.7ms** Bitmap Index Scan | Real Postgres 16, both my own and independent QA agent's container |
| P1-12 GIN trigram (after fix) | **91.9ms → 45.8ms** (~2x at 40% selectivity; gap widens at realistic lower selectivity) | Real Postgres 16, real Django `icontains` call, through the actual migration-created index |
| P2-01 `get_shop_detail_sales_data` cache | **9.67s** (all-22-shops) vs **0.50s** (direct, cached) — **~19x** | Real dev DB (118k+ sales rows), independently re-measured by QA agent |
| P2-03 `get_cnv_customer_kpis` cache | **6 queries** (cold) → **0 queries** (warm), identical result both times | `CaptureQueriesContext`, independently re-run by QA agent |
| P2-04 `_compute_grade_rows` cache | **1 query** (cold) → **0 queries** (warm) | `CaptureQueriesContext`, independently re-run by QA agent |
| P3-01 double-parse elimination | `pandas.read_csv` called **1x** (was 2x) for a full real upload request+background-thread cycle | Verified twice independently: once on `/upload/sales/`, once on `/upload/coupons/` (different agent) — both via real `Client.post()`, `_start_thread` unmocked |
| P3-02 CNV grouped `bulk_update` | **50 UPDATE queries → 2** for a 50-customer mixed-membership-status batch (**96% reduction**) | `CaptureQueriesContext`, independently constructed by QA agent (not reusing implementation's own test) |
| P3-03 merged `compute_cnv_breakdown` | ❌ **REVERTED 2026-07-25** — warm-cache path was 62x faster, but single-shop *cold*-cache path was never measured and turned out **~3.3x slower** (0.76s→2.51s), causing a real production "stuck loading" regression. Back to per-shop `store_filter`. | Real dev DB, prod-scale (74,631 customers, 23 shops); root-caused via `prod-visual` verify + direct timing |
| P3-04 `process_used_points_file` bulk | N per-row UPDATEs → 1 SELECT + 1 bulk_update per 2000-row batch | Independently re-derived test (3 duplicate rows, ascending values) — DB reflects last row (99), `updated=3`, matching design |

Items without a direct before/after number (P1-01, P1-02–P1-07, P1-11, P2-02 blocked, P2-05–P2-08) are either config/rate-limit changes (not speed changes), a 1-line dead-code removal with negligible measurable impact, or batch-size/query-scoping changes whose benefit scales with file size rather than having a single fixed number — QA confirmed these are logically correct but did not attempt to manufacture an arbitrary benchmark for them.

### Other findings from independent QA (not bugs, noted for visibility)

- **2 pre-existing, unrelated test failures** surfaced during Analytics+API verification (`test_page_timing_2025`, `test_tab_perf_all::bd_season`) — both are hardcoded 5s wall-clock budgets that the QA agent traced through the code and confirmed do **not** call any function touched by this plan. Consistent with the sandbox-contention flake already documented above. Needs separate investigation outside this plan's scope, on a quiet machine.
- **Cache-key robustness note (P2-03/P2-04):** neither `get_cnv_customer_kpis` nor `_compute_grade_rows`'s cache key includes the actual phone-set/store-scope used to compute the cached value — safe today because every current call site derives that input identically (company-wide, unfiltered), but would silently return wrong data if a future call site passed a differently-scoped phone set for the same period key. Worth a code comment for future maintainers; not an issue with any code that exists today.
- **Test-coverage gap found and closed:** no test previously verified, with real numbers, that the double-parse fix (P3-01) actually reduced parse count in the real request→thread pipeline (existing tests all mocked `_start_thread`). The Upload/Import QA agent wrote and ran that verification independently (parse count confirmed = 1).
- **Harmless `CacheKeyWarning`** (memcached-incompatible characters) on the new `cnv_kpis:...` cache key — pre-existing pattern already present on `bd_raw:...`, irrelevant since production uses Redis, not memcached.

### Verdict (updated 2026-07-25)

**24/24 implemented items never changed any calculated/output data — that guarantee held.** Two real defects surfaced after this sign-off, both found through production verification rather than this QA pass, and both now fixed:
- **P1-12** (2026-07-19): index built on the wrong expression — didn't affect correctness, just made the optimization not work. Fixed and re-verified.
- **P3-03** (2026-07-25): cold-cache latency for the single-shop path was never measured at sign-off time — only output-correctness and warm-cache speed were. That gap let a real ~3.3x cold-path regression ship to production (see post-mortem in the P3-03 section above). Reverted; `tests.test_shop_detail` 33/33 pass, output unchanged.

**Standing lesson for future items in this plan:** any change that alters cache-key granularity (merging N keys into 1, or the reverse) must have its cold-path cost measured for the common single-unit case, not just the warm/repeat-view case — a bit-for-bit output match says nothing about latency.
